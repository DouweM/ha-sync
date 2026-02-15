#if canImport(WatchConnectivity)
import WatchConnectivity
import HAWatchCore

/// Manages WatchConnectivity session for settings transfer between iPhone and Watch.
/// On watchOS: receives settings from iPhone.
/// On iOS: sends settings to Watch.
final class WatchConnectivityManager: NSObject, WCSessionDelegate {
    static let shared = WatchConnectivityManager()

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

    // MARK: - WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        // Session activated
    }

    #if os(iOS)
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) {
        // Re-activate for subsequent device connections
        WCSession.default.activate()
    }
    #endif

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        Task { @MainActor in
            SettingsManager.shared.applyReceivedSettings(userInfo)
        }
    }
}
#endif
