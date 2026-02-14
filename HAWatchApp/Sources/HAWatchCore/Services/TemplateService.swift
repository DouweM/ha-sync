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
            \(entityId)|||{{ states("\(entityId)") }}|||{{ state_attr("\(entityId)", "friendly_name") | default("", true) | replace("\\n", " ") }}|||{{ state_attr("\(entityId)", "unit_of_measurement") | default("", true) }}|||{{ state_attr("\(entityId)", "icon") | default("", true) }}|||{{ state_attr("\(entityId)", "device_class") | default("", true) }}
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

            states[entityId] = EntityState(
                entityId: entityId,
                state: state,
                name: name,
                unit: unit,
                icon: icon,
                deviceClass: deviceClass
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
        [{% for e in states.\(domain) %}{"entity_id": {{ e.entity_id | tojson }}, "state": {{ e.state | tojson }}, "name": {{ (e.name | default("")) | tojson }}, "icon": {{ (e.attributes.get("icon", "") | string) | tojson }}, "attributes": {"known": {{ (e.attributes.get("known", "") | string) | tojson }}, "device_class": {{ (e.attributes.get("device_class", "") | string) | tojson }}, "friendly_name": {{ (e.attributes.get("friendly_name", "") | string) | tojson }}}}{% if not loop.last %},{% endif %}{% endfor %}]
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

public struct EntitySearchAttributes: Codable, Sendable {
    public var known: String?
    public var deviceClass: String?
    public var friendlyName: String?

    enum CodingKeys: String, CodingKey {
        case known
        case deviceClass = "device_class"
        case friendlyName = "friendly_name"
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
