public struct FormattedState: Sendable, Equatable {
    public var text: String
    public var color: SemanticColor

    public init(text: String, color: SemanticColor = .primary) {
        self.text = text
        self.color = color
    }
}

/// Format-agnostic semantic color for entity states.
///
/// Each renderer maps these to its own presentation colors:
/// - SwiftUI: `.positive` → `.green`, `.danger` → `.red`, etc.
/// - Rich CLI: `.positive` → "green", `.warning` → "bold yellow", etc.
/// - SwiftBar: `.positive` → "#4CD964", `.danger` → "#FF3B30", etc.
public enum SemanticColor: String, Codable, Sendable, Equatable {
    /// Default / no emphasis
    case primary
    /// Secondary text
    case secondary
    /// Off, away, disconnected, disarmed, empty, clear
    case inactive
    /// Home, locked, closed, connected, OK, armed
    case positive
    /// On (lights/switches/fans), occupied
    case active
    /// Open (doors/windows), motion
    case warning
    /// Unlocked, triggered, low battery, problem
    case danger
    /// Named zones, weather conditions, auto climate
    case info
    /// Heating
    case heat
    /// Cooling
    case cool

    /// Whether this is an emphasized/active state color
    public var isActive: Bool {
        switch self {
        case .positive, .active, .warning, .danger, .info, .heat, .cool:
            return true
        case .primary, .secondary, .inactive:
            return false
        }
    }
}
