import SwiftUI
import HAWatchCore

struct DashboardPickerView: View {
    let serverURL: String
    let accessToken: String

    @State private var dashboards: [DashboardListItem] = []
    @State private var selectedId: String?
    @State private var isLoading = false

    var body: some View {
        List {
            if isLoading {
                ProgressView("Loading dashboards...")
            } else {
                ForEach(dashboards, id: \.urlPath) { dashboard in
                    Button {
                        selectedId = dashboard.urlPath
                        // Save as default and sync to watch
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

        isLoading = false
    }
}
