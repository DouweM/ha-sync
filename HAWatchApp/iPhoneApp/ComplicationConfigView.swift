import SwiftUI
import HAWatchCore

struct ComplicationConfigView: View {
    let serverURL: String
    let accessToken: String

    @State private var entities: [EntitySearchResult] = []
    @State private var isLoading = false
    @State private var searchText = ""
    @State private var selectedEntities: Set<String> = []

    var filteredEntities: [EntitySearchResult] {
        if searchText.isEmpty { return entities }
        return entities.filter { entity in
            entity.entityId.localizedCaseInsensitiveContains(searchText) ||
            entity.name.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        List {
            if isLoading {
                ProgressView("Loading entities...")
            } else {
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

                            if selectedEntities.contains(entity.entityId) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.blue)
                            }
                        }
                    }
                    .tint(.primary)
                }
            }
        }
        .navigationTitle("Complications")
        .searchable(text: $searchText, prompt: "Search entities")
        .task { await loadEntities() }
    }

    private func toggleSelection(_ entityId: String) {
        if selectedEntities.contains(entityId) {
            selectedEntities.remove(entityId)
        } else {
            selectedEntities.insert(entityId)
        }
    }

    private func loadEntities() async {
        guard let url = URL(string: serverURL) else { return }
        isLoading = true

        let client = HAAPIClient(baseURL: url, token: accessToken)
        let templateService = TemplateService(apiClient: client)

        // Load common domains
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
