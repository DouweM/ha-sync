import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// REST + transient WebSocket client for Home Assistant API.
public actor HAAPIClient {
    private let baseURL: URL
    private let token: String
    private let session: URLSession

    public init(baseURL: URL, token: String, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.token = token
        self.session = session
    }

    // MARK: - REST API

    /// Render a Jinja2 template via POST /api/template.
    public func renderTemplate(_ template: String) async throws -> String {
        let url = baseURL.appendingPathComponent("api/template")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = ["template": template]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await performRequest(request)
        try validateResponse(response)
        return String(data: data, encoding: .utf8) ?? ""
    }

    /// Validate connection by fetching /api/config.
    public func validateConnection() async throws -> HAConfig {
        let url = baseURL.appendingPathComponent("api/config")
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await performRequest(request)
        try validateResponse(response)
        return try JSONDecoder().decode(HAConfig.self, from: data)
    }

    /// Fetch history data for an entity via GET /api/history/period.
    public func fetchHistory(
        entityId: String,
        start: Date,
        end: Date = Date()
    ) async throws -> [[HAHistoryEntry]] {
        let formatter = ISO8601DateFormatter()
        let startStr = formatter.string(from: start)

        guard var components = URLComponents(url: baseURL.appendingPathComponent("api/history/period/\(startStr)"), resolvingAgainstBaseURL: false) else {
            throw HAAPIError.invalidURL("api/history/period/\(startStr)")
        }
        components.queryItems = [
            URLQueryItem(name: "filter_entity_id", value: entityId),
            URLQueryItem(name: "end_time", value: formatter.string(from: end)),
            URLQueryItem(name: "minimal_response", value: "true"),
        ]

        guard let historyURL = components.url else {
            throw HAAPIError.invalidURL(components.description)
        }
        var request = URLRequest(url: historyURL)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await performRequest(request)
        try validateResponse(response)
        return try JSONDecoder().decode([[HAHistoryEntry]].self, from: data)
    }

    /// Fetch camera snapshot via GET /api/camera_proxy/{entity_id}.
    public func fetchCameraSnapshot(entityId: String) async throws -> Data {
        let url = baseURL.appendingPathComponent("api/camera_proxy/\(entityId)")
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await performRequest(request)
        try validateResponse(response)
        return data
    }

    /// Fetch an authenticated image (e.g. /local/...).
    public func fetchImage(path: String) async throws -> Data {
        let url: URL
        if path.hasPrefix("http") {
            guard let parsed = URL(string: path) else {
                throw HAAPIError.invalidURL(path)
            }
            url = parsed
        } else {
            url = baseURL.appendingPathComponent(path)
        }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await performRequest(request)
        try validateResponse(response)
        return data
    }

    /// Call a Home Assistant service via POST /api/services/{domain}/{service}.
    public func callService(
        domain: String,
        service: String,
        entityId: String
    ) async throws {
        let url = baseURL.appendingPathComponent("api/services/\(domain)/\(service)")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = ["entity_id": entityId]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await performRequest(request)
        try validateResponse(response)
    }

    // MARK: - WebSocket (transient, for dashboard config)

    /// Fetch dashboard configuration via WebSocket.
    /// Opens connection, authenticates, fetches config, then closes.
    public func fetchDashboardConfig(dashboardId: String? = nil) async throws -> DashboardConfig {
        let wsURL = try buildWebSocketURL()
        let messages = try await webSocketExchange(url: wsURL, dashboardId: dashboardId)

        guard let configData = messages.last,
              let data = configData.data(using: .utf8)
        else {
            throw HAAPIError.noDashboardConfig
        }

        let wrapper = try JSONDecoder().decode(WebSocketResultWrapper.self, from: data)
        guard let result = wrapper.result else {
            throw HAAPIError.noDashboardConfig
        }

        let resultData = try JSONSerialization.data(withJSONObject: result)
        return try JSONDecoder().decode(DashboardConfig.self, from: resultData)
    }

    /// Fetch list of available dashboards via WebSocket.
    public func fetchDashboardList() async throws -> [DashboardListItem] {
        let wsURL = try buildWebSocketURL()
        let messages = try await webSocketExchange(url: wsURL, command: "lovelace/dashboards/list", params: [:])

        guard let responseData = messages.last,
              let data = responseData.data(using: .utf8)
        else {
            throw HAAPIError.noDashboardConfig
        }

        let wrapper = try JSONDecoder().decode(WebSocketArrayResultWrapper<DashboardListItem>.self, from: data)
        return wrapper.result ?? []
    }

    // MARK: - Private helpers

    private func performRequest(_ request: URLRequest) async throws -> (Data, URLResponse) {
        #if canImport(FoundationNetworking)
        return try await withCheckedThrowingContinuation { continuation in
            session.dataTask(with: request) { data, response, error in
                if let error = error {
                    continuation.resume(throwing: error)
                } else if let data = data, let response = response {
                    continuation.resume(returning: (data, response))
                } else {
                    continuation.resume(throwing: HAAPIError.unknownError)
                }
            }.resume()
        }
        #else
        return try await session.data(for: request)
        #endif
    }

    private func validateResponse(_ response: URLResponse) throws {
        guard let httpResponse = response as? HTTPURLResponse else { return }
        switch httpResponse.statusCode {
        case 200...299:
            return
        case 401:
            throw HAAPIError.unauthorized
        case 404:
            throw HAAPIError.notFound
        default:
            throw HAAPIError.httpError(statusCode: httpResponse.statusCode)
        }
    }

    private func buildWebSocketURL() throws -> URL {
        var urlString = baseURL.absoluteString
        if urlString.hasPrefix("https://") {
            urlString = "wss://" + urlString.dropFirst("https://".count)
        } else if urlString.hasPrefix("http://") {
            urlString = "ws://" + urlString.dropFirst("http://".count)
        }
        if !urlString.hasSuffix("/") { urlString += "/" }
        urlString += "api/websocket"
        guard let url = URL(string: urlString) else {
            throw HAAPIError.invalidURL(urlString)
        }
        return url
    }

    private func webSocketExchange(
        url: URL,
        dashboardId: String? = nil,
        command: String = "lovelace/config",
        params: [String: String]? = nil
    ) async throws -> [String] {
        // WebSocket implementation is platform-specific.
        // On Apple platforms, URLSessionWebSocketTask is available.
        // On Linux, we'd need a third-party WebSocket library.
        // For now, provide the Apple implementation with a Linux stub.

        #if canImport(Darwin)
        return try await appleWebSocketExchange(url: url, dashboardId: dashboardId, command: command, params: params)
        #else
        // Linux stub - in production, use a library like swift-nio-websocket
        throw HAAPIError.webSocketUnavailable
        #endif
    }

    #if canImport(Darwin)
    private func appleWebSocketExchange(
        url: URL,
        dashboardId: String?,
        command: String,
        params: [String: String]?
    ) async throws -> [String] {
        let wsTask = session.webSocketTask(with: url)
        wsTask.resume()
        var messages: [String] = []

        // 1. Receive auth_required
        let authRequired = try await wsTask.receive()
        if case .string(let msg) = authRequired {
            messages.append(msg)
        }

        // 2. Send auth
        let authMsg = """
        {"type": "auth", "access_token": "\(token)"}
        """
        try await wsTask.send(.string(authMsg))

        // 3. Receive auth_ok
        let authOk = try await wsTask.receive()
        if case .string(let msg) = authOk {
            messages.append(msg)
        }

        // 4. Send command
        var commandDict: [String: Any] = [
            "id": 1,
            "type": command,
        ]
        if let dashboardId = dashboardId {
            commandDict["url_path"] = dashboardId
        }
        if let params = params {
            for (key, value) in params {
                commandDict[key] = value
            }
        }
        let commandData = try JSONSerialization.data(withJSONObject: commandDict)
        let commandStr = String(data: commandData, encoding: .utf8)!
        try await wsTask.send(.string(commandStr))

        // 5. Receive result
        let result = try await wsTask.receive()
        if case .string(let msg) = result {
            messages.append(msg)
        }

        // 6. Close
        wsTask.cancel(with: .goingAway, reason: nil)

        return messages
    }
    #endif
}

