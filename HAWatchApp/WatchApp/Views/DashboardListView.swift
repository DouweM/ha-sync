import SwiftUI
import HAWatchCore

struct DashboardListView: View {
    @Environment(SettingsManager.self) private var settings
    @Environment(\.deepLinkDashboardId) private var deepLinkDashboardId
    @Environment(\.deepLinkViewPath) private var deepLinkViewPath
    @State private var viewModel = DashboardViewModel()
    @State private var navigationPath = NavigationPath()

    /// The dashboard ID to navigate to (from deep link or default setting)
    private var targetDashboardId: String? {
        deepLinkDashboardId ?? settings.appSettings.defaultDashboardId
    }

    /// The view path to navigate to (from deep link or default setting)
    private var targetViewPath: String? {
        deepLinkViewPath ?? settings.appSettings.defaultViewPath
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
            Group {
                if viewModel.isLoading && viewModel.dashboards.isEmpty && viewModel.renderedViews.isEmpty {
                    ProgressView("Loading...")
                } else if let error = viewModel.error {
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.title2)
                            .foregroundStyle(.yellow)
                        Text(error)
                            .font(.caption)
                            .multilineTextAlignment(.center)
                        Button("Retry") {
                            Task { await viewModel.loadDashboards() }
                        }
                    }
                } else {
                    List {
                        ForEach(viewModel.dashboards, id: \.urlPath) { dashboard in
                            NavigationLink(value: dashboard) {
                                Label {
                                    Text(dashboard.title ?? dashboard.urlPath ?? "Dashboard")
                                } icon: {
                                    EntityIconView(sfSymbolName: IconMapper.shared.sfSymbolName(for: dashboard.icon))
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Dashboards")
            .navigationDestination(for: DashboardListItem.self) { dashboard in
                ViewPageView(viewModel: viewModel, dashboardId: dashboard.urlPath) { newId in
                    navigationPath = NavigationPath()
                    Task {
                        await viewModel.loadDashboard(id: newId)
                        navigationPath.append(newId)
                    }
                }
                .environment(\.apiClient, viewModel.apiClient)
            }
            .navigationDestination(for: String.self) { dashboardId in
                ViewPageView(viewModel: viewModel, dashboardId: dashboardId) { newId in
                    navigationPath = NavigationPath()
                    Task {
                        await viewModel.loadDashboard(id: newId)
                        navigationPath.append(newId)
                    }
                }
                .environment(\.apiClient, viewModel.apiClient)
            }
        }
        .task {
            viewModel.configure(settings: settings.appSettings)

            if let targetId = targetDashboardId {
                // Load dashboard list in background for the picker
                Task { await viewModel.loadDashboards() }
                // Load the target dashboard and auto-navigate
                await viewModel.loadDashboard(id: targetId)
                // Select the target view if specified
                if let viewPath = targetViewPath {
                    viewModel.selectView(byPath: viewPath)
                }
                // Push to the view page
                navigationPath.append(targetId)
            } else {
                await viewModel.loadDashboards()
            }
        }
        .onChange(of: deepLinkDashboardId) { _, newId in
            guard let newId else { return }
            Task {
                // Navigate to deep-linked dashboard
                navigationPath = NavigationPath()
                await viewModel.loadDashboard(id: newId)
                if let viewPath = deepLinkViewPath {
                    viewModel.selectView(byPath: viewPath)
                }
                navigationPath.append(newId)
            }
        }
    }
}
