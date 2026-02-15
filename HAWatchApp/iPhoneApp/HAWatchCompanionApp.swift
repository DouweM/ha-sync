import SwiftUI

@main
struct HAWatchCompanionApp: App {
    @State private var settings = SettingsManager.shared

    init() {
        #if canImport(WatchConnectivity)
        WatchConnectivityManager.shared.activate()
        #endif
    }

    var body: some Scene {
        WindowGroup {
            CompanionRootView()
                .environment(settings)
        }
    }
}
