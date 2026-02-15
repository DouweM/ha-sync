import AppIntents
import WidgetKit
import SwiftUI
import HAWatchCore

struct ToggleEntityIntent: AppIntent, ControlConfigurationIntent {
    static var title: LocalizedStringResource = "Toggle Entity"
    static var description = IntentDescription("Toggle a Home Assistant entity")

    @Parameter(title: "Entity ID")
    var entityId: String?

    @Parameter(title: "Entity Name")
    var entityName: String?

    init() {}

    init(entityId: String, entityName: String? = nil) {
        self.entityId = entityId
        self.entityName = entityName
    }

    @MainActor
    private func getSettings() -> (baseURL: URL, token: String)? {
        guard let baseURL = SettingsManager.shared.appSettings.baseURL else { return nil }
        return (baseURL, SettingsManager.shared.appSettings.accessToken)
    }

    func perform() async throws -> some IntentResult {
        guard let entityId = entityId,
              let settings = await getSettings()
        else {
            return .result()
        }

        let client = HAAPIClient(
            baseURL: settings.baseURL,
            token: settings.token
        )

        let domain = entityId.split(separator: ".").first.map(String.init) ?? ""
        let template = "{{ states('\(entityId)') }}"
        let currentState = try await client.renderTemplate(template)

        let service = currentState.trimmingCharacters(in: .whitespacesAndNewlines) == "on"
            ? "turn_off"
            : "turn_on"

        try await client.callService(
            domain: domain,
            service: service,
            entityId: entityId
        )

        return .result()
    }
}

struct ControlToggleWidget: ControlWidget {
    var body: some ControlWidgetConfiguration {
        AppIntentControlConfiguration(
            kind: "ControlToggle",
            intent: ToggleEntityIntent.self
        ) { configuration in
            ControlWidgetButton(action: configuration) {
                let name = configuration.entityName ?? configuration.entityId ?? "Entity"
                let icon = iconForEntity(configuration.entityId)
                Label(name, systemImage: icon)
            }
        }
        .displayName("Toggle Entity")
        .description("Quick toggle a Home Assistant entity")
    }

    private func iconForEntity(_ entityId: String?) -> String {
        guard let entityId else { return "power" }
        let domain = entityId.split(separator: ".").first.map(String.init) ?? ""
        switch domain {
        case "light": return "lightbulb.fill"
        case "switch": return "switch.2"
        case "fan": return "fan.fill"
        case "lock": return "lock.fill"
        case "cover": return "blinds.vertical.closed"
        case "climate": return "thermometer.medium"
        case "automation": return "gearshape.2.fill"
        case "script": return "scroll.fill"
        case "scene": return "theatermasks.fill"
        case "input_boolean": return "togglepower"
        default: return "power"
        }
    }
}
