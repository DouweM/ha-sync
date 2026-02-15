import SwiftUI
import HAWatchCore

struct ComplicationConfigView: View {
    @Environment(SettingsManager.self) private var settings

    @State private var showAddSheet = false
    @State private var entityStates: [String: EntityState] = [:]

    private var selectedIds: [String] {
        settings.appSettings.complicationEntities
    }

    private func displayName(for entityId: String) -> String {
        if let state = entityStates[entityId] {
            return state.displayName
        }
        // Fallback: prettify the entity ID
        let objectId = entityId.split(separator: ".").dropFirst().joined(separator: ".")
        return objectId.replacingOccurrences(of: "_", with: " ").capitalized
    }

    var body: some View {
        List {
            if selectedIds.isEmpty {
                ContentUnavailableView(
                    "No Complications",
                    systemImage: "watchface.applewatch.case",
                    description: Text("Tap + to add entities for watch complications.")
                )
            } else {
                ForEach(selectedIds, id: \.self) { entityId in
                    HStack {
                        Image(systemName: IconMapper.shared.sfSymbolName(
                            for: entityStates[entityId]?.icon,
                            entityId: entityId,
                            deviceClass: entityStates[entityId]?.deviceClass
                        ))
                        .frame(width: 24)
                        .foregroundStyle(.secondary)

                        VStack(alignment: .leading) {
                            Text(displayName(for: entityId))
                                .font(.body)
                            Text(entityId)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .onDelete { offsets in
                    var ids = selectedIds
                    ids.remove(atOffsets: offsets)
                    settings.updateComplicationEntities(ids)
                }
            }
        }
        .navigationTitle("Complications")
        .task(id: selectedIds) {
            await loadEntityStates()
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showAddSheet = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showAddSheet) {
            EntitySearchSheet()
        }
    }

    private func loadEntityStates() async {
        guard !selectedIds.isEmpty,
              let url = settings.appSettings.baseURL else { return }

        let client = HAAPIClient(baseURL: url, token: settings.appSettings.accessToken)
        let templateService = TemplateService(apiClient: client)

        if let states = try? await templateService.fetchEntityStates(entityIds: selectedIds) {
            entityStates = states
        }
    }
}

// MARK: - Entity Search Sheet

private struct EntitySearchSheet: View {
    @Environment(SettingsManager.self) private var settings
    @Environment(\.dismiss) private var dismiss

    @State private var entities: [EntitySearchResult] = []
    @State private var isLoading = false
    @State private var searchText = ""

    private var selectedIds: Set<String> {
        Set(settings.appSettings.complicationEntities)
    }

    var filteredEntities: [EntitySearchResult] {
        if searchText.isEmpty { return entities }
        return entities.filter { entity in
            entity.entityId.localizedCaseInsensitiveContains(searchText) ||
            entity.name.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(filteredEntities, id: \.entityId) { entity in
                    Button {
                        toggleSelection(entity.entityId)
                    } label: {
                        HStack {
                            Image(systemName: IconMapper.shared.sfSymbolName(
                                for: entity.icon,
                                entityId: entity.entityId,
                                deviceClass: entity.attributes?.deviceClass
                            ))
                            .frame(width: 24)
                            .foregroundStyle(.secondary)

                            VStack(alignment: .leading) {
                                Text(entity.name.isEmpty ? entity.entityId : entity.name)
                                    .font(.body)
                                Text(entity.entityId)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            if selectedIds.contains(entity.entityId) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.blue)
                            }
                        }
                    }
                    .tint(.primary)
                }
            }
            .overlay {
                if isLoading {
                    ProgressView("Loading entities...")
                }
            }
            .navigationTitle("Add Entity")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $searchText, prompt: "Search entities")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .task { await loadEntities() }
        }
    }

    private func toggleSelection(_ entityId: String) {
        var ids = settings.appSettings.complicationEntities
        if let index = ids.firstIndex(of: entityId) {
            ids.remove(at: index)
        } else {
            ids.append(entityId)
        }
        settings.updateComplicationEntities(ids)
    }

    private func loadEntities() async {
        guard let url = settings.appSettings.baseURL else { return }
        isLoading = true

        let client = HAAPIClient(baseURL: url, token: settings.appSettings.accessToken)
        let templateService = TemplateService(apiClient: client)

        let domains = ["sensor", "binary_sensor", "light", "switch", "climate", "lock", "person", "weather"]
        var allEntities: [EntitySearchResult] = []

        for domain in domains {
            if let results = try? await templateService.searchEntities(domain: domain) {
                allEntities.append(contentsOf: results)
            }
        }

        entities = allEntities.sorted { $0.entityId < $1.entityId }
        isLoading = false
    }
}
