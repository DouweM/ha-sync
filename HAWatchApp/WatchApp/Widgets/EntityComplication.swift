import WidgetKit
import SwiftUI
import HAWatchCore

// TODO: APNs push widget updates — requires a Home Assistant addon to send APNs
// on state change. When implemented, add an APNs handler in HAWatchApp.swift
// that calls WidgetCenter.shared.reloadTimelines(ofKind:) for relevant widgets.

struct EntityComplicationEntry: TimelineEntry {
    let date: Date
    let entityId: String?
    let entityName: String
    let stateText: String
    let iconName: String
    let stateColor: StateColor
    let numericValue: Double?
}

struct EntityComplicationProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> EntityComplicationEntry {
        EntityComplicationEntry(
            date: .now,
            entityId: nil,
            entityName: "Temperature",
            stateText: "23°C",
            iconName: "thermometer.medium",
            stateColor: .primary,
            numericValue: 23.0
        )
    }

    func snapshot(for configuration: EntityComplicationIntent, in context: Context) async -> EntityComplicationEntry {
        await fetchEntry(for: configuration) ?? placeholder(in: context)
    }

    func timeline(for configuration: EntityComplicationIntent, in context: Context) async -> Timeline<EntityComplicationEntry> {
        let entry = await fetchEntry(for: configuration) ?? EntityComplicationEntry(
            date: .now,
            entityId: configuration.entityId,
            entityName: configuration.entityName ?? "Entity",
            stateText: "--",
            iconName: "circle.fill",
            stateColor: .primary,
            numericValue: nil
        )

        let nextUpdate = Calendar.current.date(byAdding: .minute, value: 15, to: .now)!
        return Timeline(entries: [entry], policy: .after(nextUpdate))
    }

    @MainActor
    func recommendations() -> [AppIntentRecommendation<EntityComplicationIntent>] {
        let entities = SettingsManager.shared.appSettings.complicationEntities
        guard !entities.isEmpty else {
            return [
                AppIntentRecommendation(
                    intent: EntityComplicationIntent(),
                    description: "Entity State"
                )
            ]
        }

        return entities.map { entityId in
            let name = HAEntityQuery.nameFromId(entityId)
            let intent = EntityComplicationIntent(entityId: entityId, entityName: name)
            return AppIntentRecommendation(intent: intent, description: "\(name)")
        }
    }

    // MARK: - Smart Stack Relevance

    /// Provide relevance hints for Smart Stack ordering.
    /// Home automation entities are most relevant during morning/evening routines.
    func relevances() async -> WidgetRelevances<EntityComplicationIntent> {
        // Surface home automation widgets during morning and evening routines
        let calendar = Calendar.current
        let now = Date()

        var relevances: [WidgetRelevance<EntityComplicationIntent>] = []

        // Morning routine: 6:00 - 9:00
        if var morningStart = calendar.date(bySettingHour: 6, minute: 0, second: 0, of: now),
           var morningEnd = calendar.date(bySettingHour: 9, minute: 0, second: 0, of: now) {
            // If we're past 9am, use tomorrow's window
            if now > morningEnd {
                morningStart = calendar.date(byAdding: .day, value: 1, to: morningStart) ?? morningStart
                morningEnd = calendar.date(byAdding: .day, value: 1, to: morningEnd) ?? morningEnd
            }
            relevances.append(WidgetRelevance(relevance: .date(from: morningStart, to: morningEnd)))
        }

        // Evening routine: 17:00 - 22:00
        if var eveningStart = calendar.date(bySettingHour: 17, minute: 0, second: 0, of: now),
           var eveningEnd = calendar.date(bySettingHour: 22, minute: 0, second: 0, of: now) {
            if now > eveningEnd {
                eveningStart = calendar.date(byAdding: .day, value: 1, to: eveningStart) ?? eveningStart
                eveningEnd = calendar.date(byAdding: .day, value: 1, to: eveningEnd) ?? eveningEnd
            }
            relevances.append(WidgetRelevance(relevance: .date(from: eveningStart, to: eveningEnd)))
        }

        return WidgetRelevances(relevances)
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

        let numericValue = Double(entityState.state)

        return EntityComplicationEntry(
            date: .now,
            entityId: entityId,
            entityName: configuration.entityName ?? entityState.displayName,
            stateText: formatted.text,
            iconName: iconName,
            stateColor: formatted.color,
            numericValue: numericValue
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

struct CornerComplicationView: View {
    let entry: EntityComplicationEntry

    var body: some View {
        if let value = entry.numericValue {
            // Gauge for numeric entities (temperature, battery, etc.)
            Gauge(value: clampedValue(value), in: gaugeRange(value)) {
                Image(systemName: entry.iconName)
            } currentValueLabel: {
                Text(entry.stateText)
                    .font(.system(size: 11))
            }
            .gaugeStyle(.circular)
            .widgetAccentable()
            .widgetLabel(entry.entityName)
        } else {
            // Non-numeric: show icon + state text
            VStack(spacing: 1) {
                Image(systemName: entry.iconName)
                    .font(.title3)
                Text(entry.stateText)
                    .font(.system(size: 11))
            }
            .widgetAccentable()
            .widgetLabel(entry.entityName)
        }
    }

    /// Clamp value within a reasonable gauge range
    private func clampedValue(_ value: Double) -> Double {
        min(max(value, gaugeRange(value).lowerBound), gaugeRange(value).upperBound)
    }

    /// Determine a sensible gauge range based on value magnitude
    private func gaugeRange(_ value: Double) -> ClosedRange<Double> {
        if value >= 0 && value <= 100 {
            return 0...100  // Percentage-like (battery, humidity)
        } else if value >= -40 && value <= 60 {
            return -40...60  // Temperature-like
        } else {
            return 0...max(value * 1.5, 1)
        }
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
        Group {
            switch widgetFamily {
            case .accessoryCircular:
                CircularComplicationView(entry: entry)
            case .accessoryRectangular:
                RectangularComplicationView(entry: entry)
            case .accessoryInline:
                InlineComplicationView(entry: entry)
            case .accessoryCorner:
                CornerComplicationView(entry: entry)
            default:
                CircularComplicationView(entry: entry)
            }
        }
        .widgetURL(URL(string: "hawatch://entity/\(entry.entityId ?? "")")!)
    }
}
