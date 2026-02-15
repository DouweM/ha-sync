import SwiftUI
import HAWatchCore

@main
struct HAWatchApp: App {
    @State private var settings = SettingsManager.shared
    @State private var deepLinkDashboardId: String?
    @State private var deepLinkViewPath: String?

    init() {
        #if canImport(WatchConnectivity)
        WatchConnectivityManager.shared.activate()
        #endif

        #if os(watchOS)
        scheduleBackgroundRefresh()
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
        }

        #if os(watchOS)
        WKBackgroundTask { task in
            handleBackgroundTask(task)
        }
        #endif
    }

    // MARK: - Deep Linking

    /// Handle `hawatch://dashboard/{dashboardId}/view/{viewPath}` URLs.
    private func handleDeepLink(_ url: URL) {
        guard url.scheme == "hawatch" else { return }

        let pathComponents = url.pathComponents.filter { $0 != "/" }
        // Expected: ["dashboard", "{id}", "view", "{path}"]
        // or: ["dashboard", "{id}"]
        guard pathComponents.count >= 2,
              pathComponents[0] == "dashboard" else { return }

        deepLinkDashboardId = pathComponents[1]

        if pathComponents.count >= 4, pathComponents[2] == "view" {
            deepLinkViewPath = pathComponents[3]
        } else {
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

    private func handleBackgroundTask(_ task: WKBackgroundTask) {
        if let refreshTask = task as? WKApplicationRefreshBackgroundTask {
            Task {
                await refreshComplicationData()
                refreshTask.setTaskCompletedWithSnapshot(false)
                scheduleBackgroundRefresh()
            }
        } else {
            task.setTaskCompletedWithSnapshot(false)
        }
    }

    private func refreshComplicationData() async {
        let appSettings = await SettingsManager.shared.appSettings
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

extension EnvironmentValues {
    var deepLinkDashboardId: String? {
        get { self[DeepLinkDashboardIdKey.self] }
        set { self[DeepLinkDashboardIdKey.self] = newValue }
    }

    var deepLinkViewPath: String? {
        get { self[DeepLinkViewPathKey.self] }
        set { self[DeepLinkViewPathKey.self] = newValue }
    }
}
