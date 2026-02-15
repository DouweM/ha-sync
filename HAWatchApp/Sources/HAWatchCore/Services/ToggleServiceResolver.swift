import Foundation

/// Resolves the correct Home Assistant service call for toggling an entity.
/// Handles domain-specific state patterns (lock/cover/climate) beyond simple on/off.
public struct ToggleServiceResolver: Sendable {
    public static let shared = ToggleServiceResolver()

    public init() {}

    /// Result of resolving a toggle service.
    public struct ResolvedService: Sendable, Equatable {
        public let domain: String
        public let service: String

        public init(domain: String, service: String) {
            self.domain = domain
            self.service = service
        }
    }

    /// Resolve the correct service to call when toggling an entity.
    /// - Parameters:
    ///   - domain: The entity domain (e.g. "light", "lock", "cover")
    ///   - currentState: The current state of the entity
    /// - Returns: The service to call, or nil if the domain is not toggleable
    public func resolveToggleService(domain: String, currentState: String) -> ResolvedService? {
        switch domain {
        case "lock":
            return currentState == "locked"
                ? ResolvedService(domain: "lock", service: "unlock")
                : ResolvedService(domain: "lock", service: "lock")

        case "cover":
            let closedStates: Set<String> = ["closed", "closing"]
            return closedStates.contains(currentState)
                ? ResolvedService(domain: "cover", service: "open_cover")
                : ResolvedService(domain: "cover", service: "close_cover")

        case "climate":
            return currentState == "off"
                ? ResolvedService(domain: "climate", service: "turn_on")
                : ResolvedService(domain: "climate", service: "turn_off")

        case "light", "switch", "fan", "input_boolean", "automation":
            return currentState == "on"
                ? ResolvedService(domain: domain, service: "turn_off")
                : ResolvedService(domain: domain, service: "turn_on")

        case "script", "scene":
            return ResolvedService(domain: domain, service: "turn_on")

        default:
            return nil
        }
    }
}
