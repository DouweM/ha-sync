import SwiftUI
import HAWatchCore
#if os(watchOS)
import WatchKit
import WidgetKit
#endif

@main
struct HAWatchApp: App {
    @State private var settings = SettingsManager.shared
    @State private var deepLinkDashboardId: String?
    @State private var deepLinkViewPath: String?

    init() {
        #if canImport(WatchConnectivity)
        WatchConnectivityManager.shared.activate()
        #endif
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(settings)
                .environment(\.deepLinkDashboardId, deepLinkDashboardId)
                .environment(\.deepLinkViewPath, deepLinkViewPath)
                .onOpenURL { url in
                    handleDeepLink(url)
                }
                #if os(watchOS)
                .task {
                    scheduleBackgroundRefresh()
                }
                #endif
        }
        #if os(watchOS)
        .backgroundTask(.appRefresh) { _ in
            await refreshComplicationData()
            await scheduleBackgroundRefresh()
        }
        #endif
    }

    // MARK: - Deep Linking

    /// Handle deep link URLs:
    /// - `hawatch://dashboard/{dashboardId}/view/{viewPath}`
    /// - `hawatch://dashboard/{dashboardId}`
    /// - `hawatch://entity/{entityId}` (from complications, opens default dashboard)
    private func handleDeepLink(_ url: URL) {
        guard url.scheme == "hawatch" else { return }

        let pathComponents = url.pathComponents.filter { $0 != "/" }

        if pathComponents.count >= 2, pathComponents[0] == "dashboard" {
            deepLinkDashboardId = pathComponents[1]
            if pathComponents.count >= 4, pathComponents[2] == "view" {
                deepLinkViewPath = pathComponents[3]
            } else {
                deepLinkViewPath = nil
            }
        } else if pathComponents.count >= 1, pathComponents[0] == "entity" {
            // Entity deep link from complication — open default dashboard
            deepLinkDashboardId = nil
            deepLinkViewPath = nil
        }
    }

    // MARK: - Background Refresh

    #if os(watchOS)
    private func scheduleBackgroundRefresh() {
        let preferredDate = Date(timeIntervalSinceNow: 15 * 60) // 15 minutes
        WKApplication.shared().scheduleBackgroundRefresh(
            withPreferredDate: preferredDate,
            userInfo: nil
        ) { _ in }
    }

    private func refreshComplicationData() async {
        let appSettings = SettingsManager.shared.appSettings
        guard appSettings.isConfigured,
              let baseURL = appSettings.baseURL else { return }

        let entityIds = appSettings.complicationEntities
        guard !entityIds.isEmpty else { return }

        let client = HAAPIClient(baseURL: baseURL, token: appSettings.accessToken)
        let templateService = TemplateService(apiClient: client)

        // Fetch latest states for complication entities
        _ = try? await templateService.fetchEntityStates(entityIds: entityIds)

        // Reload all complication timelines
        WidgetCenter.shared.reloadAllTimelines()
    }
    #endif
}

// MARK: - Deep Link Environment Keys

private struct DeepLinkDashboardIdKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

private struct DeepLinkViewPathKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

// MARK: - Shared API Client Environment Key

private struct APIClientKey: EnvironmentKey {
    static let defaultValue: HAAPIClient? = nil
}

extension EnvironmentValues {
    var deepLinkDashboardId: String? {
        get { self[DeepLinkDashboardIdKey.self] }
        set { self[DeepLinkDashboardIdKey.self] = newValue }
    }

    var deepLinkViewPath: String? {
        get { self[DeepLinkViewPathKey.self] }
        set { self[DeepLinkViewPathKey.self] = newValue }
    }

    var apiClient: HAAPIClient? {
        get { self[APIClientKey.self] }
        set { self[APIClientKey.self] = newValue }
    }
}
