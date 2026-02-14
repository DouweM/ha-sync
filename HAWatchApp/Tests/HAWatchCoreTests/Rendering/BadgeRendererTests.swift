import Testing
@testable import HAWatchCore

@Suite("BadgeRenderer")
struct BadgeRendererTests {
    let renderer = BadgeRenderer()

    // MARK: - Entity badges

    @Test("Entity badge with valid state renders correctly")
    func entityBadgeRendersCorrectly() {
        let badge = BadgeConfig(type: "entity", entity: "sensor.temp", name: "Temp")
        let state = EntityState(
            entityId: "sensor.temp",
            state: "22.5",
            name: "Temperature",
            unit: "°C",
            icon: "mdi:thermometer",
            deviceClass: "temperature"
        )
        let result = renderer.renderEntityBadge(
            badge: badge,
            stateProvider: { $0 == "sensor.temp" ? state : nil }
        )
        #expect(result != nil)
        #expect(result?.name == "Temp")
        #expect(result?.entityId == "sensor.temp")
    }

    @Test("Entity badge with missing entity returns nil")
    func entityBadgeMissingEntity() {
        let badge = BadgeConfig(type: "entity", entity: "sensor.missing")
        let result = renderer.renderEntityBadge(
            badge: badge,
            stateProvider: { _ in nil }
        )
        #expect(result == nil)
    }

    @Test("Entity badge with failing visibility returns nil")
    func entityBadgeHiddenByVisibility() {
        let badge = BadgeConfig(
            type: "entity",
            entity: "sensor.temp",
            visibility: [VisibilityCondition.state(entity: "sensor.temp", state: "off", stateNot: nil)]
        )
        let state = EntityState(entityId: "sensor.temp", state: "22.5", name: "Temperature")
        let result = renderer.renderEntityBadge(
            badge: badge,
            stateProvider: { $0 == "sensor.temp" ? state : nil }
        )
        #expect(result == nil)
    }

    // MARK: - Mushroom badges

    @Test("Mushroom badge with content renders")
    func mushroomBadgeWithContent() {
        let badge = BadgeConfig(
            type: "custom:mushroom-template-badge",
            entity: "person.john",
            icon: "mdi:account"
        )
        let result = renderer.renderMushroomBadge(
            badge: badge,
            contentResult: "Home",
            labelResult: nil,
            stateProvider: { _ in nil }
        )
        #expect(result != nil)
        #expect(result?.name == "Home")
        #expect(result?.state?.color == .green)
    }

    @Test("Mushroom badge with 'away' content gets dim color")
    func mushroomBadgeAwayColor() {
        let badge = BadgeConfig(type: "custom:mushroom-template-badge", entity: "person.john")
        let result = renderer.renderMushroomBadge(
            badge: badge,
            contentResult: "Away",
            labelResult: nil,
            stateProvider: { _ in nil }
        )
        #expect(result?.state?.color == .dim)
    }

    @Test("Mushroom badge with only label renders")
    func mushroomBadgeOnlyLabel() {
        let badge = BadgeConfig(type: "custom:mushroom-template-badge", entity: "sensor.temp")
        let result = renderer.renderMushroomBadge(
            badge: badge,
            contentResult: nil,
            labelResult: "22°C",
            stateProvider: { _ in nil }
        )
        #expect(result != nil)
        #expect(result?.name == "22°C")
    }

    @Test("Mushroom badge with empty results returns nil")
    func mushroomBadgeEmptyResults() {
        let badge = BadgeConfig(type: "custom:mushroom-template-badge", entity: "sensor.temp")
        let result = renderer.renderMushroomBadge(
            badge: badge,
            contentResult: nil,
            labelResult: nil,
            stateProvider: { _ in nil }
        )
        #expect(result == nil)
    }
}
