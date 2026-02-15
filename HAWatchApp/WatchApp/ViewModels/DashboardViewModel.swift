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

    enum ConnectionState {
        case connected, disconnected, reconnecting
    }
    var connectionState: ConnectionState = .connected

    /// Track which view indices need re-rendering (set on poll, cleared on render)
    var staleViewIndices: Set<Int> = []

    private(set) var apiClient: HAAPIClient?
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

    /// Select a view by its path (used for deep-linking and default view navigation)
    func selectView(byPath path: String) {
        for (index, view) in renderedViews.enumerated() {
            if view.path == path {
                selectedViewIndex = index
                return
            }
        }
    }

    func startPolling(interval: TimeInterval = 30) {
        stopPolling()
        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(interval))
                guard !Task.isCancelled else { break }
                do {
                    try await self?.viewRenderer?.refreshStates()
                    if let self = self { self.connectionState = .connected }
                } catch {
                    if let self = self { self.connectionState = .disconnected }
                    continue
                }

                guard let self = self,
                      let config = self.currentConfig,
                      let renderer = self.viewRenderer else { continue }

                // Mark all views as stale
                self.staleViewIndices = Set(0..<config.views.count)

                // Re-render the currently visible view immediately
                let currentIndex = self.selectedViewIndex
                if currentIndex < config.views.count {
                    let view = config.views[currentIndex]
                    if let rv = try? await renderer.render(view: view) {
                        self.renderedViews[currentIndex] = rv
                        self.staleViewIndices.remove(currentIndex)
                    }
                }
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    /// Re-render a view if it's marked as stale (called when a view becomes visible)
    func refreshIfStale(viewIndex: Int) async {
        guard staleViewIndices.contains(viewIndex),
              let config = currentConfig,
              viewIndex < config.views.count,
              let renderer = viewRenderer else { return }

        let view = config.views[viewIndex]
        if let rv = try? await renderer.render(view: view) {
            renderedViews[viewIndex] = rv
            staleViewIndices.remove(viewIndex)
        }
    }

    /// Toggle a Home Assistant entity (light, switch, etc.)
    func toggleEntity(entityId: String) async {
        guard let client = apiClient else { return }

        let domain = entityId.split(separator: ".").first.map(String.init) ?? ""

        // Domains that only support turn_on (no toggle)
        let turnOnOnlyDomains: Set<String> = ["script", "scene"]
        // Domains that support toggling
        let toggleableDomains: Set<String> = [
            "light", "switch", "fan", "input_boolean", "lock",
            "cover", "climate", "automation"
        ]

        guard turnOnOnlyDomains.contains(domain) || toggleableDomains.contains(domain) else { return }

        do {
            if turnOnOnlyDomains.contains(domain) {
                try await client.callService(domain: domain, service: "turn_on", entityId: entityId)
            } else {
                // Check current state and toggle
                let template = "{{ states('\(entityId)') }}"
                let currentState = try await client.renderTemplate(template)
                let service = currentState.trimmingCharacters(in: .whitespacesAndNewlines) == "on" ? "turn_off" : "turn_on"
                try await client.callService(domain: domain, service: service, entityId: entityId)
            }

            // Refresh the current view after toggling
            try? await Task.sleep(for: .milliseconds(500))
            if let config = currentConfig,
               selectedViewIndex < config.views.count,
               let renderer = viewRenderer {
                let view = config.views[selectedViewIndex]
                if let rv = try? await renderer.render(view: view) {
                    renderedViews[selectedViewIndex] = rv
                }
            }
        } catch {
            // Silently fail — the entity state will update on next poll
        }
    }
}
