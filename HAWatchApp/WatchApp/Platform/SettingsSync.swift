import Foundation
import HAWatchCore

/// Manages settings persistence and sync.
/// Uses UserDefaults for local storage, with WatchConnectivity + CloudKit for sync.
@Observable
@MainActor
final class SettingsManager {
    static let shared = SettingsManager()

    private(set) var appSettings: AppSettings

    private let defaults = UserDefaults.standard
    private let settingsKey = "appSettings"

    private init() {
        if let data = UserDefaults.standard.data(forKey: "appSettings"),
           let settings = try? JSONDecoder().decode(AppSettings.self, from: data) {
            self.appSettings = settings

            // Load token from keychain if available
            if let token = KeychainService.load(key: "accessToken") {
                self.appSettings.accessToken = token
            }
        } else {
            self.appSettings = AppSettings()
        }
    }

    func save(_ settings: AppSettings) {
        appSettings = settings

        // Save token to keychain
        if !settings.accessToken.isEmpty {
            try? KeychainService.save(key: "accessToken", value: settings.accessToken)
        }

        // Save non-sensitive settings to UserDefaults
        var settingsForDefaults = settings
        settingsForDefaults.accessToken = "" // Don't store token in UserDefaults
        if let data = try? JSONEncoder().encode(settingsForDefaults) {
            defaults.set(data, forKey: settingsKey)
        }
    }

    func updateDefaultDashboard(id: String?, viewPath: String? = nil) {
        appSettings.defaultDashboardId = id
        appSettings.defaultViewPath = viewPath
        save(appSettings)
    }
}
