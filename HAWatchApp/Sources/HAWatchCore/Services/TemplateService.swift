import Foundation

/// Batch Jinja2 template evaluation via HA REST API.
/// Uses ||| separator to combine multiple template evaluations into a single API call.
public actor TemplateService {
    private let apiClient: HAAPIClient

    public init(apiClient: HAAPIClient) {
        self.apiClient = apiClient
    }

    /// Evaluate a single Jinja2 template.
    public func evaluate(_ template: String) async throws -> String {
        try await apiClient.renderTemplate(template)
    }

    /// Evaluate multiple templates in a single API call using ||| separator.
    /// Returns results in the same order as input templates.
    public func evaluateBatch(_ templates: [String]) async throws -> [String] {
        guard !templates.isEmpty else { return [] }

        if templates.count == 1 {
            let result = try await evaluate(templates[0])
            return [result]
        }

        let combined = templates.joined(separator: "|||")
        let result = try await evaluate(combined)
        let parts = result.components(separatedBy: "|||")

        // Pad with empty strings if API returned fewer parts
        var results = parts.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        while results.count < templates.count {
            results.append("")
        }

        return Array(results.prefix(templates.count))
    }

    /// Fetch entity states in batch using template API.
    /// Returns a dictionary of entity_id -> EntityState.
    public func fetchEntityStates(entityIds: [String]) async throws -> [String: EntityState] {
        guard !entityIds.isEmpty else { return [:] }

        let lines = entityIds.map { entityId in
            """
            \(entityId)|||{{ states("\(entityId)") }}|||{{ state_attr("\(entityId)", "friendly_name") | default("", true) | replace("\\n", " ") }}|||{{ state_attr("\(entityId)", "unit_of_measurement") | default("", true) }}|||{{ state_attr("\(entityId)", "icon") | default("", true) }}|||{{ state_attr("\(entityId)", "device_class") | default("", true) }}|||{{ state_attr("\(entityId)", "entity_picture") | default("", true) }}|||{{ state_attr("\(entityId)", "temperature") | default("", true) }}
            """
        }

        let template = lines.joined(separator: "\n")
        let output = try await apiClient.renderTemplate(template)

        var states: [String: EntityState] = [:]

        for line in output.split(separator: "\n") {
            let parts = line.split(separator: "|||", omittingEmptySubsequences: false).map {
                $0.trimmingCharacters(in: .whitespaces)
            }
            guard parts.count >= 3 else { continue }

            let entityId = parts[0]
            let state = parts.count > 1 ? parts[1] : ""
            let name = parts.count > 2 ? parts[2] : ""
            let unit = parts.count > 3 ? parts[3] : ""
            let icon = parts.count > 4 ? parts[4] : ""
            let deviceClass = parts.count > 5 ? parts[5] : ""
            let entityPicture = parts.count > 6 ? parts[6] : ""
            let temperature = parts.count > 7 ? parts[7] : ""

            var attributes: [String: String] = [:]
            if !entityPicture.isEmpty {
                attributes["entity_picture"] = entityPicture
            }
            if !temperature.isEmpty {
                attributes["temperature"] = temperature
            }

            states[entityId] = EntityState(
                entityId: entityId,
                state: state,
                name: name,
                unit: unit,
                icon: icon,
                deviceClass: deviceClass,
                attributes: attributes
            )
        }

        return states
    }

    /// Fetch entities matching a label.
    public func fetchEntitiesWithLabel(_ label: String) async throws -> Set<String> {
        let template = "{{ label_entities(\"\(label)\") | tojson }}"
        let output = try await apiClient.renderTemplate(template)
        let cleaned = output.replacingOccurrences(of: "\n", with: "")

        guard let data = cleaned.data(using: .utf8),
              let array = try? JSONSerialization.jsonObject(with: data) as? [String]
        else { return [] }

        return Set(array)
    }

    /// Search entities by domain.
    public func searchEntities(domain: String) async throws -> [EntitySearchResult] {
        let template = """
        [{% for e in states.\(domain) %}{"entity_id": {{ e.entity_id | tojson }}, "state": {{ e.state | tojson }}, "name": {{ (e.name | default("")) | tojson }}, "icon": {{ (e.attributes.get("icon", "") | string) | tojson }}, "attributes": {{% for k, v in e.attributes.items() if v is string or v is number %}{{ k | tojson }}: {{ v | string | tojson }}{% if not loop.last %}, {% endif %}{% endfor %}}}{% if not loop.last %},{% endif %}{% endfor %}]
        """

        let output = try await apiClient.renderTemplate(template)
        let cleaned = output.replacingOccurrences(of: "\n", with: "")

        guard let data = cleaned.data(using: .utf8) else { return [] }
        return (try? JSONDecoder().decode([EntitySearchResult].self, from: data)) ?? []
    }

    /// Fetch user ID mapping from person entities.
    public func fetchUserIds() async throws -> [String: String] {
        let template = """
        [{% for p in states.person %}{"name": {{ p.name | lower | tojson }}, "user_id": {{ (p.attributes.user_id | default("")) | tojson }}}{% if not loop.last %},{% endif %}{% endfor %}]
        """

        let output = try await apiClient.renderTemplate(template)
        let cleaned = output.replacingOccurrences(of: "\n", with: "")

        guard let data = cleaned.data(using: .utf8),
              let persons = try? JSONDecoder().decode([PersonMapping].self, from: data)
        else { return [:] }

        var mapping: [String: String] = [:]
        for person in persons where !person.userId.isEmpty {
            mapping[person.name] = person.userId
        }
        return mapping
    }
}

// MARK: - Response types

public struct EntitySearchResult: Codable, Sendable {
    public var entityId: String
    public var state: String
    public var name: String
    public var icon: String?
    public var attributes: EntitySearchAttributes?

    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id"
        case state, name, icon, attributes
    }
}

/// Generic attribute dictionary decoded from search results.
/// Supports any string/numeric/boolean attribute value, coerced to String.
public struct EntitySearchAttributes: Codable, Sendable {
    public var values: [String: String]

    public init(values: [String: String] = [:]) {
        self.values = values
    }

    public subscript(key: String) -> String? {
        values[key]
    }

    private struct DynamicKey: CodingKey {
        var stringValue: String
        var intValue: Int?
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { self.stringValue = String(intValue); self.intValue = intValue }
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicKey.self)
        var dict: [String: String] = [:]
        for key in container.allKeys {
            if let s = try? container.decode(String.self, forKey: key) {
                dict[key.stringValue] = s
            } else if let d = try? container.decode(Double.self, forKey: key) {
                dict[key.stringValue] = d == Double(Int(d)) ? String(Int(d)) : String(d)
            } else if let b = try? container.decode(Bool.self, forKey: key) {
                dict[key.stringValue] = String(b)
            }
            // Skip complex types (arrays, objects) — not useful for attribute matching
        }
        self.values = dict
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: DynamicKey.self)
        for (key, value) in values {
            if let codingKey = DynamicKey(stringValue: key) {
                try container.encode(value, forKey: codingKey)
            }
        }
    }
}

private struct PersonMapping: Codable {
    var name: String
    var userId: String

    enum CodingKeys: String, CodingKey {
        case name
        case userId = "user_id"
    }
}
