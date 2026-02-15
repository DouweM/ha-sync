import AppIntents
import WidgetKit
import SwiftUI
import HAWatchCore

struct ToggleEntityIntent: AppIntent {
    static var title: LocalizedStringResource = "Toggle Entity"
    static var description = IntentDescription("Toggle a Home Assistant entity")

    @Parameter(title: "Entity ID")
    var entityId: String?

    init() {}

    init(entityId: String) {
        self.entityId = entityId
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
        StaticControlConfiguration(kind: "ControlToggle") {
            ControlWidgetButton(action: ToggleEntityIntent()) {
                Label("Toggle", systemImage: "power")
            }
        }
        .displayName("Toggle Entity")
        .description("Quick toggle a Home Assistant entity")
    }
}
