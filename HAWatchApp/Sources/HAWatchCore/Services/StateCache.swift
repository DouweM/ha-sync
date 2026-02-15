import Foundation

/// In-memory entity state cache with batch fetch support.
public actor StateCache {
    private var cache: [String: EntityState] = [:]
    private let templateService: TemplateService

    public init(templateService: TemplateService) {
        self.templateService = templateService
    }

    /// Get cached state for an entity.
    public func getState(_ entityId: String) -> EntityState? {
        cache[entityId]
    }

    /// Get the raw state string for an entity.
    public func getStateValue(_ entityId: String) -> String? {
        cache[entityId]?.state
    }

    /// Get display name for an entity.
    public func getDisplayName(_ entityId: String) -> String {
        if let cached = cache[entityId], !cached.name.isEmpty {
            return cached.name
        }
        let objectId = entityId.split(separator: ".").dropFirst().joined(separator: ".")
        return objectId.replacingOccurrences(of: "_", with: " ").capitalized
    }

    /// Store an entity state in the cache.
    public func set(_ entityId: String, state: EntityState) {
        cache[entityId] = state
    }

    /// Batch fetch and cache entity states.
    public func fetchStates(for entityIds: Set<String>) async throws {
        guard !entityIds.isEmpty else { return }

        // Only fetch entities not already cached
        let toFetch = entityIds.filter { cache[$0] == nil }
        guard !toFetch.isEmpty else { return }

        let states = try await templateService.fetchEntityStates(entityIds: Array(toFetch))
        for (entityId, state) in states {
            cache[entityId] = state
        }
    }

    /// Force refresh all cached entities.
    public func refreshAll() async throws {
        let entityIds = Array(cache.keys)
        guard !entityIds.isEmpty else { return }

        let states = try await templateService.fetchEntityStates(entityIds: entityIds)
        for (entityId, state) in states {
            cache[entityId] = state
        }
    }

    /// Clear the cache.
    public func clear() {
        cache.removeAll()
    }

    /// Extract all entity IDs from a config structure.
    public static func extractEntityIds(from config: Any) -> Set<String> {
        var entities: Set<String> = []
        extractEntitiesRecursive(from: config, into: &entities)
        return entities
    }

    private static func extractEntitiesRecursive(from obj: Any, into entities: inout Set<String>) {
        if let dict = obj as? [String: Any] {
            for key in ["entity", "entity_id"] {
                if let value = dict[key] as? String {
                    entities.insert(value)
                } else if let values = dict[key] as? [String] {
                    entities.formUnion(values)
                }
            }
            for value in dict.values {
                extractEntitiesRecursive(from: value, into: &entities)
            }
        } else if let array = obj as? [Any] {
            for item in array {
                extractEntitiesRecursive(from: item, into: &entities)
            }
        }
    }

    /// Extract entity IDs from typed config models.
    public static func extractEntityIds(from view: ViewConfig) -> Set<String> {
        var entities: Set<String> = []

        for badge in view.badges ?? [] {
            if let entity = badge.entity { entities.insert(entity) }
            extractEntityIds(from: badge.visibility, into: &entities)
        }

        for section in view.sections ?? [] {
            extractEntityIds(from: section.visibility, into: &entities)
            for card in section.cards ?? [] {
                extractEntityIds(from: card, into: &entities)
            }
        }

        return entities
    }

    private static func extractEntityIds(from card: CardConfig, into entities: inout Set<String>) {
        if let entity = card.entity { entities.insert(entity) }
        if let entityList = card.entities {
            entities.formUnion(entityList.map(\.entity))
        }
        if let target = card.target?.entityId {
            entities.formUnion(target)
        }
        extractEntityIds(from: card.visibility, into: &entities)
        for badge in card.badges ?? [] {
            if let entity = badge.entity { entities.insert(entity) }
            extractEntityIds(from: badge.visibility, into: &entities)
        }
        if let nestedCard = card.card {
            extractEntityIds(from: nestedCard, into: &entities)
        }
        // auto-entities include rules with explicit entity_id
        if let filter = card.filter {
            for rule in filter.include ?? [] {
                if let entityId = rule.entityId { entities.insert(entityId) }
            }
        }
        // map entities
        for mapEntity in card.mapCardEntities ?? [] {
            if let entity = mapEntity.entity { entities.insert(entity) }
        }
        if let focus = card.focusEntity { entities.insert(focus) }
    }

    private static func extractEntityIds(from conditions: [VisibilityCondition]?, into entities: inout Set<String>) {
        guard let conditions = conditions else { return }
        for condition in conditions {
            switch condition {
            case .state(let entity, _, _), .numericState(let entity, _, _):
                if !entity.isEmpty { entities.insert(entity) }
            case .or(let nested), .and(let nested), .not(let nested):
                extractEntityIds(from: nested, into: &entities)
            case .user, .screen:
                break
            }
        }
    }
}