// MARK: - Error types

public enum HAAPIError: Error, Sendable {
    case unauthorized
    case notFound
    case httpError(statusCode: Int)
    case noDashboardConfig
    case webSocketUnavailable
    case invalidURL(String)
    case unknownError
}

// MARK: - API response types

public struct HAConfig: Codable, Sendable {
    public var locationName: String?
    public var version: String?

    enum CodingKeys: String, CodingKey {
        case locationName = "location_name"
        case version
    }
}

public struct HAHistoryEntry: Codable, Sendable {
    public var state: String
    public var lastChanged: String?

    enum CodingKeys: String, CodingKey {
        case state
        case lastChanged = "last_changed"
    }
}

public struct DashboardListItem: Codable, Sendable, Hashable {
    public var id: String?
    public var urlPath: String?
    public var title: String?
    public var icon: String?
    public var showInSidebar: Bool?
    public var requireAdmin: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case urlPath = "url_path"
        case title, icon
        case showInSidebar = "show_in_sidebar"
        case requireAdmin = "require_admin"
    }
}

// MARK: - WebSocket response wrappers

private struct WebSocketResultWrapper: Codable {
    var id: Int?
    var type: String?
    var success: Bool?
    var result: [String: Any]?

    enum CodingKeys: String, CodingKey {
        case id, type, success, result
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(Int.self, forKey: .id)
        type = try container.decodeIfPresent(String.self, forKey: .type)
        success = try container.decodeIfPresent(Bool.self, forKey: .success)

        // Decode result as raw JSON
        if let rawData = try? container.decodeIfPresent(RawJSON.self, forKey: .result) {
            result = rawData.value as? [String: Any]
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(id, forKey: .id)
        try container.encodeIfPresent(type, forKey: .type)
        try container.encodeIfPresent(success, forKey: .success)
    }
}

private struct WebSocketArrayResultWrapper<T: Codable>: Codable {
    var id: Int?
    var type: String?
    var success: Bool?
    var result: [T]?
}

private struct RawJSON: Codable {
    let value: Any

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let dict = try? container.decode([String: RawJSON].self) {
            value = dict.mapValues { $0.value }
        } else if let array = try? container.decode([RawJSON].self) {
            value = array.map { $0.value }
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else {
            value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        // Not needed for decoding-only usage
    }
}
