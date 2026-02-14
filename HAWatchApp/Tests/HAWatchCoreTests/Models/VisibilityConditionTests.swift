import Testing
import Foundation
@testable import HAWatchCore

@Suite("VisibilityCondition")
struct VisibilityConditionTests {
    @Test("Decode state condition")
    func decodeState() throws {
        let json = """
        {"condition": "state", "entity": "light.test", "state": "on"}
        """
        let data = json.data(using: .utf8)!
        let condition = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .state(let entity, let state, _) = condition {
            #expect(entity == "light.test")
            #expect(state == "on")
        } else {
            Issue.record("Expected .state")
        }
    }

    @Test("Decode state_not condition")
    func decodeStateNot() throws {
        let json = """
        {"condition": "state", "entity": "light.test", "state_not": "off"}
        """
        let data = json.data(using: .utf8)!
        let condition = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .state(_, _, let stateNot) = condition {
            #expect(stateNot == "off")
        } else {
            Issue.record("Expected .state")
        }
    }

    @Test("Decode numeric_state condition")
    func decodeNumericState() throws {
        let json = """
        {"condition": "numeric_state", "entity": "sensor.temp", "above": 20, "below": 30}
        """
        let data = json.data(using: .utf8)!
        let condition = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .numericState(let entity, let above, let below) = condition {
            #expect(entity == "sensor.temp")
            #expect(above == 20)
            #expect(below == 30)
        } else {
            Issue.record("Expected .numericState")
        }
    }

    @Test("Decode user condition")
    func decodeUser() throws {
        let json = """
        {"condition": "user", "users": ["abc123", "def456"]}
        """
        let data = json.data(using: .utf8)!
        let condition = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .user(let users) = condition {
            #expect(users == ["abc123", "def456"])
        } else {
            Issue.record("Expected .user")
        }
    }

    @Test("Decode screen condition")
    func decodeScreen() throws {
        let json = """
        {"condition": "screen", "media_query": "(max-width: 767px)"}
        """
        let data = json.data(using: .utf8)!
        let condition = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .screen(let mediaQuery) = condition {
            #expect(mediaQuery == "(max-width: 767px)")
        } else {
            Issue.record("Expected .screen")
        }
    }

    @Test("Decode or condition with nested conditions")
    func decodeOr() throws {
        let json = """
        {
            "condition": "or",
            "conditions": [
                {"condition": "state", "entity": "light.a", "state": "on"},
                {"condition": "state", "entity": "light.b", "state": "on"}
            ]
        }
        """
        let data = json.data(using: .utf8)!
        let condition = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .or(let conditions) = condition {
            #expect(conditions.count == 2)
        } else {
            Issue.record("Expected .or")
        }
    }

    @Test("Decode numeric state value as string")
    func decodeStateAsNumber() throws {
        // HA can send state as a number in JSON
        let json = """
        {"condition": "state", "entity": "input_number.x", "state": "42"}
        """
        let data = json.data(using: .utf8)!
        let condition = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .state(_, let state, _) = condition {
            #expect(state == "42")
        } else {
            Issue.record("Expected .state")
        }
    }

    @Test("Roundtrip encode/decode")
    func roundtrip() throws {
        let original = VisibilityCondition.state(entity: "light.test", state: "on", stateNot: nil)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(VisibilityCondition.self, from: data)

        if case .state(let entity, let state, _) = decoded {
            #expect(entity == "light.test")
            #expect(state == "on")
        } else {
            Issue.record("Expected .state")
        }
    }
}
