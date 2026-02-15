import SwiftUI
import HAWatchCore

struct CompanionSettingsView: View {
    @Environment(SettingsManager.self) private var settings

    @State private var connectionStatus: String?
    @State private var isCheckingConnection = false
    @State private var showDisconnectConfirmation = false

    private var isConfigured: Bool {
        settings.appSettings.isConfigured
    }

    var body: some View {
        NavigationStack {
            Form {
                connectionSection
                if isConfigured {
                    watchAppSection
                    watchSection
                }
                aboutSection
            }
            .navigationTitle("HA Watch")
            .task(id: settings.appSettings.serverURL) {
                await checkConnection()
            }
        }
    }

    // MARK: - Connection

    @ViewBuilder
    private var connectionSection: some View {
        Section("Connection") {
            if isConfigured {
                HStack {
                    Label {
                        VStack(alignment: .leading) {
                            Text(settings.appSettings.serverURL)
                                .font(.body)
                            if let status = connectionStatus {
                                Text(status)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    } icon: {
                        if isCheckingConnection {
                            ProgressView()
                        } else if connectionStatus != nil {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                        } else {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(.orange)
                        }
                    }
                }

                NavigationLink("Edit Connection") {
                    ConnectionFormView()
                }
            } else {
                NavigationLink {
                    ConnectionFormView()
                } label: {
                    Label("Connect to Home Assistant", systemImage: "house.fill")
                }
            }
        }
    }

    // MARK: - Watch App

    @ViewBuilder
    private var watchAppSection: some View {
        Section("Watch App") {
            NavigationLink {
                DefaultViewPickerView()
            } label: {
                HStack {
                    Label("Default View", systemImage: "square.grid.2x2")
                    Spacer()
                    if let title = settings.appSettings.defaultViewTitle ?? settings.appSettings.defaultDashboardId {
                        Text(title)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            NavigationLink {
                ComplicationConfigView()
            } label: {
                HStack {
                    Label("Complications", systemImage: "watchface.applewatch.case")
                    Spacer()
                    let count = settings.appSettings.complicationEntities.count
                    if count > 0 {
                        Text("\(count) entities")
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    // MARK: - Watch

    @ViewBuilder
    private var watchSection: some View {
        Section("Watch") {
            WatchStatusView()
        }
    }

    // MARK: - About

    @ViewBuilder
    private var aboutSection: some View {
        Section("About") {
            HStack {
                Text("Version")
                Spacer()
                Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")
                    .foregroundStyle(.secondary)
            }

            if isConfigured {
                Button("Disconnect", role: .destructive) {
                    showDisconnectConfirmation = true
                }
                .confirmationDialog(
                    "Disconnect from Home Assistant?",
                    isPresented: $showDisconnectConfirmation,
                    titleVisibility: .visible
                ) {
                    Button("Disconnect", role: .destructive) {
                        disconnect()
                    }
                } message: {
                    Text("This will clear your saved connection settings. You can reconnect at any time.")
                }
            }
        }
    }

    // MARK: - Actions

    private func checkConnection() async {
        guard let url = settings.appSettings.baseURL else {
            connectionStatus = nil
            return
        }
        isCheckingConnection = true

        let client = HAAPIClient(baseURL: url, token: settings.appSettings.accessToken)
        do {
            let config = try await client.validateConnection()
            connectionStatus = "Connected to \(config.locationName ?? "Home Assistant")"
        } catch {
            connectionStatus = nil
        }

        isCheckingConnection = false

        // Backfill view title if missing
        if settings.appSettings.defaultDashboardId != nil,
           settings.appSettings.defaultViewTitle == nil {
            if let dashboards = try? await client.fetchDashboardList(),
               let match = dashboards.first(where: { $0.urlPath == settings.appSettings.defaultDashboardId }) {
                settings.updateDefaultView(
                    dashboardId: match.urlPath,
                    viewTitle: match.title,
                    viewPath: settings.appSettings.defaultViewPath
                )
            }
        }
    }

    private func disconnect() {
        connectionStatus = nil
        settings.save(AppSettings())
        KeychainService.delete(key: "accessToken")
    }
}
