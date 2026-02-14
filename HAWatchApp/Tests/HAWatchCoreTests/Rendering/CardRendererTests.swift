import Testing
@testable import HAWatchCore

@Suite("CardRenderer")
struct CardRendererTests {
    let renderer = CardRenderer()

    // MARK: - Tile card

    @Test("Tile card renders with entity_picture")
    func tileWithEntityPicture() {
        let card = CardConfig(type: "tile", entity: "person.john")
        let state = EntityState(
            entityId: "person.john",
            state: "home",
            name: "John",
            icon: "mdi:account",
            attributes: ["entity_picture": "/local/john.jpg"]
        )
        let result = renderer.renderTile(
            card: card,
            stateProvider: { $0 == "person.john" ? state : nil }
        )
        guard case .tile(let tile) = result else {
            Issue.record("Expected tile card")
            return
        }
        #expect(tile.entityPictureURL == "/local/john.jpg")
        #expect(tile.name == "John")
        #expect(tile.entityId == "person.john")
    }

    @Test("Tile card without entity_picture has nil URL")
    func tileWithoutEntityPicture() {
        let card = CardConfig(type: "tile", entity: "sensor.temp")
        let state = EntityState(
            entityId: "sensor.temp",
            state: "22.5",
            name: "Temperature",
            unit: "°C"
        )
        let result = renderer.renderTile(
            card: card,
            stateProvider: { $0 == "sensor.temp" ? state : nil }
        )
        guard case .tile(let tile) = result else {
            Issue.record("Expected tile card")
            return
        }
        #expect(tile.entityPictureURL == nil)
    }

    @Test("Tile card with missing entity returns nil")
    func tileMissingEntity() {
        let card = CardConfig(type: "tile", entity: "sensor.missing")
        let result = renderer.renderTile(
            card: card,
            stateProvider: { _ in nil }
        )
        #expect(result == nil)
    }

    @Test("Tile card respects grid_options for half-width")
    func tileHalfWidth() {
        let card = CardConfig(
            type: "tile",
            entity: "light.living_room",
            gridOptions: GridOptions(columns: 6)
        )
        let state = EntityState(entityId: "light.living_room", state: "on", name: "Living Room")
        let result = renderer.renderTile(
            card: card,
            stateProvider: { $0 == "light.living_room" ? state : nil }
        )
        guard case .tile(let tile) = result else {
            Issue.record("Expected tile card")
            return
        }
        #expect(tile.isHalfWidth == true)
    }

    @Test("Tile card name override from config")
    func tileNameOverride() {
        let card = CardConfig(type: "tile", entity: "sensor.temp", name: "Custom Name")
        let state = EntityState(entityId: "sensor.temp", state: "22", name: "Temperature")
        let result = renderer.renderTile(
            card: card,
            stateProvider: { $0 == "sensor.temp" ? state : nil }
        )
        guard case .tile(let tile) = result else {
            Issue.record("Expected tile card")
            return
        }
        #expect(tile.name == "Custom Name")
    }

    // MARK: - Auto-entities card

    @Test("Auto-entities card renders tiles from resolved entities")
    func autoEntitiesTiles() {
        let resolved: [(entityId: String, options: AutoEntitiesOptions)] = [
            ("light.bedroom", AutoEntitiesOptions()),
            ("light.kitchen", AutoEntitiesOptions(name: "Kitchen Light")),
        ]
        let states: [String: EntityState] = [
            "light.bedroom": EntityState(entityId: "light.bedroom", state: "on", name: "Bedroom"),
            "light.kitchen": EntityState(entityId: "light.kitchen", state: "on", name: "Kitchen"),
        ]
        let result = renderer.renderAutoEntities(
            resolvedEntities: resolved,
            stateProvider: { states[$0] }
        )
        guard case .autoEntities(let ae) = result else {
            Issue.record("Expected autoEntities card")
            return
        }
        #expect(ae.tiles.count == 2)
        #expect(ae.tiles[0].name == "Bedroom")
        #expect(ae.tiles[1].name == "Kitchen Light")
    }

    @Test("Auto-entities skips unavailable entities")
    func autoEntitiesSkipsUnavailable() {
        let resolved: [(entityId: String, options: AutoEntitiesOptions)] = [
            ("light.bedroom", AutoEntitiesOptions()),
        ]
        let states: [String: EntityState] = [
            "light.bedroom": EntityState(entityId: "light.bedroom", state: "unavailable", name: "Bedroom"),
        ]
        let result = renderer.renderAutoEntities(
            resolvedEntities: resolved,
            stateProvider: { states[$0] }
        )
        #expect(result == nil)
    }

    // MARK: - Weather card

    @Test("Weather card renders with condition")
    func weatherCard() {
        let card = CardConfig(type: "weather-forecast", entity: "weather.home")
        let state = EntityState(
            entityId: "weather.home",
            state: "partly_cloudy",
            name: "Home Weather",
            attributes: ["temperature": "18"]
        )
        let result = renderer.renderWeather(
            card: card,
            stateProvider: { $0 == "weather.home" ? state : nil }
        )
        guard case .weather(let weather) = result else {
            Issue.record("Expected weather card")
            return
        }
        #expect(weather.condition == "Partly Cloudy")
        #expect(weather.temperature == "18")
    }

    // MARK: - Camera card

    @Test("Camera card generates snapshot path")
    func cameraCard() {
        let card = CardConfig(type: "picture-entity", entity: "camera.front_door")
        let state = EntityState(entityId: "camera.front_door", state: "idle", name: "Front Door")
        let result = renderer.renderCamera(
            card: card,
            stateProvider: { $0 == "camera.front_door" ? state : nil }
        )
        guard case .camera(let cam) = result else {
            Issue.record("Expected camera card")
            return
        }
        #expect(cam.snapshotPath == "api/camera_proxy/camera.front_door")
        #expect(cam.name == "Front Door")
    }

    // MARK: - Map cards

    @Test("ImageMap card renders with markers and zones")
    func imageMapCard() {
        let markers = [
            MapMarker(entityId: "person.john", name: "John", latitude: 52.5, longitude: 4.9, normalizedX: 0.5, normalizedY: 0.5),
        ]
        let zones = [
            ZoneMarker(entityId: "zone.home", name: "Home", normalizedX: 0.5, normalizedY: 0.5),
        ]
        let result = renderer.renderImageMap(imageURL: "/local/map.png", markers: markers, zoneMarkers: zones)
        guard case .imageMap(let map) = result else {
            Issue.record("Expected imageMap card")
            return
        }
        #expect(map.imageURL == "/local/map.png")
        #expect(map.markers.count == 1)
        #expect(map.zoneMarkers.count == 1)
    }

    @Test("NativeMap card renders with center and markers")
    func nativeMapCard() {
        let markers = [
            MapMarker(entityId: "person.john", name: "John", latitude: 52.37, longitude: 4.89),
        ]
        let zones = [
            MapZone(entityId: "zone.home", name: "Home", latitude: 52.37, longitude: 4.89, radius: 100),
        ]
        let result = renderer.renderNativeMap(
            centerLatitude: 52.37,
            centerLongitude: 4.89,
            markers: markers,
            zones: zones,
            useSatellite: true
        )
        guard case .nativeMap(let map) = result else {
            Issue.record("Expected nativeMap card")
            return
        }
        #expect(map.centerLatitude == 52.37)
        #expect(map.markers.count == 1)
        #expect(map.zones.count == 1)
        #expect(map.useSatellite == true)
    }
}
