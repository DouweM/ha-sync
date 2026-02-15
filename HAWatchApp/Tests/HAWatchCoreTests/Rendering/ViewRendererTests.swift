import Testing
@testable import HAWatchCore

@Suite("ViewRenderer")
struct ViewRendererTests {
    let sectionRenderer = SectionRenderer()
    let badgeRenderer = BadgeRenderer()

    let mockStates: [String: EntityState] = [
        "light.living_room": EntityState(
            entityId: "light.living_room", state: "on", name: "Living Room",
            icon: "mdi:lightbulb"
        ),
        "light.bedroom": EntityState(
            entityId: "light.bedroom", state: "off", name: "Bedroom",
            icon: "mdi:lightbulb"
        ),
        "sensor.temperature": EntityState(
            entityId: "sensor.temperature", state: "23", name: "Temperature",
            unit: "°C", deviceClass: "temperature"
        ),
        "sensor.humidity": EntityState(
            entityId: "sensor.humidity", state: "45", name: "Humidity",
            unit: "%", deviceClass: "humidity"
        ),
        "weather.home": EntityState(
            entityId: "weather.home", state: "sunny", name: "Home Weather",
            attributes: ["temperature": "21"]
        ),
        "person.john": EntityState(
            entityId: "person.john", state: "home", name: "John",
            icon: "mdi:account",
            attributes: ["entity_picture": "/local/john.jpg"]
        ),
        "camera.front_door": EntityState(
            entityId: "camera.front_door", state: "idle", name: "Front Door"
        ),
        "alarm_control_panel.home": EntityState(
            entityId: "alarm_control_panel.home", state: "armed_away",
            name: "Home Alarm"
        ),
    ]

    func stateProvider(_ entityId: String) -> EntityState? {
        mockStates[entityId]
    }

    /// Simulate ViewRenderer.render() synchronously using sub-renderers.
    private func renderView(_ view: ViewConfig) -> RenderedView {
        // Render top-level badges
        let badges: [RenderedBadge] = (view.badges ?? []).compactMap { badge in
            badgeRenderer.renderEntityBadge(
                badge: badge,
                stateProvider: stateProvider
            )
        }

        // Render sections
        let sections: [RenderedSection] = (view.sections ?? []).compactMap { section in
            sectionRenderer.renderSection(
                section: section,
                stateProvider: stateProvider
            )
        }

        return RenderedView(
            title: view.title,
            path: view.path,
            badges: badges,
            sections: sections
        )
    }

    // MARK: - Basic view structure

    @Test("Empty view produces empty RenderedView")
    func emptyView() {
        let view = ViewConfig(title: "Empty", path: "empty")
        let result = renderView(view)
        #expect(result.title == "Empty")
        #expect(result.path == "empty")
        #expect(result.badges.isEmpty)
        #expect(result.sections.isEmpty)
    }

    @Test("View title and path are preserved")
    func viewTitleAndPath() {
        let view = ViewConfig(title: "My Home", path: "home")
        let result = renderView(view)
        #expect(result.title == "My Home")
        #expect(result.path == "home")
    }

    // MARK: - Badges

    @Test("View with entity badges renders them")
    func viewWithBadges() {
        let view = ViewConfig(
            title: "Home",
            path: "home",
            badges: [
                BadgeConfig(type: "entity", entity: "sensor.temperature", name: "Temp"),
                BadgeConfig(type: "entity", entity: "sensor.humidity", name: "Humidity"),
            ]
        )
        let result = renderView(view)
        #expect(result.badges.count == 2)
        #expect(result.badges[0].name == "Temp")
        #expect(result.badges[1].name == "Humidity")
    }

    @Test("View badge with missing entity is skipped")
    func viewBadgeMissingEntity() {
        let view = ViewConfig(
            title: "Home",
            badges: [
                BadgeConfig(type: "entity", entity: "sensor.nonexistent"),
                BadgeConfig(type: "entity", entity: "sensor.temperature", name: "Temp"),
            ]
        )
        let result = renderView(view)
        #expect(result.badges.count == 1)
        #expect(result.badges[0].name == "Temp")
    }

    // MARK: - Sections with tiles

