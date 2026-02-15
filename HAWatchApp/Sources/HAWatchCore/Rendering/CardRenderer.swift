import Foundation

/// Renders card configs into RenderedCard output.
/// Dispatches by card type, similar to render.py:868-889.
public struct CardRenderer: Sendable {
    private let iconMapper: IconMapper
    private let stateFormatter: StateFormatter
    private let visibilityChecker: VisibilityChecker

    public init(
        iconMapper: IconMapper = .shared,
        stateFormatter: StateFormatter = .shared,
        visibilityChecker: VisibilityChecker = VisibilityChecker()
    ) {
        self.iconMapper = iconMapper
        self.stateFormatter = stateFormatter
        self.visibilityChecker = visibilityChecker
    }

    // MARK: - Tile card

    /// Render a tile card.
    public func renderTile(
        card: CardConfig,
        stateProvider: (String) -> EntityState?,
        currentUserId: String? = nil
    ) -> RenderedCard? {
        guard let entityId = card.entity else { return nil }
        guard let entityState = stateProvider(entityId) else { return nil }

        let name = card.name ?? entityState.displayName
        let iconName = iconMapper.sfSymbolName(
            for: card.icon ?? entityState.icon,
            entityId: entityId,
            deviceClass: entityState.deviceClass
        )
        let formatted = stateFormatter.format(
            entityId: entityId,
            state: entityState.state,
            deviceClass: entityState.deviceClass,
            unit: entityState.unit
        )
        let isHalf = card.gridOptions?.columns?.intValue == 6

        let tile = RenderedTile(
            entityId: entityId,
            name: name,
            iconName: iconName,
            state: formatted,
            isHalfWidth: isHalf,
            entityPictureURL: entityState.attributes["entity_picture"],
            colorName: card.color
        )

        return .tile(tile)
    }

    // MARK: - Auto-entities card

    /// Render an auto-entities card from resolved entity list.
    public func renderAutoEntities(
        resolvedEntities: [(entityId: String, options: AutoEntitiesOptions)],
        stateProvider: (String) -> EntityState?
    ) -> RenderedCard? {
        var tiles: [RenderedTile] = []

        for (entityId, options) in resolvedEntities {
            guard let entityState = stateProvider(entityId) else { continue }
            let state = entityState.state
            if state.isEmpty || state == "unavailable" || state == "unknown" { continue }

            let name: String
            if let optName = options.name, !optName.trimmingCharacters(in: .whitespaces).isEmpty {
                name = optName
            } else {
                name = entityState.displayName
            }

            let icon = options.icon ?? entityState.icon
            let iconName = iconMapper.sfSymbolName(
                for: icon,
                entityId: entityId,
                deviceClass: entityState.deviceClass
            )
            let formatted = stateFormatter.format(
                entityId: entityId,
                state: state,
                deviceClass: entityState.deviceClass,
                unit: entityState.unit
            )

            tiles.append(RenderedTile(
                entityId: entityId,
                name: name,
                iconName: iconName,
                state: formatted,
                entityPictureURL: entityState.attributes["entity_picture"]
            ))
        }

        guard !tiles.isEmpty else { return nil }
        return .autoEntities(RenderedAutoEntities(tiles: tiles))
    }

    // MARK: - Weather card

    /// Render a weather card.
    public func renderWeather(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) -> RenderedCard? {
        guard let entityId = card.entity else { return nil }
        guard let entityState = stateProvider(entityId) else { return nil }

        let condition = entityState.state
        let iconName = iconMapper.weatherSymbolName(for: condition)
        let rawTemp = entityState.attributes["temperature"] ?? ""
        let tempUnit = entityState.unit.isEmpty ? "°C" : entityState.unit
        let temp = stateFormatter.formatTemperature(rawValue: rawTemp, unit: tempUnit) ?? entityState.state

        let weather = RenderedWeather(
            entityId: entityId,
            condition: condition.replacingOccurrences(of: "_", with: " ").capitalized,
            temperature: temp,
            iconName: iconName
        )

        return .weather(weather)
    }

    // MARK: - Camera card

    /// Render a camera/picture-entity card.
    public func renderCamera(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) -> RenderedCard? {
        let entityId = card.cameraImage ?? card.entity ?? ""
        guard !entityId.isEmpty else { return nil }

        let name = card.name ?? stateProvider(entityId)?.displayName ?? entityId
        let snapshotPath = "api/camera_proxy/\(entityId)"

        return .camera(RenderedCamera(
            entityId: entityId,
            name: name,
            snapshotPath: snapshotPath
        ))
    }

    // MARK: - History graph card

    /// Render a history graph card placeholder (data loaded separately).
    public func renderHistoryGraph(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) -> RenderedCard? {
        guard let entityId = card.entity ?? card.entities?.first?.entity else { return nil }
        let name = card.name ?? stateProvider(entityId)?.displayName ?? entityId

        return .historyGraph(RenderedHistoryGraph(
            entityId: entityId,
            name: name
        ))
    }

    // MARK: - Logbook card

    /// Render a logbook card from fetched state data.
    public func renderLogbook(
        entries: [LogbookEntry]
    ) -> RenderedCard? {
        guard !entries.isEmpty else { return nil }
        return .logbook(RenderedLogbook(entries: entries))
    }

    // MARK: - Map cards

    /// Render an image map card (Mode 1: custom image overlay).
    public func renderImageMap(
        imageURL: String,
        markers: [MapMarker],
        zoneMarkers: [ZoneMarker],
        focusCenterX: Double? = nil,
        focusCenterY: Double? = nil
    ) -> RenderedCard? {
        return .imageMap(RenderedImageMap(
            imageURL: imageURL,
            markers: markers,
            zoneMarkers: zoneMarkers,
            focusCenterX: focusCenterX,
            focusCenterY: focusCenterY
        ))
    }

    /// Render a native map card (Mode 2: MapKit).
    public func renderNativeMap(
        centerLatitude: Double,
        centerLongitude: Double,
        markers: [MapMarker],
        zones: [MapZone],
        useSatellite: Bool,
        focusCenterLatitude: Double? = nil,
        focusCenterLongitude: Double? = nil
    ) -> RenderedCard? {
        return .nativeMap(RenderedNativeMap(
            centerLatitude: centerLatitude,
            centerLongitude: centerLongitude,
            markers: markers,
            zones: zones,
            useSatellite: useSatellite,
            focusCenterLatitude: focusCenterLatitude,
            focusCenterLongitude: focusCenterLongitude
        ))
    }
}
