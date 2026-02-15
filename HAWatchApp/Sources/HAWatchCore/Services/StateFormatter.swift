/// Formats entity state values for display.
/// Port of render.py:415-506.
public struct StateFormatter: Sendable {
    public static let shared = StateFormatter()

    public init() {}

    /// Format an entity state for display.
    /// - Parameters:
    ///   - entityId: The entity ID (used to determine domain)
    ///   - state: The raw state string
    ///   - deviceClass: Optional device class (for binary_sensor)
    ///   - unit: Optional unit of measurement (for sensor)
    /// - Returns: FormattedState with display text and color
    public func format(
        entityId: String,
        state: String,
        deviceClass: String = "",
        unit: String = ""
    ) -> FormattedState {
        let domain = entityId.split(separator: ".").first.map(String.init) ?? ""

        if state == "unavailable" || state == "unknown" {
            return FormattedState(text: "?", color: .dim)
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
            return FormattedState(text: "Home", color: .green)
        case "not_home":
            return FormattedState(text: "Away", color: .dim)
        default:
            return FormattedState(text: state, color: .cyan)
        }
    }

    private func formatLock(state: String) -> FormattedState {
        switch state {
        case "locked":
            return FormattedState(text: "Locked", color: .green)
        default:
            return FormattedState(text: "Unlocked", color: .red)
        }
    }

    private func formatCover(state: String) -> FormattedState {
        switch state {
        case "closed":
            return FormattedState(text: "Closed", color: .green)
        default:
            return FormattedState(text: state.capitalized, color: .yellow)
        }
    }

    private func formatBinarySensor(state: String, deviceClass: String) -> FormattedState {
        switch deviceClass {
        case "door", "window", "garage_door", "opening":
            if state == "on" {
                return FormattedState(text: "Open", color: .yellow)
            }
            return FormattedState(text: "Closed", color: .green)

        case "motion":
            if state == "on" {
                return FormattedState(text: "Motion", color: .yellow)
            }
            return FormattedState(text: "Clear", color: .dim)

        case "occupancy":
            if state == "on" {
                return FormattedState(text: "Occupied", color: .yellow)
            }
            return FormattedState(text: "Empty", color: .dim)

        case "connectivity", "plug", "power":
            if state == "on" {
                return FormattedState(text: "Connected", color: .green)
            }
            return FormattedState(text: "Disconnected", color: .dim)

        case "battery":
            if state == "on" {
                return FormattedState(text: "Low", color: .red)
            }
            return FormattedState(text: "OK", color: .green)

        case "problem":
            if state == "on" {
                return FormattedState(text: "Problem", color: .red)
            }
            return FormattedState(text: "OK", color: .green)

        default:
            if state == "on" {
                return FormattedState(text: "On", color: .yellow)
            }
            return FormattedState(text: "Off", color: .dim)
        }
    }

    private func formatToggle(state: String) -> FormattedState {
        if state == "on" {
            return FormattedState(text: "On", color: .yellow)
        }
        return FormattedState(text: "Off", color: .dim)
    }

    private func formatAlarm(state: String) -> FormattedState {
        switch state {
        case "disarmed":
            return FormattedState(text: "Disarmed", color: .dim)
        case "armed_home":
            return FormattedState(text: "Armed", color: .green)
        case "armed_away":
            return FormattedState(text: "Armed", color: .green)
        case "triggered":
            return FormattedState(text: "TRIGGERED", color: .red)
        default:
            return FormattedState(text: state, color: .primary)
        }
    }

    private func formatClimate(state: String) -> FormattedState {
        switch state {
        case "off":
            return FormattedState(text: "Off", color: .dim)
        case "heat":
            return FormattedState(text: "Heating", color: .red)
        case "cool":
            return FormattedState(text: "Cooling", color: .blue)
        case "heat_cool", "auto":
            return FormattedState(text: "Auto", color: .cyan)
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
        var display = state
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "partlycloudy", with: "Partly Cloudy")
        display = display.capitalized
        return FormattedState(text: display, color: .cyan)
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
