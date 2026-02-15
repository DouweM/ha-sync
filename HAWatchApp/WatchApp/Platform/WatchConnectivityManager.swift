#if canImport(WatchConnectivity)
import WatchConnectivity
import HAWatchCore

/// Manages WatchConnectivity session for settings transfer between iPhone and Watch.
/// On watchOS: receives settings from iPhone.
/// On iOS: sends settings to Watch.
@Observable
@MainActor
final class WatchConnectivityManager: NSObject, WCSessionDelegate {
    static let shared = WatchConnectivityManager()

    #if os(iOS)
    private(set) var isPaired = false
    private(set) var isWatchAppInstalled = false
    private(set) var isReachable = false
    #endif

    private override init() {
        super.init()
    }

    /// Activate the WatchConnectivity session. Call early in app lifecycle.
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    /// Send settings to the paired device via `transferUserInfo` (guaranteed delivery).
    func sendSettings(_ settings: AppSettings) {
        guard WCSession.default.activationState == .activated else { return }

        #if os(iOS)
        guard WCSession.default.isPaired, WCSession.default.isWatchAppInstalled else { return }
        #endif

        var info: [String: Any] = [
            "serverURL": settings.serverURL,
            "accessToken": settings.accessToken,
        ]
        if let dashboardId = settings.defaultDashboardId {
            info["defaultDashboardId"] = dashboardId
        }
        if let viewPath = settings.defaultViewPath {
            info["defaultViewPath"] = viewPath
        }
        if !settings.complicationEntities.isEmpty {
            info["complicationEntities"] = settings.complicationEntities
        }

        WCSession.default.transferUserInfo(info)
    }

    #if os(iOS)
    private func updateWatchState(_ session: WCSession) {
        isPaired = session.isPaired
        isWatchAppInstalled = session.isWatchAppInstalled
        isReachable = session.isReachable
    }
    #endif

    // MARK: - WCSessionDelegate

    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        #if os(iOS)
        let paired = session.isPaired
        let installed = session.isWatchAppInstalled
        let reachable = session.isReachable
        Task { @MainActor in
            self.isPaired = paired
            self.isWatchAppInstalled = installed
            self.isReachable = reachable
        }
        #endif
    }

    #if os(iOS)
    nonisolated func sessionDidBecomeInactive(_ session: WCSession) {}
    nonisolated func sessionDidDeactivate(_ session: WCSession) {
        // Re-activate for subsequent device connections
        WCSession.default.activate()
    }

    nonisolated func sessionWatchStateDidChange(_ session: WCSession) {
        let paired = session.isPaired
        let installed = session.isWatchAppInstalled
        let reachable = session.isReachable
        Task { @MainActor in
            self.isPaired = paired
            self.isWatchAppInstalled = installed
            self.isReachable = reachable
        }
    }

    nonisolated func sessionReachabilityDidChange(_ session: WCSession) {
        let reachable = session.isReachable
        Task { @MainActor in
            self.isReachable = reachable
        }
    }
    #endif

    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        nonisolated(unsafe) let info = userInfo
        Task { @MainActor in
            SettingsManager.shared.applyReceivedSettings(info)
        }
    }
}
#endif
