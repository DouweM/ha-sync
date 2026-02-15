import Foundation

public struct AppSettings: Codable, Sendable {
    public var serverURL: String
    public var accessToken: String
    public var defaultDashboardId: String?
    public var defaultViewPath: String?
    public var complicationEntities: [String]
    public var pollingInterval: TimeInterval

    public init(
        serverURL: String = "",
        accessToken: String = "",
        defaultDashboardId: String? = nil,
        defaultViewPath: String? = nil,
        complicationEntities: [String] = [],
        pollingInterval: TimeInterval = 30
    ) {
        self.serverURL = serverURL
        self.accessToken = accessToken
        self.defaultDashboardId = defaultDashboardId
        self.defaultViewPath = defaultViewPath
        self.complicationEntities = complicationEntities
        self.pollingInterval = pollingInterval
    }

    public var isConfigured: Bool {
        !serverURL.isEmpty && !accessToken.isEmpty
    }

    public var baseURL: URL? {
        URL(string: serverURL)
    }
}
