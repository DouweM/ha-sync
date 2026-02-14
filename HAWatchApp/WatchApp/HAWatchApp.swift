import SwiftUI

@main
struct HAWatchApp: App {
    @State private var settings = SettingsManager.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(settings)
        }
    }
}
