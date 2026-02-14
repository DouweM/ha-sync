import Testing
@testable import HAWatchCore

@Suite("VisibilityChecker")
struct VisibilityCheckerTests {
    let checker = VisibilityChecker()

    let mockStates: [String: String] = [
        "light.living_room": "on",
        "light.bedroom": "off",
        "sensor.temperature": "23.5",
        "input_boolean.guest_mode": "on",
        "person.john": "home",
    ]

    func stateProvider(_ entityId: String) -> String? {
        mockStates[entityId]
    }

    // MARK: - No conditions

    @Test("No conditions means visible")
    func noConditions() {
        #expect(checker.isVisible(conditions: nil, stateProvider: stateProvider))
        #expect(checker.isVisible(conditions: [], stateProvider: stateProvider))
    }

    // MARK: - State condition

    @Test("State condition matches")
    func stateMatches() {
        let conditions = [VisibilityCondition.state(entity: "light.living_room", state: "on", stateNot: nil)]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("State condition does not match")
    func stateDoesNotMatch() {
        let conditions = [VisibilityCondition.state(entity: "light.living_room", state: "off", stateNot: nil)]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("State_not condition matches (should hide)")
    func stateNotMatches() {
        let conditions = [VisibilityCondition.state(entity: "light.living_room", state: nil, stateNot: "on")]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("State_not condition does not match (should show)")
    func stateNotDoesNotMatch() {
        let conditions = [VisibilityCondition.state(entity: "light.living_room", state: nil, stateNot: "off")]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("Unknown entity returns unknown state")
    func unknownEntity() {
        let conditions = [VisibilityCondition.state(entity: "light.nonexistent", state: "on", stateNot: nil)]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    // MARK: - Numeric state

    @Test("Numeric state above threshold")
    func numericAbove() {
        let conditions = [VisibilityCondition.numericState(entity: "sensor.temperature", above: 20, below: nil)]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("Numeric state below threshold")
    func numericBelow() {
        let conditions = [VisibilityCondition.numericState(entity: "sensor.temperature", above: nil, below: 30)]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("Numeric state in range")
    func numericInRange() {
        let conditions = [VisibilityCondition.numericState(entity: "sensor.temperature", above: 20, below: 30)]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("Numeric state out of range")
    func numericOutOfRange() {
        let conditions = [VisibilityCondition.numericState(entity: "sensor.temperature", above: 25, below: nil)]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("Numeric state with non-numeric value")
    func numericNonNumeric() {
        let conditions = [VisibilityCondition.numericState(entity: "light.living_room", above: 0, below: nil)]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    // MARK: - User condition

    @Test("User condition matches")
    func userMatches() {
        let conditions = [VisibilityCondition.user(users: ["user123"])]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider, currentUserId: "user123"))
    }

    @Test("User condition does not match")
    func userDoesNotMatch() {
        let conditions = [VisibilityCondition.user(users: ["user123"])]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider, currentUserId: "user456"))
    }

    @Test("User condition with no current user")
    func userNoCurrentUser() {
        let conditions = [VisibilityCondition.user(users: ["user123"])]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider, currentUserId: nil))
    }

    // MARK: - Screen condition (watch = mobile)

    @Test("Screen max-width 767px matches on watch")
    func screenMobile() {
        let conditions = [VisibilityCondition.screen(mediaQuery: "(max-width: 767px)")]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("Screen min-width 768px does not match on watch")
    func screenDesktop() {
        let conditions = [VisibilityCondition.screen(mediaQuery: "(min-width: 768px)")]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    // MARK: - Combinators

    @Test("OR with one matching condition")
    func orOneMatch() {
        let conditions = [
            VisibilityCondition.or(conditions: [
                .state(entity: "light.living_room", state: "off", stateNot: nil),
                .state(entity: "light.living_room", state: "on", stateNot: nil),
            ])
        ]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("OR with no matching conditions")
    func orNoMatch() {
        let conditions = [
            VisibilityCondition.or(conditions: [
                .state(entity: "light.living_room", state: "off", stateNot: nil),
                .state(entity: "light.bedroom", state: "on", stateNot: nil),
            ])
        ]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("AND with all matching conditions")
    func andAllMatch() {
        let conditions = [
            VisibilityCondition.and(conditions: [
                .state(entity: "light.living_room", state: "on", stateNot: nil),
                .state(entity: "input_boolean.guest_mode", state: "on", stateNot: nil),
            ])
        ]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("AND with one failing condition")
    func andOneFail() {
        let conditions = [
            VisibilityCondition.and(conditions: [
                .state(entity: "light.living_room", state: "on", stateNot: nil),
                .state(entity: "light.bedroom", state: "on", stateNot: nil),
            ])
        ]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("NOT inverts result")
    func notInverts() {
        let conditions = [
            VisibilityCondition.not(conditions: [
                .state(entity: "light.bedroom", state: "off", stateNot: nil),
            ])
        ]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("NOT with failing sub-condition shows")
    func notWithFailingSubCondition() {
        let conditions = [
            VisibilityCondition.not(conditions: [
                .state(entity: "light.bedroom", state: "on", stateNot: nil),
            ])
        ]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    // MARK: - Multiple top-level conditions (AND behavior)

    @Test("Multiple top-level conditions all must pass")
    func multipleTopLevel() {
        let conditions: [VisibilityCondition] = [
            .state(entity: "light.living_room", state: "on", stateNot: nil),
            .state(entity: "input_boolean.guest_mode", state: "on", stateNot: nil),
        ]
        #expect(checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }

    @Test("Multiple top-level conditions one fails")
    func multipleTopLevelOneFails() {
        let conditions: [VisibilityCondition] = [
            .state(entity: "light.living_room", state: "on", stateNot: nil),
            .state(entity: "light.bedroom", state: "on", stateNot: nil),
        ]
        #expect(!checker.isVisible(conditions: conditions, stateProvider: stateProvider))
    }
}
