import Foundation

/// Resolves auto-entities filter rules to matching entity IDs.
/// Port of render.py:671-788.
public actor AutoEntitiesResolver {
    private let templateService: TemplateService
    private let stateCache: StateCache

    public init(templateService: TemplateService, stateCache: StateCache) {
        self.templateService = templateService
        self.stateCache = stateCache
    }

    /// Resolve auto-entities filter to a list of (entityId, options) pairs.
    public func resolve(filter: AutoEntitiesFilter) async throws -> [(entityId: String, options: AutoEntitiesOptions)] {
        let includeRules = filter.include ?? []
        var matched: [(String, AutoEntitiesOptions)] = []

        for rule in includeRules {
            // Explicit entity_id rule
            if let entityId = rule.entityId, rule.domain == nil {
                let options = rule.options ?? AutoEntitiesOptions()
                // Ensure entity is in cache
                try await stateCache.fetchStates(for: [entityId])
                if await stateCache.getState(entityId) != nil {
                    matched.append((entityId, options))
                }
                continue
            }

            // Domain-based rule
            guard let domain = rule.domain else { continue }

            // Skip integration-based rules (can't resolve from template)
            if rule.integration != nil { continue }

            let domainEntities = try await templateService.searchEntities(domain: domain)

            // Fetch label entities if rule has a label filter
            let labelEntities: Set<String>?
            if let label = rule.label {
                labelEntities = try await templateService.fetchEntitiesWithLabel(label)
            } else {
                labelEntities = nil
            }

            for entity in domainEntities {
                let entityId = entity.entityId

                // Skip already matched
                if matched.contains(where: { $0.0 == entityId }) { continue }

                // Filter by label
                if let labelEntities = labelEntities, !labelEntities.contains(entityId) {
                    continue
                }

                // Apply not-conditions
                if let notFilter = rule.not, shouldExclude(entity: entity, notFilter: notFilter, templateService: templateService) {
                    continue
                }

                // Check attribute matches
                if let attrs = rule.attributes, !matchesAttributes(entity: entity, required: attrs) {
                    continue
                }

                let options = rule.options ?? AutoEntitiesOptions()
                matched.append((entityId, options))

                // Cache the entity state
                await stateCache.set(entityId, state: EntityState(
                    entityId: entityId,
                    state: entity.state,
                    name: entity.name,
                    icon: entity.icon ?? "",
                    deviceClass: entity.attributes?.deviceClass ?? ""
                ))
            }
        }

        // Deduplicate
        var seen: Set<String> = []
        var unique: [(String, AutoEntitiesOptions)] = []
        for (entityId, options) in matched {
            if !seen.contains(entityId) {
                seen.insert(entityId)
                unique.append((entityId, options))
            }
        }

        return unique
    }

    private func shouldExclude(
        entity: EntitySearchResult,
        notFilter: AutoEntitiesNot,
        templateService: TemplateService
    ) -> Bool {
        guard let orConditions = notFilter.or else { return false }

        for condition in orConditions {
            if let requiredState = condition.state, entity.state == requiredState {
                return true
            }
            // Note: label-based exclusions require async and are handled separately
            // For synchronous check, we skip label conditions here
        }
        return false
    }

    private func matchesAttributes(
        entity: EntitySearchResult,
        required: [String: AnyCodable]
    ) -> Bool {
        let entityAttrs = entity.attributes

        for (attrName, attrValue) in required {
            let expected = attrValue.stringValue.lowercased()
            let actual: String

            switch attrName {
            case "device_class":
                actual = (entityAttrs?.deviceClass ?? "").lowercased()
            case "friendly_name":
                actual = (entityAttrs?.friendlyName ?? "").lowercased()
            case "known":
                actual = (entityAttrs?.known ?? "").lowercased()
            default:
                actual = ""
            }

            if actual != expected { return false }
        }

        return true
    }
}
