/// Formats entity state values for display.
/// Pure function — testable without a Home Assistant connection.
/// Single source of truth for state formatting across all renderers.
public struct StateFormatter: Sendable {
    public static let shared = StateFormatter()

    public init() {}

    /// Format an entity state for display.
    /// - Parameters:
    ///   - entityId: The entity ID (used to determine domain)
    ///   - state: The raw state string
    ///   - deviceClass: Optional device class (for binary_sensor)
    ///   - unit: Optional unit of measurement (for sensor)
    /// - Returns: FormattedState with display text and semantic color
    public func format(
        entityId: String,
        state: String,
        deviceClass: String = "",
        unit: String = ""
    ) -> FormattedState {
        let domain = entityId.split(separator: ".").first.map(String.init) ?? ""

        if state == "unavailable" || state == "unknown" {
            return FormattedState(text: "?", color: .inactive)
        }

        switch domain {
        case "person":
            return formatPerson(state: state)
        case "lock":
            return formatLock(state: state)
        case "cover":
            return formatCover(state: state)
        case "binary_sensor":
            return formatBinarySensor(state: state, deviceClass: deviceClass)
        case "light", "switch", "fan", "input_boolean":
            return formatToggle(state: state)
        case "alarm_control_panel":
            return formatAlarm(state: state)
        case "climate":
            return formatClimate(state: state)
        case "sensor":
            return formatSensor(state: state, unit: unit)
        case "weather":
            return formatWeather(state: state)
        case "image":
            return FormattedState(text: "", color: .primary)
        default:
            return FormattedState(text: state, color: .primary)
        }
    }

    private func formatPerson(state: String) -> FormattedState {
        switch state {
        case "home":
            return FormattedState(text: "Home", color: .positive)
        case "not_home":
            return FormattedState(text: "Away", color: .inactive)
        default:
            return FormattedState(text: state, color: .info)
        }
    }

    private func formatLock(state: String) -> FormattedState {
        switch state {
        case "locked":
            return FormattedState(text: "Locked", color: .positive)
        default:
            return FormattedState(text: "Unlocked", color: .danger)
        }
    }

    private func formatCover(state: String) -> FormattedState {
        switch state {
        case "closed":
            return FormattedState(text: "Closed", color: .positive)
        default:
            return FormattedState(text: state.capitalized, color: .warning)
        }
    }

    private func formatBinarySensor(state: String, deviceClass: String) -> FormattedState {
        switch deviceClass {
        case "door", "window", "garage_door", "opening":
            if state == "on" {
                return FormattedState(text: "Open", color: .warning)
            }
            return FormattedState(text: "Closed", color: .positive)

        case "motion":
            if state == "on" {
                return FormattedState(text: "Motion", color: .warning)
            }
            return FormattedState(text: "Clear", color: .inactive)

        case "occupancy":
            if state == "on" {
                return FormattedState(text: "Occupied", color: .active)
            }
            return FormattedState(text: "Empty", color: .inactive)

        case "connectivity", "plug", "power":
            if state == "on" {
                return FormattedState(text: "Connected", color: .positive)
            }
            return FormattedState(text: "Disconnected", color: .inactive)

        case "battery":
            if state == "on" {
                return FormattedState(text: "Low", color: .danger)
            }
            return FormattedState(text: "OK", color: .positive)

        case "problem":
            if state == "on" {
                return FormattedState(text: "Problem", color: .danger)
            }
            return FormattedState(text: "OK", color: .positive)

        default:
            if state == "on" {
                return FormattedState(text: "On", color: .warning)
            }
            return FormattedState(text: "Off", color: .inactive)
        }
    }

    private func formatToggle(state: String) -> FormattedState {
        if state == "on" {
            return FormattedState(text: "On", color: .active)
        }
        return FormattedState(text: "Off", color: .inactive)
    }

    private func formatAlarm(state: String) -> FormattedState {
        switch state {
        case "disarmed":
            return FormattedState(text: "Disarmed", color: .inactive)
        case "armed_home":
            return FormattedState(text: "Armed home", color: .positive)
        case "armed_away":
            return FormattedState(text: "Armed away", color: .positive)
        case "armed_night":
            return FormattedState(text: "Armed night", color: .positive)
        case "armed_vacation":
            return FormattedState(text: "Armed vacation", color: .positive)
        case "armed_custom_bypass":
            return FormattedState(text: "Armed custom", color: .positive)
        case "triggered":
            return FormattedState(text: "TRIGGERED", color: .danger)
        default:
            return FormattedState(text: state, color: .primary)
        }
    }

    private func formatClimate(state: String) -> FormattedState {
        switch state {
        case "off":
            return FormattedState(text: "Off", color: .inactive)
        case "heat":
            return FormattedState(text: "Heating", color: .heat)
        case "cool":
            return FormattedState(text: "Cooling", color: .cool)
        case "heat_cool", "auto":
            return FormattedState(text: "Auto", color: .info)
        default:
            return FormattedState(text: state.capitalized, color: .primary)
        }
    }

    private func formatSensor(state: String, unit: String) -> FormattedState {
        var displayState = state
        if let val = Double(state) {
            if val == Double(Int(val)) {
                displayState = String(Int(val))
            } else {
                displayState = String(format: "%.1f", val)
            }
        }
        if !unit.isEmpty {
            return FormattedState(text: "\(displayState)\(unit)", color: .primary)
        }
        return FormattedState(text: displayState, color: .primary)
    }

    private func formatWeather(state: String) -> FormattedState {
        return FormattedState(text: formatWeatherCondition(state), color: .info)
    }

    /// Format a weather condition string for display (e.g. "partlycloudy" → "Partly Cloudy").
    public func formatWeatherCondition(_ condition: String) -> String {
        condition
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "partlycloudy", with: "Partly Cloudy")
            .capitalized
    }

    /// Format a temperature value for display (e.g. "21°C", "22.5°F").
    /// - Parameters:
    ///   - rawValue: The raw temperature string from the attribute
    ///   - unit: The unit string (e.g. "°C", "°F")
    /// - Returns: Formatted temperature string, or nil if rawValue is empty
    public func formatTemperature(rawValue: String, unit: String = "°C") -> String? {
        guard !rawValue.isEmpty else { return nil }
        guard let val = Double(rawValue) else { return "\(rawValue)\(unit)" }

        if val == Double(Int(val)) {
            return "\(Int(val))\(unit)"
        } else {
            return "\(String(format: "%.1f", val))\(unit)"
        }
    }
}
