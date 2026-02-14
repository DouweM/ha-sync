public struct FormattedState: Sendable, Equatable {
    public var text: String
    public var color: StateColor

    public init(text: String, color: StateColor = .primary) {
        self.text = text
        self.color = color
    }
}

public enum StateColor: String, Codable, Sendable, Equatable {
    case primary
    case secondary
    case green
    case red
    case yellow
    case blue
    case cyan
    case orange
    case dim

    /// Whether this is a "bright" active state color
    public var isActive: Bool {
        switch self {
        case .green, .red, .yellow, .blue, .cyan, .orange:
            return true
        case .primary, .secondary, .dim:
            return false
        }
    }
}
