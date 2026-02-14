/// Evaluates visibility conditions against cached entity state.
/// Port of render.py:332-391.
/// On watchOS, treat screen as mobile (max-width: 767px matches).
public struct VisibilityChecker: Sendable {
    public init() {}

    /// Check if a list of visibility conditions are all met.
    /// - Parameters:
    ///   - conditions: The visibility conditions to evaluate
    ///   - stateProvider: Closure to look up entity state by ID
    ///   - currentUserId: The current HA user ID (for user conditions)
    /// - Returns: true if visible (all conditions pass)
    public func isVisible(
        conditions: [VisibilityCondition]?,
        stateProvider: (String) -> String?,
        currentUserId: String? = nil
    ) -> Bool {
        guard let conditions = conditions, !conditions.isEmpty else {
            return true
        }

        for condition in conditions {
            if !evaluateCondition(condition, stateProvider: stateProvider, currentUserId: currentUserId) {
                return false
            }
        }
        return true
    }

    private func evaluateCondition(
        _ condition: VisibilityCondition,
        stateProvider: (String) -> String?,
        currentUserId: String?
    ) -> Bool {
        switch condition {
        case .state(let entity, let requiredState, let stateNot):
            guard !entity.isEmpty else { return false }
            let currentState = stateProvider(entity) ?? "unknown"

            if let required = requiredState, currentState != required {
                return false
            }
            if let notState = stateNot, currentState == notState {
                return false
            }
            return true

        case .numericState(let entity, let above, let below):
            guard !entity.isEmpty else { return false }
            let currentState = stateProvider(entity) ?? ""
            guard let value = Double(currentState) else { return false }

            if let above = above, value <= above {
                return false
            }
            if let below = below, value >= below {
                return false
            }
            return true

        case .user(let users):
            guard let userId = currentUserId else { return false }
            return users.contains(userId)

        case .screen(let mediaQuery):
            // Watch is mobile: max-width: 767px matches, min-width: 768px doesn't
            if mediaQuery.contains("max-width: 767px") {
                return true  // Watch IS small screen
            }
            if mediaQuery.contains("min-width: 768px") {
                return false  // Watch is NOT large screen
            }
            return true

        case .or(let conditions):
            return conditions.contains { sub in
                evaluateCondition(sub, stateProvider: stateProvider, currentUserId: currentUserId)
            }

        case .and(let conditions):
            return conditions.allSatisfy { sub in
                evaluateCondition(sub, stateProvider: stateProvider, currentUserId: currentUserId)
            }

        case .not(let conditions):
            return !conditions.allSatisfy { sub in
                evaluateCondition(sub, stateProvider: stateProvider, currentUserId: currentUserId)
            }
        }
    }
}
