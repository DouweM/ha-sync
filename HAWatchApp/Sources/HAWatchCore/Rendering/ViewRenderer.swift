import Foundation

/// Orchestrates the full rendering pipeline:
/// fetch states -> resolve auto-entities -> check visibility -> produce RenderedView.
public actor ViewRenderer {
    private let apiClient: HAAPIClient
    private let templateService: TemplateService
    private let stateCache: StateCache
    private let autoEntitiesResolver: AutoEntitiesResolver
    private let iconMapper: IconMapper
    private let stateFormatter: StateFormatter
    private let visibilityChecker: VisibilityChecker
    private let badgeRenderer: BadgeRenderer
    private let cardRenderer: CardRenderer
    private let sectionRenderer: SectionRenderer

    private var currentUserId: String?

    public init(apiClient: HAAPIClient) {
        self.apiClient = apiClient
        let templateService = TemplateService(apiClient: apiClient)
        let stateCache = StateCache(templateService: templateService)

        self.templateService = templateService
        self.stateCache = stateCache
        self.autoEntitiesResolver = AutoEntitiesResolver(
            templateService: templateService,
            stateCache: stateCache
        )
        self.iconMapper = .shared
        self.stateFormatter = .shared
        self.visibilityChecker = VisibilityChecker()
        self.badgeRenderer = BadgeRenderer()
        self.cardRenderer = CardRenderer()
        self.sectionRenderer = SectionRenderer()
    }

    /// Render a complete view config into a RenderedView.
    public func render(
        view: ViewConfig,
        user: String? = nil
    ) async throws -> RenderedView {
        // Resolve user ID if needed
        if let user = user {
            let userIds = try await templateService.fetchUserIds()
            currentUserId = userIds[user.lowercased()]
        }

        // Extract and fetch all entity states
        let entityIds = StateCache.extractEntityIds(from: view)
        try await stateCache.fetchStates(for: entityIds)

        // Take a snapshot of all cached states for synchronous access
        let stateSnapshot = await buildStateSnapshot(entityIds: entityIds)
        let syncStateProvider: @Sendable (String) -> EntityState? = { entityId in
            stateSnapshot[entityId]
        }

        // Render badges
        let badges = await renderBadges(
            badges: view.badges ?? [],
            stateProvider: syncStateProvider
        )

        // Render sections
        var sections: [RenderedSection] = []
        for section in view.sections ?? [] {
            if let rendered = await renderFullSection(
                section: section,
                stateProvider: syncStateProvider
            ) {
                sections.append(rendered)
            }
        }

        return RenderedView(
            title: view.title,
            path: view.path,
            badges: badges,
            sections: sections
        )
    }

    /// Refresh entity states for the current view (for polling).
    public func refreshStates() async throws {
        try await stateCache.refreshAll()
    }

    // MARK: - Private

    private func buildStateSnapshot(entityIds: Set<String>) async -> [String: EntityState] {
        var snapshot: [String: EntityState] = [:]
        for entityId in entityIds {
            if let state = await stateCache.getState(entityId) {
                snapshot[entityId] = state
            }
        }
        return snapshot
    }

    private func renderBadges(
        badges: [BadgeConfig],
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> [RenderedBadge] {
        // Collect all mushroom badge templates for batch evaluation
        var templates: [String] = []
        // Track which badge index maps to which template indices (content, label, color, icon, picture)
        var badgeTemplateMap: [(badgeIndex: Int, contentIdx: Int?, labelIdx: Int?, colorIdx: Int?, iconIdx: Int?, pictureIdx: Int?)] = []

        for (i, badge) in badges.enumerated() {
            let badgeType = badge.type ?? "entity"
            guard badgeType == "custom:mushroom-template-badge" else { continue }

            var contentIdx: Int?
            var labelIdx: Int?
            var colorIdx: Int?
            var iconIdx: Int?
            var pictureIdx: Int?
            if let content = badge.content {
                contentIdx = templates.count
                templates.append(content)
            }
            if let label = badge.label {
                labelIdx = templates.count
                templates.append(label)
            }
            // Color can also be a Jinja template
            if let color = badge.color, color.contains("{") {
                colorIdx = templates.count
                templates.append(color)
            }
            // Icon can be a Jinja template
            if let icon = badge.icon, icon.contains("{") {
                iconIdx = templates.count
                templates.append(icon)
            }
            // Picture can be a Jinja template
            if let picture = badge.picture, !picture.isEmpty, picture.contains("{") {
                pictureIdx = templates.count
                templates.append(picture)
            }
            badgeTemplateMap.append((badgeIndex: i, contentIdx: contentIdx, labelIdx: labelIdx, colorIdx: colorIdx, iconIdx: iconIdx, pictureIdx: pictureIdx))
        }

        // Batch evaluate all templates in a single API call
        let results = (try? await templateService.evaluateBatch(templates)) ?? Array(repeating: "", count: templates.count)

        // Build lookup from badge index to evaluated results
        var mushroomResults: [Int: (content: String?, label: String?, color: String?, icon: String?, picture: String?)] = [:]
        for entry in badgeTemplateMap {
            let content = entry.contentIdx.map { results[$0] }
            let label = entry.labelIdx.map { results[$0] }
            let color = entry.colorIdx.map { results[$0] }
            let icon = entry.iconIdx.map { results[$0] }
            let picture = entry.pictureIdx.map { results[$0] }
            mushroomResults[entry.badgeIndex] = (content, label, color, icon, picture)
        }

        // Render all badges
        var rendered: [RenderedBadge] = []
        for (i, badge) in badges.enumerated() {
            let badgeType = badge.type ?? "entity"

            if badgeType == "custom:mushroom-template-badge" {
                let templateResults = mushroomResults[i]
                // If color was a template, update the badge with the evaluated result
                var effectiveBadge = badge
                if let evaluatedColor = templateResults?.color,
                   !evaluatedColor.isEmpty {
                    effectiveBadge.color = evaluatedColor
                }
                if let renderedBadge = badgeRenderer.renderMushroomBadge(
                    badge: effectiveBadge,
                    contentResult: templateResults?.content,
                    labelResult: templateResults?.label,
                    iconResult: templateResults?.icon,
                    pictureResult: templateResults?.picture,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    rendered.append(renderedBadge)
                }
            } else {
                if let renderedBadge = badgeRenderer.renderEntityBadge(
                    badge: badge,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    rendered.append(renderedBadge)
                }
            }
        }

        return rendered
    }

    private func renderFullSection(
        section: SectionConfig,
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> RenderedSection? {
        guard visibilityChecker.isVisible(
            conditions: section.visibility,
            stateProvider: { stateProvider($0)?.state ?? "unknown" },
            currentUserId: currentUserId
        ) else { return nil }

        let cards = section.cards ?? []
        var items: [RenderedSectionItem] = []
        var pendingHeading: CardConfig?

        for card in cards {
            if card.type == "heading", let headingText = card.heading, !headingText.isEmpty {
                let heading = await buildHeadingAsync(
                    card: card,
                    stateProvider: stateProvider
                )

                guard let heading = heading else { continue }

                if let existing = pendingHeading {
                    if let h = await buildHeadingAsync(card: existing, stateProvider: stateProvider) {
                        items.append(.spacing)
                        items.append(.heading(h))
                    }
                    pendingHeading = nil
                }

                if heading.badges.isEmpty {
                    pendingHeading = card
                } else {
                    items.append(.spacing)
                    items.append(.heading(heading))
                }
                continue
            }

            let renderedCard = await renderCardAsync(
                card: card,
                stateProvider: stateProvider
            )

            if let renderedCard = renderedCard {
                if let pending = pendingHeading {
                    if let h = await buildHeadingAsync(card: pending, stateProvider: stateProvider) {
                        items.append(.spacing)
                        items.append(.heading(h))
                    }
                    pendingHeading = nil
                }
                items.append(.card(renderedCard))
            }
        }

        guard !items.isEmpty else { return nil }
        return RenderedSection(items: items)
    }

    private func buildHeadingAsync(
        card: CardConfig,
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> RenderedHeading? {
        guard visibilityChecker.isVisible(
            conditions: card.visibility,
            stateProvider: { stateProvider($0)?.state ?? "unknown" },
            currentUserId: currentUserId
        ) else { return nil }

        guard let text = card.heading, !text.isEmpty else { return nil }

        let iconName: String?
        if let icon = card.icon, !icon.isEmpty {
            iconName = iconMapper.sfSymbolName(for: icon)
        } else {
            iconName = nil
        }

        let badgeConfigs = card.badges ?? []

        // Collect mushroom badge templates for batch evaluation
        var templates: [String] = []
        var badgeTemplateMap: [(badgeIndex: Int, contentIdx: Int?, labelIdx: Int?, colorIdx: Int?, iconIdx: Int?, pictureIdx: Int?)] = []

        for (i, badgeConfig) in badgeConfigs.enumerated() {
            let badgeType = badgeConfig.type ?? "entity"
            guard badgeType == "custom:mushroom-template-badge" else { continue }

            var contentIdx: Int?
            var labelIdx: Int?
            var colorIdx: Int?
            var iconIdx: Int?
            var pictureIdx: Int?
            if let content = badgeConfig.content {
                contentIdx = templates.count
                templates.append(content)
            }
            if let label = badgeConfig.label {
                labelIdx = templates.count
                templates.append(label)
            }
            if let color = badgeConfig.color, color.contains("{") {
                colorIdx = templates.count
                templates.append(color)
            }
            if let icon = badgeConfig.icon, icon.contains("{") {
                iconIdx = templates.count
                templates.append(icon)
            }
            if let picture = badgeConfig.picture, !picture.isEmpty, picture.contains("{") {
                pictureIdx = templates.count
                templates.append(picture)
            }
            badgeTemplateMap.append((badgeIndex: i, contentIdx: contentIdx, labelIdx: labelIdx, colorIdx: colorIdx, iconIdx: iconIdx, pictureIdx: pictureIdx))
        }

        let results = (try? await templateService.evaluateBatch(templates)) ?? Array(repeating: "", count: templates.count)

        var mushroomResults: [Int: (content: String?, label: String?, color: String?, icon: String?, picture: String?)] = [:]
        for entry in badgeTemplateMap {
            let content = entry.contentIdx.map { results[$0] }
            let label = entry.labelIdx.map { results[$0] }
            let color = entry.colorIdx.map { results[$0] }
            let icon = entry.iconIdx.map { results[$0] }
            let picture = entry.pictureIdx.map { results[$0] }
            mushroomResults[entry.badgeIndex] = (content, label, color, icon, picture)
        }

        var badges: [RenderedBadge] = []
        for (i, badgeConfig) in badgeConfigs.enumerated() {
            let badgeType = badgeConfig.type ?? "entity"

            if badgeType == "custom:mushroom-template-badge" {
                let templateResults = mushroomResults[i]
                var effectiveBadge = badgeConfig
                if let evaluatedColor = templateResults?.color,
                   !evaluatedColor.isEmpty {
                    effectiveBadge.color = evaluatedColor
                }
                if let badge = badgeRenderer.renderMushroomBadge(
                    badge: effectiveBadge,
                    contentResult: templateResults?.content,
                    labelResult: templateResults?.label,
                    iconResult: templateResults?.icon,
                    pictureResult: templateResults?.picture,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    badges.append(badge)
                }
            } else {
                if let badge = badgeRenderer.renderEntityBadge(
                    badge: badgeConfig,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    badges.append(badge)
                }
            }
        }

        return RenderedHeading(
            text: text,
            iconName: iconName,
            badges: badges
        )
    }

    private func renderCardAsync(
        card: CardConfig,
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> RenderedCard? {
        switch card.type {
        case "tile":
            return cardRenderer.renderTile(
                card: card,
                stateProvider: stateProvider,
                currentUserId: currentUserId
            )

        case "custom:auto-entities":
            guard let filter = card.filter else { return nil }
            let cardConfig = card.card
            // Handle auto-entities wrapping a map card
            if cardConfig?.type == "custom:map-card" {
                return await renderAutoEntitiesMapCard(card: card, filter: filter, stateProvider: stateProvider)
            }
            // Skip logbook nested cards
            if cardConfig?.type == "logbook" {
                return nil
            }

            let resolved = (try? await autoEntitiesResolver.resolve(filter: filter)) ?? []
            // Re-snapshot state after auto-entities resolution (new entities may have been cached)
            let freshSnapshot = await buildAutoEntitiesSnapshot(resolved: resolved, stateProvider: stateProvider)
            return cardRenderer.renderAutoEntities(
                resolvedEntities: resolved,
                stateProvider: { freshSnapshot[$0] }
            )

        case "logbook":
            return await renderLogbookCard(card: card, stateProvider: stateProvider)

        case "picture-entity":
            return cardRenderer.renderCamera(card: card, stateProvider: stateProvider)

        case "weather-forecast":
            return await renderWeatherCard(card: card, stateProvider: stateProvider)

        case "history-graph":
            return await renderHistoryGraphCard(card: card, stateProvider: stateProvider)

        case "custom:map-card":
            return await renderMapCard(card: card, stateProvider: stateProvider)

        case "custom:navbar-card":
            return nil

        default:
            return nil
        }
    }

    private func buildAutoEntitiesSnapshot(
        resolved: [(entityId: String, options: AutoEntitiesOptions)],
        stateProvider: (String) -> EntityState?
    ) async -> [String: EntityState] {
        var snapshot: [String: EntityState] = [:]
        for (entityId, _) in resolved {
            if let state = await stateCache.getState(entityId) {
                snapshot[entityId] = state
            } else if let state = stateProvider(entityId) {
                snapshot[entityId] = state
            }
        }
        return snapshot
    }

    private func renderLogbookCard(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) async -> RenderedCard? {
        var entityIds: [String] = []
        if let target = card.target?.entityId {
            entityIds = target
        } else if let entities = card.entities {
            entityIds = entities
        }

        guard !entityIds.isEmpty else { return nil }

        // Fetch logbook data via template
        let lines = entityIds.map { eid in
            """
            \(eid)|||{{ states("\(eid)") }}|||{{ state_attr("\(eid)", "friendly_name") | default("", true) | replace("\\n", " ") }}|||{{ as_timestamp(states.\(eid).last_changed) | default(0) }}
            """
        }
        let template = lines.joined(separator: "\n")

        guard let output = try? await templateService.evaluate(template) else { return nil }

        var entries: [(Date, String, String, String)] = []
        let now = Date()

        for line in output.split(separator: "\n") {
            let parts = line.split(separator: "|||", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
            guard parts.count >= 4 else { continue }

            let entityId = parts[0]
            let state = parts[1]
            let name = parts[2].isEmpty
                ? entityId.split(separator: ".").dropFirst().joined(separator: ".").replacingOccurrences(of: "_", with: " ").capitalized
                : parts[2]
            let timestampStr = parts[3]

            guard !state.isEmpty, state != "unavailable", state != "unknown",
                  let timestamp = Double(timestampStr), timestamp > 0
            else { continue }

            let date = Date(timeIntervalSince1970: timestamp)
            entries.append((date, name, state, entityId))
        }

        entries.sort { $0.0 > $1.0 }

        let logbookEntries = entries.prefix(5).compactMap { (lastChanged, name, state, entityId) -> LogbookEntry? in
            let formatted = stateFormatter.format(
                entityId: entityId,
                state: state,
                deviceClass: stateProvider(entityId)?.deviceClass ?? ""
            )
            guard !formatted.text.isEmpty else { return nil }

            let delta = now.timeIntervalSince(lastChanged)
            let timeAgo: String
            if delta >= 86400 {
                timeAgo = "\(Int(delta / 86400))d ago"
            } else if delta >= 3600 {
                timeAgo = "\(Int(delta / 3600))h ago"
            } else if delta >= 60 {
                timeAgo = "\(Int(delta / 60))m ago"
            } else {
                timeAgo = "just now"
            }

            return LogbookEntry(name: name, state: formatted, timeAgo: timeAgo)
        }

        return cardRenderer.renderLogbook(entries: logbookEntries)
    }

    // MARK: - Weather rendering

    private func renderWeatherCard(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) async -> RenderedCard? {
        guard let entityId = card.entity else { return nil }
        guard let entityState = stateProvider(entityId) else { return nil }

        let condition = entityState.state
        let iconName = iconMapper.weatherSymbolName(for: condition)
        let rawTemp = entityState.attributes["temperature"] ?? ""
        let tempUnit = entityState.unit.isEmpty ? "°C" : entityState.unit
        let temp = stateFormatter.formatTemperature(rawValue: rawTemp, unit: tempUnit) ?? entityState.state

        var forecastItems: [WeatherForecastItem] = []

        if card.showForecast != false {
            // Fetch forecast via template
            let template = """
            {% set forecast = state_attr('\(entityId)', 'forecast') or [] %}
            [{% for f in forecast[:5] %}{"day": {{ f.datetime[:10] | tojson }}, "condition": {{ f.condition | tojson }}, "temp": {{ f.temperature | default(0) }}, "templow": {{ f.templow | default("") | tojson }}}{% if not loop.last %},{% endif %}{% endfor %}]
            """
            if let output = try? await templateService.evaluate(template),
               let data = output.replacingOccurrences(of: "\n", with: "").data(using: .utf8),
               let items = try? JSONDecoder().decode([WeatherForecastJSON].self, from: data) {
                let dayFormatter = DateFormatter()
                dayFormatter.dateFormat = "yyyy-MM-dd"
                let shortFormatter = DateFormatter()
                shortFormatter.dateFormat = "EEE"

                for item in items {
                    let dayLabel: String
                    if let date = dayFormatter.date(from: item.day) {
                        dayLabel = shortFormatter.string(from: date)
                    } else {
                        dayLabel = String(item.day.suffix(5))
                    }

                    forecastItems.append(WeatherForecastItem(
                        day: dayLabel,
                        iconName: iconMapper.weatherSymbolName(for: item.condition),
                        tempHigh: "\(Int(item.temp))°",
                        tempLow: item.templow.isEmpty ? nil : "\(item.templow)°"
                    ))
                }
            }
        }

        return .weather(RenderedWeather(
            entityId: entityId,
            condition: condition.replacingOccurrences(of: "_", with: " ").capitalized,
            temperature: temp,
            iconName: iconName,
            forecast: forecastItems
        ))
    }

    // MARK: - History graph rendering

    private func renderHistoryGraphCard(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) async -> RenderedCard? {
        guard let entityId = card.entity ?? card.entities?.first else { return nil }
        let name = card.name ?? stateProvider(entityId)?.displayName ?? entityId
        let hoursToShow = card.hoursToShow ?? 24

        let end = Date()
        let start = end.addingTimeInterval(-Double(hoursToShow) * 3600)

        var dataPoints: [HistoryDataPoint] = []
        if let history = try? await apiClient.fetchHistory(entityId: entityId, start: start, end: end),
           let entries = history.first {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let fallbackFormatter = ISO8601DateFormatter()
            fallbackFormatter.formatOptions = [.withInternetDateTime]

            for entry in entries {
                guard let value = Double(entry.state) else { continue }
                let dateStr = entry.lastChanged ?? ""
                guard let date = formatter.date(from: dateStr) ?? fallbackFormatter.date(from: dateStr) else { continue }
                dataPoints.append(HistoryDataPoint(timestamp: date, value: value))
            }
        }

        return .historyGraph(RenderedHistoryGraph(
            entityId: entityId,
            name: name,
            dataPoints: dataPoints
        ))
    }

    // MARK: - Map card rendering

    private func renderMapCard(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) async -> RenderedCard? {
        let mapEntities = card.mapCardEntities ?? []
        guard !mapEntities.isEmpty else { return nil }

        let entityIds = mapEntities.compactMap(\.entity)
        guard !entityIds.isEmpty else { return nil }

        // Fetch GPS coordinates for all map entities via template
        let markers = await fetchMapMarkers(entityIds: entityIds, mapEntities: mapEntities, stateProvider: stateProvider)
        guard !markers.isEmpty else { return nil }

        // Resolve focus_entity coordinates if specified
        let focusCoords: (lat: Double, lon: Double)?
        if let focusEntity = card.focusEntity {
            focusCoords = resolveFocusCoordinates(entityId: focusEntity, markers: markers, zones: await fetchMapZones())
        } else {
            focusCoords = nil
        }

        // Check if this is an image-overlay map (has image plugin with bounds)
        if let plugins = card.plugins,
           let imagePlugin = plugins.first(where: { $0.name == "image" }),
           let imageURL = imagePlugin.options?.url,
           let boundsArray = imagePlugin.options?.bounds,
           let coordMapper = CoordinateMapper(boundsArray: boundsArray) {

            // Image overlay mode - normalize marker positions
            let normalizedMarkers = markers.map { marker -> MapMarker in
                var m = marker
                if let pos = coordMapper.normalize(latitude: marker.latitude, longitude: marker.longitude) {
                    m.normalizedX = pos.x
                    m.normalizedY = pos.y
                }
                return m
            }

            // Resolve focus center in normalized coordinates
            var focusCenterX: Double?
            var focusCenterY: Double?
            if let fc = focusCoords,
               let pos = coordMapper.normalize(latitude: fc.lat, longitude: fc.lon) {
                focusCenterX = pos.x
                focusCenterY = pos.y
            }

            // Fetch zone markers
            let zones = await fetchZoneMarkers(coordMapper: coordMapper)

            return cardRenderer.renderImageMap(
                imageURL: imageURL,
                markers: normalizedMarkers,
                zoneMarkers: zones,
                focusCenterX: focusCenterX,
                focusCenterY: focusCenterY
            )
        } else {
            // Native MapKit mode
            let avgLat = markers.map(\.latitude).reduce(0, +) / Double(markers.count)
            let avgLon = markers.map(\.longitude).reduce(0, +) / Double(markers.count)

            // Fetch zone data
            let zones = await fetchMapZones()

            return cardRenderer.renderNativeMap(
                centerLatitude: avgLat,
                centerLongitude: avgLon,
                markers: markers,
                zones: zones,
                useSatellite: card.darkMode ?? true,
                focusCenterLatitude: focusCoords?.lat,
                focusCenterLongitude: focusCoords?.lon
            )
        }
    }

    private func renderAutoEntitiesMapCard(
        card: CardConfig,
        filter: AutoEntitiesFilter,
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> RenderedCard? {
        let resolved = (try? await autoEntitiesResolver.resolve(filter: filter)) ?? []
        guard !resolved.isEmpty else { return nil }

        let entityIds = resolved.map(\.entityId)

        // Build MapEntity entries from resolved entities
        let mapEntities = entityIds.map { MapEntity(entity: $0) }
        let markers = await fetchMapMarkers(entityIds: entityIds, mapEntities: mapEntities, stateProvider: stateProvider)
        guard !markers.isEmpty else { return nil }

        // Check if the nested card config has plugin/bounds info
        let nestedCard = card.card
        if let plugins = nestedCard?.plugins,
           let imagePlugin = plugins.first(where: { $0.name == "image" }),
           let imageURL = imagePlugin.options?.url,
           let boundsArray = imagePlugin.options?.bounds,
           let coordMapper = CoordinateMapper(boundsArray: boundsArray) {

            let normalizedMarkers = markers.map { marker -> MapMarker in
                var m = marker
                if let pos = coordMapper.normalize(latitude: marker.latitude, longitude: marker.longitude) {
                    m.normalizedX = pos.x
                    m.normalizedY = pos.y
                }
                return m
            }
            let zones = await fetchZoneMarkers(coordMapper: coordMapper)
            return cardRenderer.renderImageMap(imageURL: imageURL, markers: normalizedMarkers, zoneMarkers: zones)
        }

        let avgLat = markers.map(\.latitude).reduce(0, +) / Double(markers.count)
        let avgLon = markers.map(\.longitude).reduce(0, +) / Double(markers.count)
        let zones = await fetchMapZones()
        return cardRenderer.renderNativeMap(
            centerLatitude: avgLat,
            centerLongitude: avgLon,
            markers: markers,
            zones: zones,
            useSatellite: nestedCard?.darkMode ?? true
        )
    }

    private func fetchMapMarkers(
        entityIds: [String],
        mapEntities: [MapEntity],
        stateProvider: (String) -> EntityState?
    ) async -> [MapMarker] {
        // Fetch lat/lon/entity_picture for each entity via template
        let lines = entityIds.map { eid in
            """
            \(eid)|||{{ state_attr("\(eid)", "latitude") | default("", true) }}|||{{ state_attr("\(eid)", "longitude") | default("", true) }}|||{{ state_attr("\(eid)", "friendly_name") | default("", true) }}|||{{ state_attr("\(eid)", "entity_picture") | default("", true) }}
            """
        }
        let template = lines.joined(separator: "\n")
        guard let output = try? await templateService.evaluate(template) else { return [] }

        // Build entity→MapEntity config lookup
        var entityConfigMap: [String: MapEntity] = [:]
        for me in mapEntities {
            if let entity = me.entity { entityConfigMap[entity] = me }
        }

        var markers: [MapMarker] = []
        for line in output.split(separator: "\n") {
            let parts = line.split(separator: "|||", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
            guard parts.count >= 3 else { continue }

            let entityId = parts[0]
            guard let lat = Double(parts[1]), let lon = Double(parts[2]) else { continue }

            let name = (parts.count > 3 && !parts[3].isEmpty)
                ? parts[3]
                : (stateProvider(entityId)?.displayName ?? entityId)
            let entityPicture = parts.count > 4 ? parts[4] : ""

            let config = entityConfigMap[entityId]
            markers.append(MapMarker(
                entityId: entityId,
                name: name,
                latitude: lat,
                longitude: lon,
                colorName: config?.color,
                size: config?.size,
                entityPictureURL: entityPicture.isEmpty ? nil : entityPicture
            ))
        }

        return markers
    }

    /// Resolve focus_entity to GPS coordinates by checking markers first, then zones.
    private func resolveFocusCoordinates(
        entityId: String,
        markers: [MapMarker],
        zones: [MapZone]
    ) -> (lat: Double, lon: Double)? {
        // Check if the focus entity is a tracked marker
        if let marker = markers.first(where: { $0.entityId == entityId }) {
            return (marker.latitude, marker.longitude)
        }
        // Check if it's a zone
        if let zone = zones.first(where: { $0.entityId == entityId }) {
            return (zone.latitude, zone.longitude)
        }
        return nil
    }

    private func fetchZoneMarkers(coordMapper: CoordinateMapper) async -> [ZoneMarker] {
        let template = """
        [{% for z in states.zone %}{"entity_id": {{ z.entity_id | tojson }}, "name": {{ z.name | tojson }}, "icon": {{ (z.attributes.icon | default("")) | tojson }}, "lat": {{ z.attributes.latitude | default(0) }}, "lon": {{ z.attributes.longitude | default(0) }}}{% if not loop.last %},{% endif %}{% endfor %}]
        """
        guard let output = try? await templateService.evaluate(template),
              let data = output.replacingOccurrences(of: "\n", with: "").data(using: .utf8),
              let zones = try? JSONDecoder().decode([ZoneJSON].self, from: data)
        else { return [] }

        return zones.compactMap { zone in
            guard let pos = coordMapper.normalize(latitude: zone.lat, longitude: zone.lon) else { return nil }
            let iconName = zone.icon.isEmpty ? nil : iconMapper.sfSymbolName(for: zone.icon)
            return ZoneMarker(
                entityId: zone.entityId,
                name: zone.name,
                iconName: iconName,
                normalizedX: pos.x,
                normalizedY: pos.y
            )
        }
    }

    private func fetchMapZones() async -> [MapZone] {
        let template = """
        [{% for z in states.zone %}{"entity_id": {{ z.entity_id | tojson }}, "name": {{ z.name | tojson }}, "icon": {{ (z.attributes.icon | default("")) | tojson }}, "lat": {{ z.attributes.latitude | default(0) }}, "lon": {{ z.attributes.longitude | default(0) }}, "radius": {{ z.attributes.radius | default(0) }}, "color": {{ (z.attributes.color | default("")) | tojson }}}{% if not loop.last %},{% endif %}{% endfor %}]
        """
        guard let output = try? await templateService.evaluate(template),
              let data = output.replacingOccurrences(of: "\n", with: "").data(using: .utf8),
              let zones = try? JSONDecoder().decode([MapZoneJSON].self, from: data)
        else { return [] }

        return zones.map { zone in
            let iconName = zone.icon.isEmpty ? nil : iconMapper.sfSymbolName(for: zone.icon)
            let colorName = zone.color.isEmpty ? nil : zone.color
            return MapZone(
                entityId: zone.entityId,
                name: zone.name,
                latitude: zone.lat,
                longitude: zone.lon,
                radius: zone.radius,
                iconName: iconName,
                colorName: colorName
            )
        }
    }
}

// MARK: - JSON helpers for zone decoding

private struct ZoneJSON: Codable {
    var entityId: String
    var name: String
    var icon: String
    var lat: Double
    var lon: Double

    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id"
        case name, icon, lat, lon
    }
}

private struct MapZoneJSON: Codable {
    var entityId: String
    var name: String
    var icon: String
    var lat: Double
    var lon: Double
    var radius: Double
    var color: String

    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id"
        case name, icon, lat, lon, radius, color
    }
}

private struct WeatherForecastJSON: Codable {
    var day: String
    var condition: String
    var temp: Double
    var templow: String
}
