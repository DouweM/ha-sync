import SwiftUI
import HAWatchCore

struct DashboardListView: View {
    @Environment(SettingsManager.self) private var settings
    @State private var viewModel = DashboardViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.dashboards.isEmpty {
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
                ViewPageView(viewModel: viewModel, dashboardId: dashboard.urlPath)
            }
        }
        .task {
            viewModel.configure(settings: settings.appSettings)

            // If default dashboard is set, navigate directly
            if let defaultId = settings.appSettings.defaultDashboardId {
                await viewModel.loadDashboard(id: defaultId)
            } else {
                await viewModel.loadDashboards()
            }
        }
    }
}
