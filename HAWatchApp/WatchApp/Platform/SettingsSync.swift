import Foundation
import HAWatchCore

/// Manages settings persistence and sync.
/// Uses UserDefaults for local storage, Keychain for tokens,
/// WatchConnectivity for iPhone<->Watch transfer, and
/// NSUbiquitousKeyValueStore (CloudKit) for persistent backup.
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

        // Restore from CloudKit if local is empty
        restoreFromCloudKit()
        observeCloudKit()
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

        // Sync non-sensitive settings to CloudKit
        syncToCloudKit(settings)
    }

    func updateDefaultDashboard(id: String?, viewPath: String? = nil) {
        appSettings.defaultDashboardId = id
        appSettings.defaultViewPath = viewPath
        save(appSettings)
    }

    func updateComplicationEntities(_ entities: [String]) {
        appSettings.complicationEntities = entities
        save(appSettings)
    }

    /// Apply settings received from iPhone via WatchConnectivity.
    func applyReceivedSettings(_ info: [String: Any]) {
        if let serverURL = info["serverURL"] as? String {
            appSettings.serverURL = serverURL
        }
        if let token = info["accessToken"] as? String, !token.isEmpty {
            appSettings.accessToken = token
        }
        if let dashboardId = info["defaultDashboardId"] as? String {
            appSettings.defaultDashboardId = dashboardId
        }
        if let viewPath = info["defaultViewPath"] as? String {
            appSettings.defaultViewPath = viewPath
        }
        if let entities = info["complicationEntities"] as? [String] {
            appSettings.complicationEntities = entities
        }
        save(appSettings)
    }

    // MARK: - CloudKit (NSUbiquitousKeyValueStore)

    private func syncToCloudKit(_ settings: AppSettings) {
        #if canImport(UIKit)
        let store = NSUbiquitousKeyValueStore.default
        store.set(settings.serverURL, forKey: "serverURL")
        if let dashboardId = settings.defaultDashboardId {
            store.set(dashboardId, forKey: "defaultDashboardId")
        }
        if let viewPath = settings.defaultViewPath {
            store.set(viewPath, forKey: "defaultViewPath")
        }
        store.set(settings.complicationEntities, forKey: "complicationEntities")
        // Token is NEVER stored in CloudKit - stays in Keychain only
        store.synchronize()
        #endif
    }

    private func restoreFromCloudKit() {
        #if canImport(UIKit)
        guard !appSettings.isConfigured else { return }

        let store = NSUbiquitousKeyValueStore.default
        if let serverURL = store.string(forKey: "serverURL"), !serverURL.isEmpty {
            appSettings.serverURL = serverURL
        }
        if let dashboardId = store.string(forKey: "defaultDashboardId") {
            appSettings.defaultDashboardId = dashboardId
        }
        if let viewPath = store.string(forKey: "defaultViewPath") {
            appSettings.defaultViewPath = viewPath
        }
        if let entities = store.array(forKey: "complicationEntities") as? [String] {
            appSettings.complicationEntities = entities
        }
        #endif
    }

    private func observeCloudKit() {
        #if canImport(UIKit)
        NotificationCenter.default.addObserver(
            forName: NSUbiquitousKeyValueStore.didChangeExternallyNotification,
            object: NSUbiquitousKeyValueStore.default,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.restoreFromCloudKit()
            }
        }
        #endif
    }
}
