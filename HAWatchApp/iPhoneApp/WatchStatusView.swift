import SwiftUI

struct WatchStatusView: View {
    @Environment(SettingsManager.self) private var settings

    #if canImport(WatchConnectivity)
    private var connectivity: WatchConnectivityManager { .shared }
    #endif

    @State private var isSyncing = false
    @State private var syncResult: String?

    var body: some View {
        #if os(iOS) && canImport(WatchConnectivity)
        statusRows
        if connectivity.isPaired && connectivity.isWatchAppInstalled && connectivity.isReachable {
            syncButton
        }
        #else
        Text("WatchConnectivity not available")
            .foregroundStyle(.secondary)
        #endif
    }

    #if os(iOS) && canImport(WatchConnectivity)
    @ViewBuilder
    private var statusRows: some View {
        Label {
            Text(connectivity.isPaired ? "Watch Paired" : "Watch Not Paired")
        } icon: {
            Image(systemName: connectivity.isPaired ? "applewatch.and.arrow.forward" : "applewatch.slash")
                .foregroundStyle(connectivity.isPaired ? .green : .secondary)
        }

        Label {
            Text(connectivity.isWatchAppInstalled ? "App Installed" : "App Not Installed")
        } icon: {
            Image(systemName: connectivity.isWatchAppInstalled ? "checkmark.circle.fill" : "xmark.circle")
                .foregroundStyle(connectivity.isWatchAppInstalled ? .green : .secondary)
        }

        Label {
            Text(connectivity.isReachable ? "Reachable" : "Not Reachable")
        } icon: {
            Image(systemName: connectivity.isReachable ? "antenna.radiowaves.left.and.right" : "antenna.radiowaves.left.and.right.slash")
                .foregroundStyle(connectivity.isReachable ? .green : .secondary)
        }
    }

    @ViewBuilder
    private var syncButton: some View {
        Button {
            syncToWatch()
        } label: {
            HStack {
                Label("Sync to Watch", systemImage: "arrow.triangle.2.circlepath")
                Spacer()
                if isSyncing {
                    ProgressView()
                } else if let result = syncResult {
                    Text(result)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .disabled(!connectivity.isPaired || !connectivity.isWatchAppInstalled || isSyncing)
    }

    private func syncToWatch() {
        isSyncing = true
        syncResult = nil

        WatchConnectivityManager.shared.sendSettings(settings.appSettings)

        isSyncing = false
        syncResult = "Sent"
    }
    #endif
}
