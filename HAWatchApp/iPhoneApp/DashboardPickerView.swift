import SwiftUI
import HAWatchCore

struct DashboardPickerView: View {
    let serverURL: String
    let accessToken: String
    let onSelect: ((String?) -> Void)?

    @State private var dashboards: [DashboardListItem] = []
    @State private var selectedId: String?
    @State private var isLoading = false

    init(serverURL: String, accessToken: String, onSelect: ((String?) -> Void)? = nil) {
        self.serverURL = serverURL
        self.accessToken = accessToken
        self.onSelect = onSelect
    }

    var body: some View {
        List {
            if isLoading {
                ProgressView("Loading dashboards...")
            } else {
                ForEach(dashboards, id: \.urlPath) { dashboard in
                    Button {
                        selectedId = dashboard.urlPath
                        onSelect?(dashboard.urlPath)
                    } label: {
                        HStack {
                            if let icon = dashboard.icon {
                                Image(systemName: IconMapper.shared.sfSymbolName(for: icon))
                                    .frame(width: 24)
                            }
                            VStack(alignment: .leading) {
                                Text(dashboard.title ?? dashboard.urlPath ?? "Dashboard")
                                    .font(.body)
                                if let path = dashboard.urlPath {
                                    Text(path)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            if selectedId == dashboard.urlPath {
                                Image(systemName: "checkmark")
                                    .foregroundStyle(.blue)
                            }
                        }
                    }
                    .tint(.primary)
                }
            }
        }
        .navigationTitle("Default Dashboard")
        .task { await loadDashboards() }
    }

    private func loadDashboards() async {
        guard let url = URL(string: serverURL) else { return }
        isLoading = true

        let client = HAAPIClient(baseURL: url, token: accessToken)
        dashboards = (try? await client.fetchDashboardList()) ?? []

        // Load current selection from settings
        selectedId = SettingsManager.shared.appSettings.defaultDashboardId

        isLoading = false
    }
}
