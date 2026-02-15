import AppIntents
import HAWatchCore

/// AppEntity representing a Home Assistant entity for use in widget configuration.
struct HAEntity: AppEntity {
    static var typeDisplayRepresentation = TypeDisplayRepresentation(name: "Entity")
    static var defaultQuery = HAEntityQuery()

    var id: String  // entity_id
    var name: String

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)")
    }

    init(id: String, name: String) {
        self.id = id
        self.name = name
    }
}

struct HAEntityQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [HAEntity] {
        // Try to fetch friendly names from HA API
        let settings = await SettingsManager.shared.appSettings
        if let baseURL = settings.baseURL, !settings.accessToken.isEmpty {
            let client = HAAPIClient(baseURL: baseURL, token: settings.accessToken)
            let templateService = TemplateService(apiClient: client)
            if let states = try? await templateService.fetchEntityStates(entityIds: identifiers) {
                return identifiers.map { id in
                    let name = states[id]?.displayName ?? Self.nameFromId(id)
                    return HAEntity(id: id, name: name)
                }
            }
        }

        // Fallback: derive names from entity IDs
        return identifiers.map { id in
            HAEntity(id: id, name: Self.nameFromId(id))
        }
    }

    func suggestedEntities() async throws -> [HAEntity] {
        let settings = await SettingsManager.shared.appSettings
        let entityIds = settings.complicationEntities
        guard !entityIds.isEmpty else { return [] }

        // Try to fetch friendly names
        if let baseURL = settings.baseURL, !settings.accessToken.isEmpty {
            let client = HAAPIClient(baseURL: baseURL, token: settings.accessToken)
            let templateService = TemplateService(apiClient: client)
            if let states = try? await templateService.fetchEntityStates(entityIds: entityIds) {
                return entityIds.map { id in
                    let name = states[id]?.displayName ?? Self.nameFromId(id)
                    return HAEntity(id: id, name: name)
                }
            }
        }

        return entityIds.map { id in
            HAEntity(id: id, name: Self.nameFromId(id))
        }
    }

    /// Derive a display name from an entity_id (e.g. "sensor.living_room_temp" -> "Living Room Temp")
    static func nameFromId(_ entityId: String) -> String {
        let objectId = entityId.split(separator: ".").dropFirst().joined(separator: ".")
        return objectId.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
