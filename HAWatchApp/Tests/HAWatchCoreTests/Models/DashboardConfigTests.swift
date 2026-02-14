import Testing
import Foundation
@testable import HAWatchCore

@Suite("DashboardConfig Parsing")
struct DashboardConfigTests {
    @Test("Parse minimal dashboard config")
    func parseMinimal() throws {
        let json = """
        {
            "views": [
                {
                    "title": "Home",
                    "path": "home",
                    "sections": []
                }
            ]
        }
        """

        let data = json.data(using: .utf8)!
        let config = try JSONDecoder().decode(DashboardConfig.self, from: data)

        #expect(config.views.count == 1)
        #expect(config.views[0].title == "Home")
        #expect(config.views[0].path == "home")
    }

    @Test("Parse view with tile card")
    func parseTileCard() throws {
        let json = """
        {
            "views": [{
                "title": "Test",
                "sections": [{
                    "cards": [{
                        "type": "tile",
                        "entity": "light.living_room",
                        "name": "Living Room Light",
                        "icon": "mdi:lightbulb",
                        "grid_options": {"columns": 6}
                    }]
                }]
            }]
        }
        """

        let data = json.data(using: .utf8)!
        let config = try JSONDecoder().decode(DashboardConfig.self, from: data)
        let card = config.views[0].sections![0].cards![0]

        #expect(card.type == "tile")
        #expect(card.entity == "light.living_room")
        #expect(card.name == "Living Room Light")
        #expect(card.icon == "mdi:lightbulb")
        #expect(card.gridOptions?.columns == 6)
    }

    @Test("Parse heading card with badges")
    func parseHeadingCard() throws {
        let json = """
        {
            "views": [{
                "sections": [{
                    "cards": [{
                        "type": "heading",
                        "heading": "Security",
                        "icon": "mdi:shield",
                        "badges": [{
                            "type": "entity",
                            "entity": "alarm_control_panel.home",
                            "show_state": true
                        }]
                    }]
                }]
            }]
        }
        """

        let data = json.data(using: .utf8)!
        let config = try JSONDecoder().decode(DashboardConfig.self, from: data)
        let card = config.views[0].sections![0].cards![0]

        #expect(card.type == "heading")
        #expect(card.heading == "Security")
        #expect(card.badges?.count == 1)
        #expect(card.badges?[0].type == "entity")
    }

    @Test("Parse auto-entities card")
    func parseAutoEntities() throws {
        let json = """
        {
            "views": [{
                "sections": [{
                    "cards": [{
                        "type": "custom:auto-entities",
                        "filter": {
                            "include": [{
                                "domain": "sensor",
                                "label": "temperature",
                                "attributes": {"device_class": "temperature"}
                            }]
                        },
                        "card": {"type": "tile"}
                    }]
                }]
            }]
        }
        """

        let data = json.data(using: .utf8)!
        let config = try JSONDecoder().decode(DashboardConfig.self, from: data)
        let card = config.views[0].sections![0].cards![0]

        #expect(card.type == "custom:auto-entities")
        #expect(card.filter?.include?.count == 1)
        #expect(card.filter?.include?[0].domain == "sensor")
        #expect(card.filter?.include?[0].label == "temperature")
    }

    @Test("Parse visibility conditions")
    func parseVisibility() throws {
        let json = """
        {
            "views": [{
                "sections": [{
                    "cards": [{
                        "type": "tile",
                        "entity": "light.test",
                        "visibility": [
                            {"condition": "state", "entity": "input_boolean.show", "state": "on"},
                            {"condition": "numeric_state", "entity": "sensor.temp", "above": 20.0, "below": 30.0}
                        ]
                    }]
                }]
            }]
        }
        """

        let data = json.data(using: .utf8)!
        let config = try JSONDecoder().decode(DashboardConfig.self, from: data)
        let visibility = config.views[0].sections![0].cards![0].visibility!

        #expect(visibility.count == 2)

        if case .state(let entity, let state, _) = visibility[0] {
            #expect(entity == "input_boolean.show")
            #expect(state == "on")
        } else {
            Issue.record("Expected .state condition")
        }

        if case .numericState(let entity, let above, let below) = visibility[1] {
            #expect(entity == "sensor.temp")
            #expect(above == 20.0)
            #expect(below == 30.0)
        } else {
            Issue.record("Expected .numericState condition")
        }
    }

    @Test("Parse mushroom template badge")
    func parseMushroomBadge() throws {
        let json = """
        {
            "views": [{
                "badges": [{
                    "type": "custom:mushroom-template-badge",
                    "entity": "person.john",
                    "content": "{{ states('person.john') }}",
                    "label": "{{ state_attr('person.john', 'friendly_name') }}",
                    "icon": "mdi:account"
                }]
            }]
        }
        """

        let data = json.data(using: .utf8)!
        let config = try JSONDecoder().decode(DashboardConfig.self, from: data)
        let badge = config.views[0].badges![0]

        #expect(badge.type == "custom:mushroom-template-badge")
        #expect(badge.entity == "person.john")
        #expect(badge.content == "{{ states('person.john') }}")
        #expect(badge.icon == "mdi:account")
    }
}
