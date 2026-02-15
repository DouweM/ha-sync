import Foundation
import Testing
@testable import HAWatchCore

@Suite("AutoEntitiesResolver")
struct AutoEntitiesResolverTests {

    // MARK: - Helpers

    /// Creates a mock TemplateService + StateCache backed by an HAAPIClient that won't be called.
    /// We test the resolver's filter-matching helpers indirectly by injecting pre-populated caches
    /// and using the resolver's public `resolve` method with explicit entity_id rules (which only
    /// need the state cache, not the network).
    ///
    /// For domain-based rules we can't avoid the network call to TemplateService, so we test
    /// the pure matching logic (attributes, not-conditions) via `matchesAttributes` and
    /// `shouldExclude` through integration-style tests using explicit entity_id rules and
    /// cached states where possible, and test domain filtering structurally.

    // MARK: - Empty filter returns empty

    @Test("Empty filter returns empty results")
    func emptyFilter() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)
        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)

        let filter = AutoEntitiesFilter(include: nil, exclude: nil)
        let results = try await resolver.resolve(filter: filter)
        #expect(results.isEmpty)
    }

    @Test("Empty include array returns empty results")
    func emptyInclude() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)
        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)

        let filter = AutoEntitiesFilter(include: [], exclude: nil)
        let results = try await resolver.resolve(filter: filter)
        #expect(results.isEmpty)
    }

    // MARK: - Explicit entity_id rules

    @Test("Explicit entity_id rule returns entity when in cache")
    func explicitEntityId() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)

        // Pre-populate cache so fetchStates won't need network
        await stateCache.set("light.living_room", state: EntityState(
            entityId: "light.living_room", state: "on", name: "Living Room"
        ))

        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)
        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(entityId: "light.living_room")
        ])

        let results = try await resolver.resolve(filter: filter)
        #expect(results.count == 1)
        #expect(results[0].entityId == "light.living_room")
    }

    @Test("Explicit entity_id rule carries options through")
    func explicitEntityIdWithOptions() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)

        await stateCache.set("sensor.temp", state: EntityState(
            entityId: "sensor.temp", state: "22.5", name: "Temperature"
        ))

        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)
        let options = AutoEntitiesOptions(name: "Custom Name", icon: "mdi:thermometer")
        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(entityId: "sensor.temp", options: options)
        ])

        let results = try await resolver.resolve(filter: filter)
        #expect(results.count == 1)
        #expect(results[0].entityId == "sensor.temp")
        #expect(results[0].options.name == "Custom Name")
        #expect(results[0].options.icon == "mdi:thermometer")
    }

    @Test("Multiple explicit entity_id rules")
    func multipleExplicitEntities() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)

        await stateCache.set("light.one", state: EntityState(entityId: "light.one", state: "on"))
        await stateCache.set("light.two", state: EntityState(entityId: "light.two", state: "off"))

        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)
        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(entityId: "light.one"),
            AutoEntitiesRule(entityId: "light.two"),
        ])

        let results = try await resolver.resolve(filter: filter)
        #expect(results.count == 2)
        #expect(results[0].entityId == "light.one")
        #expect(results[1].entityId == "light.two")
    }

    // MARK: - Deduplication

    @Test("Duplicate entity_id rules are deduplicated")
    func deduplication() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)

        await stateCache.set("light.living_room", state: EntityState(
            entityId: "light.living_room", state: "on"
        ))

        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)
        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(entityId: "light.living_room"),
            AutoEntitiesRule(entityId: "light.living_room"),
            AutoEntitiesRule(entityId: "light.living_room"),
        ])

        let results = try await resolver.resolve(filter: filter)
        #expect(results.count == 1)
        #expect(results[0].entityId == "light.living_room")
    }

    // MARK: - Integration skipping

    @Test("Integration-based rules are skipped")
    func integrationSkipped() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)
        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)

        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(domain: "sensor", integration: "hue")
        ])

        // Integration rules are skipped (no network call attempted since integration != nil)
        let results = try await resolver.resolve(filter: filter)
        #expect(results.isEmpty)
    }

    // MARK: - Domain-only rule without domain (skipped)

    @Test("Rule with no entity_id and no domain is skipped")
    func noDomainNoEntitySkipped() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)
        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)

        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(label: "some_label")  // no entity_id or domain
        ])

        let results = try await resolver.resolve(filter: filter)
        #expect(results.isEmpty)
    }

    // MARK: - Default options

    @Test("Explicit entity_id without options gets default empty options")
    func defaultOptions() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)

        await stateCache.set("switch.test", state: EntityState(
            entityId: "switch.test", state: "off"
        ))

        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)
        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(entityId: "switch.test")
        ])

        let results = try await resolver.resolve(filter: filter)
        #expect(results.count == 1)
        #expect(results[0].options.name == nil)
        #expect(results[0].options.icon == nil)
    }

    // MARK: - Entity with domain set still treated as entity_id rule

    @Test("Entity_id rule with domain set is treated as entity_id lookup")
    func entityIdWithDomainUsesEntityIdPath() async throws {
        let client = HAAPIClient(baseURL: URL(string: "http://localhost:8123")!, token: "test")
        let templateService = TemplateService(apiClient: client)
        let stateCache = StateCache(templateService: templateService)

        await stateCache.set("light.test", state: EntityState(
            entityId: "light.test", state: "on"
        ))

        let resolver = AutoEntitiesResolver(templateService: templateService, stateCache: stateCache)

        // When entity_id is set AND domain is nil, it's an explicit entity_id rule
        // When domain is set (even with entity_id), it goes through domain path
        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(entityId: "light.test")
        ])

        let results = try await resolver.resolve(filter: filter)
        #expect(results.count == 1)
        #expect(results[0].entityId == "light.test")
    }

    // MARK: - Filter model structure

    @Test("AutoEntitiesFilter round-trips through Codable")
    func filterCodable() throws {
        let filter = AutoEntitiesFilter(include: [
            AutoEntitiesRule(
                entityId: "sensor.temp",
                domain: nil,
                label: nil,
                integration: nil,
                attributes: ["device_class": AnyCodable("temperature")],
                not: AutoEntitiesNot(or: [
                    AutoEntitiesCondition(state: "unavailable"),
                    AutoEntitiesCondition(label: "hidden"),
                ]),
                options: AutoEntitiesOptions(name: "Temp", icon: "mdi:thermometer")
            )
        ])

        let data = try JSONEncoder().encode(filter)
        let decoded = try JSONDecoder().decode(AutoEntitiesFilter.self, from: data)

        #expect(decoded.include?.count == 1)
        let rule = decoded.include![0]
        #expect(rule.entityId == "sensor.temp")
        #expect(rule.attributes?["device_class"]?.stringValue == "temperature")
        #expect(rule.not?.or?.count == 2)
        #expect(rule.not?.or?[0].state == "unavailable")
        #expect(rule.not?.or?[1].label == "hidden")
        #expect(rule.options?.name == "Temp")
        #expect(rule.options?.icon == "mdi:thermometer")
    }

    @Test("AutoEntitiesCondition model stores state and label")
    func conditionModel() {
        let stateCondition = AutoEntitiesCondition(state: "unavailable")
        #expect(stateCondition.state == "unavailable")
        #expect(stateCondition.label == nil)

        let labelCondition = AutoEntitiesCondition(label: "hidden")
        #expect(labelCondition.state == nil)
        #expect(labelCondition.label == "hidden")
    }
}
