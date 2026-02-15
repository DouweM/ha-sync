import WidgetKit
import SwiftUI
import HAWatchCore

struct EntityComplicationEntry: TimelineEntry {
    let date: Date
    let entityName: String
    let stateText: String
    let iconName: String
    let stateColor: StateColor
}

struct EntityComplicationProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> EntityComplicationEntry {
        EntityComplicationEntry(
            date: .now,
            entityName: "Temperature",
            stateText: "23°C",
            iconName: "thermometer.medium",
            stateColor: .primary
        )
    }

    func snapshot(for configuration: EntityComplicationIntent, in context: Context) async -> EntityComplicationEntry {
        await fetchEntry(for: configuration) ?? placeholder(in: context)
    }

    func timeline(for configuration: EntityComplicationIntent, in context: Context) async -> Timeline<EntityComplicationEntry> {
        let entry = await fetchEntry(for: configuration) ?? EntityComplicationEntry(
            date: .now,
            entityName: configuration.entityName ?? "Entity",
            stateText: "--",
            iconName: "circle.fill",
            stateColor: .primary
        )

        let nextUpdate = Calendar.current.date(byAdding: .minute, value: 15, to: .now)!
        return Timeline(entries: [entry], policy: .after(nextUpdate))
    }

    func recommendations() -> [AppIntentRecommendation<EntityComplicationIntent>] {
        [
            AppIntentRecommendation(
                intent: EntityComplicationIntent(),
                description: "Entity State"
            )
        ]
    }

    @MainActor
    private func fetchEntry(for configuration: EntityComplicationIntent) async -> EntityComplicationEntry? {
        guard let entityId = configuration.entityId,
              let baseURL = SettingsManager.shared.appSettings.baseURL
        else { return nil }

        let client = HAAPIClient(baseURL: baseURL, token: SettingsManager.shared.appSettings.accessToken)
        let templateService = TemplateService(apiClient: client)

        guard let states = try? await templateService.fetchEntityStates(entityIds: [entityId]),
              let entityState = states[entityId]
        else { return nil }

        let stateFormatter = StateFormatter.shared
        let iconMapper = IconMapper.shared
        let formatted = stateFormatter.format(
            entityId: entityId,
            state: entityState.state,
            deviceClass: entityState.deviceClass,
            unit: entityState.unit
        )
        let iconName = iconMapper.sfSymbolName(
            for: entityState.icon,
            entityId: entityId,
            deviceClass: entityState.deviceClass
        )

        return EntityComplicationEntry(
            date: .now,
            entityName: configuration.entityName ?? entityState.displayName,
            stateText: formatted.text,
            iconName: iconName,
            stateColor: formatted.color
        )
    }
}

// MARK: - Widget Views

struct CircularComplicationView: View {
    let entry: EntityComplicationEntry

    var body: some View {
        VStack(spacing: 1) {
            Image(systemName: entry.iconName)
                .font(.title3)
            Text(entry.stateText)
                .font(.system(size: 11, weight: .medium))
                .minimumScaleFactor(0.6)
        }
        .widgetAccentable()
    }
}

struct RectangularComplicationView: View {
    let entry: EntityComplicationEntry

    var body: some View {
        HStack {
            Image(systemName: entry.iconName)
                .font(.title3)
            VStack(alignment: .leading) {
                Text(entry.entityName)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(entry.stateText)
                    .font(.headline)
            }
        }
        .widgetAccentable()
    }
}

struct InlineComplicationView: View {
    let entry: EntityComplicationEntry

    var body: some View {
        Text("\(entry.entityName): \(entry.stateText)")
    }
}

// MARK: - Widget

struct EntityComplicationWidget: Widget {
    let kind = "EntityComplication"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(
            kind: kind,
            intent: EntityComplicationIntent.self,
            provider: EntityComplicationProvider()
        ) { entry in
            EntityComplicationEntryView(entry: entry)
        }
        .configurationDisplayName("Entity State")
        .description("Show a Home Assistant entity on your watch face.")
        .supportedFamilies([
            .accessoryCircular,
            .accessoryRectangular,
            .accessoryInline,
            .accessoryCorner,
        ])
    }
}

struct EntityComplicationEntryView: View {
    @Environment(\.widgetFamily) var widgetFamily
    let entry: EntityComplicationEntry

    var body: some View {
        switch widgetFamily {
        case .accessoryCircular:
            CircularComplicationView(entry: entry)
        case .accessoryRectangular:
            RectangularComplicationView(entry: entry)
        case .accessoryInline:
            InlineComplicationView(entry: entry)
        default:
            CircularComplicationView(entry: entry)
        }
    }
}
