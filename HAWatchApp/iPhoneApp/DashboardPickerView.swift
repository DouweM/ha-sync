import SwiftUI
import HAWatchCore

struct DefaultViewPickerView: View {
    @Environment(SettingsManager.self) private var settings
    @Environment(\.dismiss) private var dismiss

    @State private var dashboards: [DashboardListItem] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            ForEach(dashboards, id: \.urlPath) { dashboard in
                NavigationLink {
                    ViewPickerList(
                        dashboard: dashboard,
                        settings: settings,
                        dismiss: dismiss
                    )
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
                        if settings.appSettings.defaultDashboardId == dashboard.urlPath {
                            Image(systemName: "checkmark")
                                .foregroundStyle(.blue)
                        }
                    }
                }
                .tint(.primary)
            }
        }
        .overlay {
            if isLoading {
                ProgressView("Loading dashboards...")
            } else if let error = errorMessage {
                ContentUnavailableView {
                    Label("Connection Failed", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error)
                } actions: {
                    Button("Retry") {
                        Task { await loadDashboards() }
                    }
                }
            } else if dashboards.isEmpty {
                ContentUnavailableView(
                    "No Dashboards",
                    systemImage: "square.grid.2x2.fill",
                    description: Text("No dashboards found on this server.")
                )
            }
        }
        .navigationTitle("Default View")
        .task { await loadDashboards() }
    }

    private func loadDashboards() async {
        guard let url = settings.appSettings.baseURL else {
            errorMessage = "No server URL configured"
            return
        }
        isLoading = true
        errorMessage = nil

        let client = HAAPIClient(baseURL: url, token: settings.appSettings.accessToken)
        do {
            dashboards = try await client.fetchDashboardList()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

// MARK: - View Picker (Level 2)

private struct ViewPickerList: View {
    let dashboard: DashboardListItem
    let settings: SettingsManager
    let dismiss: DismissAction

    @State private var views: [ViewConfig] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    private var dashboardId: String {
        dashboard.urlPath ?? ""
    }

    private var dashboardTitle: String {
        dashboard.title ?? dashboard.urlPath ?? "Dashboard"
    }

    var body: some View {
        List {
            // "First View" option — selects dashboard without a specific view
            Button {
                selectView(path: nil, title: nil)
            } label: {
                HStack {
                    Label("First View (default)", systemImage: "1.square")
                    Spacer()
                    if settings.appSettings.defaultDashboardId == dashboardId,
                       settings.appSettings.defaultViewPath == nil {
                        Image(systemName: "checkmark")
                            .foregroundStyle(.blue)
                    }
                }
            }
            .tint(.primary)

            ForEach(Array(views.enumerated()), id: \.offset) { index, view in
                Button {
                    selectView(path: view.path, title: view.title)
                } label: {
                    HStack {
                        if let icon = view.icon {
                            Image(systemName: IconMapper.shared.sfSymbolName(for: icon))
                                .frame(width: 24)
                        } else {
                            Image(systemName: "rectangle")
                                .frame(width: 24)
                        }
                        VStack(alignment: .leading) {
                            Text(view.title ?? "View \(index + 1)")
                                .font(.body)
                            if let path = view.path {
                                Text(path)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if settings.appSettings.defaultDashboardId == dashboardId,
                           settings.appSettings.defaultViewPath == view.path {
                            Image(systemName: "checkmark")
                                .foregroundStyle(.blue)
                        }
                    }
                }
                .tint(.primary)
            }
        }
        .overlay {
            if isLoading {
                ProgressView("Loading views...")
            } else if let error = errorMessage {
                ContentUnavailableView {
                    Label("Failed to Load", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error)
                } actions: {
                    Button("Retry") {
                        Task { await loadViews() }
                    }
                }
            }
        }
        .navigationTitle(dashboardTitle)
        .task { await loadViews() }
    }

    private func loadViews() async {
        guard let url = settings.appSettings.baseURL else {
            errorMessage = "No server URL configured"
            return
        }
        isLoading = true
        errorMessage = nil

        let client = HAAPIClient(baseURL: url, token: settings.appSettings.accessToken)
        do {
            let config = try await client.fetchDashboardConfig(dashboardId: dashboardId)
            views = config.views
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func selectView(path: String?, title: String?) {
        let viewTitle: String
        if let title {
            viewTitle = "\(dashboardTitle) > \(title)"
        } else {
            viewTitle = dashboardTitle
        }
        settings.updateDefaultView(
            dashboardId: dashboardId,
            viewTitle: viewTitle,
            viewPath: path
        )
        dismiss()
    }
}
