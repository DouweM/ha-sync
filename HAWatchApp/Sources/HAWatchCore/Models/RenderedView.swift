import Foundation

// MARK: - Rendered output tree (consumed by SwiftUI layer)

public struct RenderedView: Sendable {
    public var title: String?
    public var path: String?
    public var badges: [RenderedBadge]
    public var sections: [RenderedSection]

    public init(
        title: String? = nil,
        path: String? = nil,
        badges: [RenderedBadge] = [],
        sections: [RenderedSection] = []
    ) {
        self.title = title
        self.path = path
        self.badges = badges
        self.sections = sections
    }
}

public struct RenderedSection: Sendable {
    public var items: [RenderedSectionItem]

    public init(items: [RenderedSectionItem] = []) {
        self.items = items
    }
}

public enum RenderedSectionItem: Sendable {
    case heading(RenderedHeading)
    case card(RenderedCard)
    case spacing
}

public struct RenderedHeading: Sendable {
    public var text: String
    public var iconName: String?
    public var badges: [RenderedBadge]

    public init(text: String, iconName: String? = nil, badges: [RenderedBadge] = []) {
        self.text = text
        self.iconName = iconName
        self.badges = badges
    }
}

public struct RenderedBadge: Sendable {
    public var iconName: String?
    public var name: String
    public var state: FormattedState?
    public var entityId: String?
    public var entityPictureURL: String?

    public init(
        iconName: String? = nil,
        name: String,
        state: FormattedState? = nil,
        entityId: String? = nil,
        entityPictureURL: String? = nil
    ) {
        self.iconName = iconName
        self.name = name
        self.state = state
        self.entityId = entityId
        self.entityPictureURL = entityPictureURL
    }
}

public enum RenderedCard: Sendable {
    case tile(RenderedTile)
    case autoEntities(RenderedAutoEntities)
    case logbook(RenderedLogbook)
    case weather(RenderedWeather)
    case camera(RenderedCamera)
    case imageMap(RenderedImageMap)
    case nativeMap(RenderedNativeMap)
    case historyGraph(RenderedHistoryGraph)

    public var isHalfWidth: Bool {
        switch self {
        case .tile(let t): return t.isHalfWidth
        default: return false
        }
    }
}

// MARK: - Card content types

public struct RenderedTile: Sendable {
    public var entityId: String
    public var name: String
    public var iconName: String?
    public var state: FormattedState
    public var isHalfWidth: Bool
    public var entityPictureURL: String?
    public var colorName: String?

    public init(
        entityId: String,
        name: String,
        iconName: String? = nil,
        state: FormattedState,
        isHalfWidth: Bool = false,
        entityPictureURL: String? = nil,
        colorName: String? = nil
    ) {
        self.entityId = entityId
        self.name = name
        self.iconName = iconName
        self.state = state
        self.isHalfWidth = isHalfWidth
        self.entityPictureURL = entityPictureURL
        self.colorName = colorName
    }
}

public struct RenderedAutoEntities: Sendable {
    public var tiles: [RenderedTile]

    public init(tiles: [RenderedTile] = []) {
        self.tiles = tiles
    }
}

public struct RenderedLogbook: Sendable {
    public var entries: [LogbookEntry]

    public init(entries: [LogbookEntry] = []) {
        self.entries = entries
    }
}

public struct LogbookEntry: Sendable {
    public var name: String
    public var state: FormattedState
    public var timeAgo: String

    public init(name: String, state: FormattedState, timeAgo: String) {
        self.name = name
        self.state = state
        self.timeAgo = timeAgo
    }
}

public struct RenderedWeather: Sendable {
    public var entityId: String
    public var condition: String
    public var temperature: String
    public var iconName: String
    public var forecast: [WeatherForecastItem]

    public init(
        entityId: String,
        condition: String,
        temperature: String,
        iconName: String,
        forecast: [WeatherForecastItem] = []
    ) {
        self.entityId = entityId
        self.condition = condition
        self.temperature = temperature
        self.iconName = iconName
        self.forecast = forecast
    }
}

public struct WeatherForecastItem: Sendable {
    public var day: String
    public var iconName: String
    public var tempHigh: String
    public var tempLow: String?

    public init(day: String, iconName: String, tempHigh: String, tempLow: String? = nil) {
        self.day = day
        self.iconName = iconName
        self.tempHigh = tempHigh
        self.tempLow = tempLow
    }
}

