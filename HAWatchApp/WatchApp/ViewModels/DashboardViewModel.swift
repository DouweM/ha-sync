import SwiftUI
import HAWatchCore

@Observable
@MainActor
final class DashboardViewModel {
    var dashboards: [DashboardListItem] = []
    var currentConfig: DashboardConfig?
    var renderedViews: [RenderedView] = []
    var selectedViewIndex: Int = 0
    var isLoading = false
    var error: String?

    private var apiClient: HAAPIClient?
    private var viewRenderer: ViewRenderer?
    private var pollingTask: Task<Void, Never>?

    func configure(settings: AppSettings) {
        guard let baseURL = settings.baseURL else { return }
        let client = HAAPIClient(baseURL: baseURL, token: settings.accessToken)
        self.apiClient = client
        self.viewRenderer = ViewRenderer(apiClient: client)
    }

    func loadDashboards() async {
        guard let client = apiClient else { return }
        isLoading = true
        error = nil

        do {
            dashboards = try await client.fetchDashboardList()
        } catch {
            self.error = "Failed to load dashboards: \(error.localizedDescription)"
        }

        isLoading = false
    }

    func loadDashboard(id: String?) async {
        guard let client = apiClient else { return }
        isLoading = true
        error = nil

        do {
            let config = try await client.fetchDashboardConfig(dashboardId: id)
            self.currentConfig = config

            // Render all views
            var rendered: [RenderedView] = []
            if let renderer = viewRenderer {
                for view in config.views {
                    let rv = try await renderer.render(view: view)
                    rendered.append(rv)
                }
            }
            self.renderedViews = rendered
        } catch {
            self.error = "Failed to load dashboard: \(error.localizedDescription)"
        }

        isLoading = false
    }

    func startPolling(interval: TimeInterval = 30) {
        stopPolling()
        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(interval))
                guard !Task.isCancelled else { break }
                try? await self?.viewRenderer?.refreshStates()
                // Re-render current view
                if let self = self,
                   let config = self.currentConfig,
                   self.selectedViewIndex < config.views.count,
                   let renderer = self.viewRenderer {
                    let view = config.views[self.selectedViewIndex]
                    if let rv = try? await renderer.render(view: view) {
                        self.renderedViews[self.selectedViewIndex] = rv
                    }
                }
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }
}