    @Test("View with single section containing tile cards")
    func viewWithTileSection() {
        let view = ViewConfig(
            title: "Lights",
            path: "lights",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "light.living_room"),
                    CardConfig(type: "tile", entity: "light.bedroom"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)
        #expect(result.sections[0].items.count == 2)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.name == "Living Room")
            #expect(tile.state.text == "On")
        } else {
            Issue.record("Expected .card(.tile) for first item")
        }

        if case .card(.tile(let tile)) = result.sections[0].items[1] {
            #expect(tile.name == "Bedroom")
            #expect(tile.state.text == "Off")
        } else {
            Issue.record("Expected .card(.tile) for second item")
        }
    }

    // MARK: - Mixed card types

    @Test("View with headings and tiles produces correct structure")
    func viewWithHeadingsAndTiles() {
        let view = ViewConfig(
            title: "Dashboard",
            path: "dashboard",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "heading", heading: "Lights"),
                    CardConfig(type: "tile", entity: "light.living_room"),
                    CardConfig(type: "heading", heading: "Climate"),
                    CardConfig(type: "tile", entity: "sensor.temperature"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)

        let items = result.sections[0].items
        // Expected: spacing, heading("LIGHTS"), tile(living_room), spacing, heading("CLIMATE"), tile(temperature)
        #expect(items.count == 6)

        if case .heading(let h) = items[1] {
            #expect(h.text == "LIGHTS")
        } else {
            Issue.record("Expected .heading for LIGHTS")
        }

        if case .card(.tile(let tile)) = items[2] {
            #expect(tile.name == "Living Room")
        } else {
            Issue.record("Expected tile after LIGHTS heading")
        }

        if case .heading(let h) = items[4] {
            #expect(h.text == "CLIMATE")
        } else {
            Issue.record("Expected .heading for CLIMATE")
        }

        if case .card(.tile(let tile)) = items[5] {
            #expect(tile.name == "Temperature")
        } else {
            Issue.record("Expected tile after CLIMATE heading")
        }
    }

    // MARK: - Multiple sections

    @Test("View with multiple sections renders all")
    func viewWithMultipleSections() {
        let view = ViewConfig(
            title: "Home",
            path: "home",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "light.living_room"),
                ]),
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "sensor.temperature"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 2)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.entityId == "light.living_room")
        } else {
            Issue.record("Expected tile in first section")
        }

        if case .card(.tile(let tile)) = result.sections[1].items[0] {
            #expect(tile.entityId == "sensor.temperature")
        } else {
            Issue.record("Expected tile in second section")
        }
    }

    // MARK: - Badges and sections together

    @Test("Full view with badges and sections renders correctly")
    func fullViewWithBadgesAndSections() {
        let view = ViewConfig(
            title: "Main Dashboard",
            path: "main",
            badges: [
                BadgeConfig(type: "entity", entity: "sensor.temperature", name: "Temp"),
            ],
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "heading", heading: "People"),
                    CardConfig(type: "tile", entity: "person.john"),
                ]),
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "light.living_room"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.title == "Main Dashboard")
        #expect(result.path == "main")
        #expect(result.badges.count == 1)
        #expect(result.badges[0].name == "Temp")
        #expect(result.sections.count == 2)
    }

    // MARK: - Heading with badges

    @Test("Heading with entity badges is emitted immediately")
    func headingWithEntityBadges() {
        let view = ViewConfig(
            title: "Security",
            sections: [
                SectionConfig(cards: [
                    CardConfig(
                        type: "heading",
                        heading: "Alarm",
                        badges: [
                            BadgeConfig(type: "entity", entity: "alarm_control_panel.home"),
                        ]
                    ),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)

        let items = result.sections[0].items
        // spacing + heading (emitted immediately because it has badges)
        #expect(items.count == 2)

        if case .heading(let h) = items[1] {
            #expect(h.text == "ALARM")
            #expect(h.badges.count == 1)
        } else {
            Issue.record("Expected heading with badges")
        }
    }

    // MARK: - Weather and camera cards

    @Test("View with weather card renders condition")
    func viewWithWeatherCard() {
        let view = ViewConfig(
            title: "Weather",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "weather-forecast", entity: "weather.home"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)

        if case .card(.weather(let weather)) = result.sections[0].items[0] {
            #expect(weather.condition == "Sunny")
            #expect(weather.temperature == "21")
        } else {
            Issue.record("Expected weather card")
        }
    }

    @Test("View with camera card renders snapshot path")
    func viewWithCameraCard() {
        let view = ViewConfig(
            title: "Cameras",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "picture-entity", entity: "camera.front_door"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)

        if case .card(.camera(let cam)) = result.sections[0].items[0] {
            #expect(cam.name == "Front Door")
            #expect(cam.snapshotPath == "api/camera_proxy/camera.front_door")
        } else {
            Issue.record("Expected camera card")
        }
    }

    // MARK: - Entity picture in tile

    @Test("Person tile includes entity_picture URL")
    func personTileWithEntityPicture() {
        let view = ViewConfig(
            title: "People",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "person.john"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.entityPictureURL == "/local/john.jpg")
            #expect(tile.name == "John")
        } else {
            Issue.record("Expected tile with entity picture")
        }
    }

    // MARK: - Half-width tiles

    @Test("Half-width tile in view")
    func halfWidthTileInView() {
        let view = ViewConfig(
            title: "Grid",
            sections: [
                SectionConfig(cards: [
                    CardConfig(
                        type: "tile",
                        entity: "light.living_room",
                        gridOptions: GridOptions(columns: 6)
                    ),
                    CardConfig(
                        type: "tile",
                        entity: "light.bedroom",
                        gridOptions: GridOptions(columns: 6)
                    ),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)
        #expect(result.sections[0].items.count == 2)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.isHalfWidth == true)
        } else {
            Issue.record("Expected half-width tile")
        }
    }

    // MARK: - Visibility filtering

    @Test("Section hidden by visibility is omitted from view")
    func sectionHiddenByVisibility() {
        let view = ViewConfig(
            title: "Conditional",
            sections: [
                SectionConfig(
                    cards: [CardConfig(type: "tile", entity: "light.living_room")],
                    visibility: [.state(entity: "light.living_room", state: "off", stateNot: nil)]
                ),
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "sensor.temperature"),
                ]),
            ]
        )
        let result = renderView(view)
        // First section is hidden (light.living_room is "on", condition requires "off")
        #expect(result.sections.count == 1)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.entityId == "sensor.temperature")
        } else {
            Issue.record("Expected temperature tile in surviving section")
        }
    }

    @Test("Section with all missing entities is omitted")
    func sectionWithMissingEntities() {
        let view = ViewConfig(
            title: "Missing",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "sensor.nonexistent"),
                ]),
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "light.living_room"),
                ]),
            ]
        )
        let result = renderView(view)
        // First section has no renderable cards, so it is omitted
        #expect(result.sections.count == 1)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.entityId == "light.living_room")
        } else {
            Issue.record("Expected living room tile")
        }
    }

    // MARK: - Unsupported card types

    @Test("Navbar card in section is skipped")
    func navbarCardSkipped() {
        let view = ViewConfig(
            title: "Nav",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "custom:navbar-card"),
                    CardConfig(type: "tile", entity: "light.living_room"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)
        // Only the tile should be present
        #expect(result.sections[0].items.count == 1)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.name == "Living Room")
        } else {
            Issue.record("Expected living room tile after skipping navbar")
        }
    }

    // MARK: - Heading without content is dropped

    @Test("Trailing heading without content is not emitted")
    func trailingHeadingDropped() {
        let view = ViewConfig(
            title: "Headings",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "light.living_room"),
                    CardConfig(type: "heading", heading: "Trailing"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)
        // The tile should be present, but the trailing heading should not
        #expect(result.sections[0].items.count == 1)

        if case .card(.tile(_)) = result.sections[0].items[0] {
            // Good -- trailing heading was dropped
        } else {
            Issue.record("Expected only tile, no trailing heading")
        }
    }

    // MARK: - Tile name override

    @Test("Tile with custom name override in view")
    func tileNameOverrideInView() {
        let view = ViewConfig(
            title: "Custom",
            sections: [
                SectionConfig(cards: [
                    CardConfig(type: "tile", entity: "sensor.temperature", name: "Room Temp"),
                ]),
            ]
        )
        let result = renderView(view)
        #expect(result.sections.count == 1)

        if case .card(.tile(let tile)) = result.sections[0].items[0] {
            #expect(tile.name == "Room Temp")
        } else {
            Issue.record("Expected tile with custom name")
        }
    }
}
