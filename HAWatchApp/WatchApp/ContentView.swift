import SwiftUI
import HAWatchCore

struct ContentView: View {
    @Environment(SettingsManager.self) private var settings

    var body: some View {
        if settings.appSettings.isConfigured {
            DashboardListView()
        } else {
            WatchSettingsView()
        }
    }
}