public struct RenderedCamera: Sendable {
    public var entityId: String
    public var name: String
    public var snapshotPath: String

    public init(entityId: String, name: String, snapshotPath: String) {
        self.entityId = entityId
        self.name = name
        self.snapshotPath = snapshotPath
    }
}

public struct RenderedImageMap: Sendable {
    public var imageURL: String
    public var markers: [MapMarker]
    public var zoneMarkers: [ZoneMarker]
    public var focusCenterX: Double?
    public var focusCenterY: Double?

    public init(
        imageURL: String,
        markers: [MapMarker] = [],
        zoneMarkers: [ZoneMarker] = [],
        focusCenterX: Double? = nil,
        focusCenterY: Double? = nil
    ) {
        self.imageURL = imageURL
        self.markers = markers
        self.zoneMarkers = zoneMarkers
        self.focusCenterX = focusCenterX
        self.focusCenterY = focusCenterY
    }
}

public struct RenderedNativeMap: Sendable {
    public var centerLatitude: Double
    public var centerLongitude: Double
    public var markers: [MapMarker]
    public var zones: [MapZone]
    public var useSatellite: Bool
    public var focusCenterLatitude: Double?
    public var focusCenterLongitude: Double?

    public init(
        centerLatitude: Double,
        centerLongitude: Double,
        markers: [MapMarker] = [],
        zones: [MapZone] = [],
        useSatellite: Bool = true,
        focusCenterLatitude: Double? = nil,
        focusCenterLongitude: Double? = nil
    ) {
        self.centerLatitude = centerLatitude
        self.centerLongitude = centerLongitude
        self.markers = markers
        self.zones = zones
        self.useSatellite = useSatellite
        self.focusCenterLatitude = focusCenterLatitude
        self.focusCenterLongitude = focusCenterLongitude
    }

    /// The effective center, using focus override if available.
    public var effectiveCenterLatitude: Double {
        focusCenterLatitude ?? centerLatitude
    }

    public var effectiveCenterLongitude: Double {
        focusCenterLongitude ?? centerLongitude
    }
}

public struct MapMarker: Sendable {
    public var entityId: String
    public var name: String
    public var latitude: Double
    public var longitude: Double
    public var normalizedX: Double?
    public var normalizedY: Double?
    public var colorName: String?
    public var size: Int?
    public var entityPictureURL: String?

    public init(
        entityId: String,
        name: String,
        latitude: Double,
        longitude: Double,
        normalizedX: Double? = nil,
        normalizedY: Double? = nil,
        colorName: String? = nil,
        size: Int? = nil,
        entityPictureURL: String? = nil
    ) {
        self.entityId = entityId
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.normalizedX = normalizedX
        self.normalizedY = normalizedY
        self.colorName = colorName
        self.size = size
        self.entityPictureURL = entityPictureURL
    }
}

public struct ZoneMarker: Sendable {
    public var entityId: String
    public var name: String
    public var iconName: String?
    public var normalizedX: Double
    public var normalizedY: Double
    public var colorName: String?

    public init(
        entityId: String,
        name: String,
        iconName: String? = nil,
        normalizedX: Double,
        normalizedY: Double,
        colorName: String? = nil
    ) {
        self.entityId = entityId
        self.name = name
        self.iconName = iconName
        self.normalizedX = normalizedX
        self.normalizedY = normalizedY
        self.colorName = colorName
    }
}

public struct MapZone: Sendable {
    public var entityId: String
    public var name: String
    public var latitude: Double
    public var longitude: Double
    public var radius: Double
    public var iconName: String?
    public var colorName: String?

    public init(
        entityId: String,
        name: String,
        latitude: Double,
        longitude: Double,
        radius: Double,
        iconName: String? = nil,
        colorName: String? = nil
    ) {
        self.entityId = entityId
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.radius = radius
        self.iconName = iconName
        self.colorName = colorName
    }
}

public struct RenderedHistoryGraph: Sendable {
    public var entityId: String
    public var name: String
    public var dataPoints: [HistoryDataPoint]

    public init(entityId: String, name: String, dataPoints: [HistoryDataPoint] = []) {
        self.entityId = entityId
        self.name = name
        self.dataPoints = dataPoints
    }
}

public struct HistoryDataPoint: Sendable {
    public var timestamp: Date
    public var value: Double

    public init(timestamp: Date, value: Double) {
        self.timestamp = timestamp
        self.value = value
    }
}
