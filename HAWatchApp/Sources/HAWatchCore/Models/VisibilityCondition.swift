import Foundation

public enum VisibilityCondition: Codable, Sendable {
    case state(entity: String, state: String?, stateNot: String?)
    case numericState(entity: String, above: Double?, below: Double?)
    case user(users: [String])
    case screen(mediaQuery: String)
    case or(conditions: [VisibilityCondition])
    case and(conditions: [VisibilityCondition])
    case not(conditions: [VisibilityCondition])

    enum CodingKeys: String, CodingKey {
        case condition, entity, state
        case stateNot = "state_not"
        case above, below, users
        case mediaQuery = "media_query"
        case conditions
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let condition = try container.decode(String.self, forKey: .condition)

        switch condition {
        case "state":
            let entity = try container.decode(String.self, forKey: .entity)
            let state = try container.decodeIfPresent(FlexibleString.self, forKey: .state)?.value
            let stateNot = try container.decodeIfPresent(FlexibleString.self, forKey: .stateNot)?.value
            self = .state(entity: entity, state: state, stateNot: stateNot)

        case "numeric_state":
            let entity = try container.decode(String.self, forKey: .entity)
            let above = try container.decodeIfPresent(Double.self, forKey: .above)
            let below = try container.decodeIfPresent(Double.self, forKey: .below)
            self = .numericState(entity: entity, above: above, below: below)

        case "user":
            let users = try container.decode([String].self, forKey: .users)
            self = .user(users: users)

        case "screen":
            let mediaQuery = try container.decodeIfPresent(String.self, forKey: .mediaQuery) ?? ""
            self = .screen(mediaQuery: mediaQuery)

        case "or":
            let conditions = try container.decode([VisibilityCondition].self, forKey: .conditions)
            self = .or(conditions: conditions)

        case "and":
            let conditions = try container.decode([VisibilityCondition].self, forKey: .conditions)
            self = .and(conditions: conditions)

        case "not":
            let conditions = try container.decode([VisibilityCondition].self, forKey: .conditions)
            self = .not(conditions: conditions)

        default:
            self = .state(entity: "", state: nil, stateNot: nil)
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)

        switch self {
        case .state(let entity, let state, let stateNot):
            try container.encode("state", forKey: .condition)
            try container.encode(entity, forKey: .entity)
            try container.encodeIfPresent(state, forKey: .state)
            try container.encodeIfPresent(stateNot, forKey: .stateNot)

        case .numericState(let entity, let above, let below):
            try container.encode("numeric_state", forKey: .condition)
            try container.encode(entity, forKey: .entity)
            try container.encodeIfPresent(above, forKey: .above)
            try container.encodeIfPresent(below, forKey: .below)

        case .user(let users):
            try container.encode("user", forKey: .condition)
            try container.encode(users, forKey: .users)

        case .screen(let mediaQuery):
            try container.encode("screen", forKey: .condition)
            try container.encode(mediaQuery, forKey: .mediaQuery)

        case .or(let conditions):
            try container.encode("or", forKey: .condition)
            try container.encode(conditions, forKey: .conditions)

        case .and(let conditions):
            try container.encode("and", forKey: .condition)
            try container.encode(conditions, forKey: .conditions)

        case .not(let conditions):
            try container.encode("not", forKey: .condition)
            try container.encode(conditions, forKey: .conditions)
        }
    }
}

/// Helper to decode state values that might be string or number in JSON
private struct FlexibleString: Codable {
    let value: String

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let s = try? container.decode(String.self) {
            value = s
        } else if let i = try? container.decode(Int.self) {
            value = String(i)
        } else if let d = try? container.decode(Double.self) {
            value = String(d)
        } else if let b = try? container.decode(Bool.self) {
            value = String(b)
        } else {
            value = ""
        }
    }
}
