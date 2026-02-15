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

        // In custom-scheme URLs, the first segment is the host (e.g. hawatch://dashboard/... → host = "dashboard")
        let pathComponents = url.pathComponents.filter { $0 != "/" }

        if url.host == "dashboard", pathComponents.count >= 1 {
            deepLinkDashboardId = pathComponents[0]
            if pathComponents.count >= 3, pathComponents[1] == "view" {
                deepLinkViewPath = pathComponents[2]
            } else {
                deepLinkViewPath = nil
            }
        } else if url.host == "entity" {
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
        guard appSettings.isConfigured else { return }

        // Reload all complication timelines — each timeline provider fetches its own data
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
