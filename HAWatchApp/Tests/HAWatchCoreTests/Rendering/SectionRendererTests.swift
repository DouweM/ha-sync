import Testing
@testable import HAWatchCore

@Suite("SectionRenderer")
struct SectionRendererTests {
    let renderer = SectionRenderer()

    let mockStates: [String: EntityState] = [
        "light.living_room": EntityState(entityId: "light.living_room", state: "on", name: "Living Room", icon: "mdi:lightbulb"),
        "light.bedroom": EntityState(entityId: "light.bedroom", state: "off", name: "Bedroom", icon: "mdi:lightbulb"),
        "sensor.temperature": EntityState(entityId: "sensor.temperature", state: "23", name: "Temperature", unit: "°C", deviceClass: "temperature"),
        "alarm_control_panel.home": EntityState(entityId: "alarm_control_panel.home", state: "armed_away", name: "Home Alarm"),
    ]

    func stateProvider(_ entityId: String) -> EntityState? {
        mockStates[entityId]
    }

    // MARK: - Basic rendering

    @Test("Empty section returns nil")
    func emptySection() {
        let section = SectionConfig(cards: [])
        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result == nil)
    }

    @Test("Section with single tile card")
    func singleTile() {
        let section = SectionConfig(cards: [
            CardConfig(type: "tile", entity: "light.living_room"),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result != nil)
        #expect(result!.items.count == 1)

        if case .card(.tile(let tile)) = result!.items[0] {
            #expect(tile.name == "Living Room")
            #expect(tile.state.text == "On")
            #expect(tile.state.color == .yellow)
        } else {
            Issue.record("Expected .card(.tile)")
        }
    }

    // MARK: - Pending heading logic

    @Test("Heading without badges is held until content follows")
    func pendingHeading() {
        let section = SectionConfig(cards: [
            CardConfig(type: "heading", heading: "Lights"),
            CardConfig(type: "tile", entity: "light.living_room"),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result != nil)
        // Should have: spacing, heading, tile
        #expect(result!.items.count == 3)

        if case .spacing = result!.items[0] {} else {
            Issue.record("Expected .spacing")
        }
        if case .heading(let h) = result!.items[1] {
            #expect(h.text == "LIGHTS")
        } else {
            Issue.record("Expected .heading")
        }
        if case .card(.tile(_)) = result!.items[2] {} else {
            Issue.record("Expected .card(.tile)")
        }
    }

    @Test("Heading without content is not emitted")
    func pendingHeadingNoContent() {
        let section = SectionConfig(cards: [
            CardConfig(type: "heading", heading: "Empty Section"),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result == nil)
    }

    @Test("Heading with badges is emitted immediately")
    func headingWithBadges() {
        let section = SectionConfig(cards: [
            CardConfig(
                type: "heading",
                heading: "Security",
                badges: [
                    BadgeConfig(type: "entity", entity: "alarm_control_panel.home"),
                ]
            ),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result != nil)
        // spacing + heading
        #expect(result!.items.count == 2)

        if case .heading(let h) = result!.items[1] {
            #expect(h.text == "SECURITY")
            #expect(h.badges.count == 1)
        } else {
            Issue.record("Expected .heading")
        }
    }

    @Test("Two consecutive headings: first emitted when second arrives")
    func twoConsecutiveHeadings() {
        let section = SectionConfig(cards: [
            CardConfig(type: "heading", heading: "First"),
            CardConfig(type: "heading", heading: "Second"),
            CardConfig(type: "tile", entity: "light.living_room"),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result != nil)

        // First heading is emitted when second heading arrives
        // Then second heading is emitted when tile arrives
        var headingCount = 0
        for item in result!.items {
            if case .heading(_) = item { headingCount += 1 }
        }
        #expect(headingCount == 2)
    }

    // MARK: - Visibility

    @Test("Section with failing visibility is hidden")
    func sectionHidden() {
        let section = SectionConfig(
            cards: [CardConfig(type: "tile", entity: "light.living_room")],
            visibility: [.state(entity: "light.living_room", state: "off", stateNot: nil)]
        )

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result == nil)
    }

    @Test("Card with failing visibility is skipped")
    func cardHidden() {
        let section = SectionConfig(cards: [
            CardConfig(
                type: "tile",
                entity: "light.living_room",
                visibility: [.state(entity: "light.living_room", state: "off", stateNot: nil)]
            ),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result == nil)
    }

    // MARK: - Half-width tiles

    @Test("Tile with columns 6 is half-width")
    func halfWidthTile() {
        let section = SectionConfig(cards: [
            CardConfig(
                type: "tile",
                entity: "light.living_room",
                gridOptions: GridOptions(columns: 6)
            ),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result != nil)

        if case .card(.tile(let tile)) = result!.items[0] {
            #expect(tile.isHalfWidth == true)
        } else {
            Issue.record("Expected half-width tile")
        }
    }

    @Test("Tile with columns 12 is full-width")
    func fullWidthTile() {
        let section = SectionConfig(cards: [
            CardConfig(
                type: "tile",
                entity: "light.living_room",
                gridOptions: GridOptions(columns: 12)
            ),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result != nil)

        if case .card(.tile(let tile)) = result!.items[0] {
            #expect(tile.isHalfWidth == false)
        } else {
            Issue.record("Expected full-width tile")
        }
    }

    // MARK: - Heading icon

    @Test("Heading with icon")
    func headingWithIcon() {
        let section = SectionConfig(cards: [
            CardConfig(type: "heading", icon: "mdi:lightbulb", heading: "Lights"),
            CardConfig(type: "tile", entity: "light.living_room"),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result != nil)

        if case .heading(let h) = result!.items[1] {
            #expect(h.iconName == "lightbulb.fill")
        } else {
            Issue.record("Expected .heading with icon")
        }
    }

    // MARK: - Unsupported card types

    @Test("Navbar card is skipped")
    func navbarSkipped() {
        let section = SectionConfig(cards: [
            CardConfig(type: "custom:navbar-card"),
        ])

        let result = renderer.renderSection(section: section, stateProvider: stateProvider)
        #expect(result == nil)
    }
}
