import Foundation

// MARK: - Dashboard Config (from WebSocket lovelace/config)

public struct DashboardConfig: Codable, Sendable {
    public var views: [ViewConfig]

    public init(views: [ViewConfig]) {
        self.views = views
    }
}

public struct ViewConfig: Codable, Sendable {
    public var title: String?
    public var path: String?
    public var icon: String?
    public var badges: [BadgeConfig]?
    public var sections: [SectionConfig]?
    public var type: String?
    public var visibility: [VisibilityCondition]?

    public init(
        title: String? = nil,
        path: String? = nil,
        icon: String? = nil,
        badges: [BadgeConfig]? = nil,
        sections: [SectionConfig]? = nil,
        type: String? = nil,
        visibility: [VisibilityCondition]? = nil
    ) {
        self.title = title
        self.path = path
        self.icon = icon
        self.badges = badges
        self.sections = sections
        self.type = type
        self.visibility = visibility
    }
}

public struct SectionConfig: Codable, Sendable {
    public var title: String?
    public var cards: [CardConfig]?
    public var visibility: [VisibilityCondition]?

    public init(
        title: String? = nil,
        cards: [CardConfig]? = nil,
        visibility: [VisibilityCondition]? = nil
    ) {
        self.title = title
        self.cards = cards
        self.visibility = visibility
    }
}

/// Box wrapper for recursive value types.
public final class Indirect<T: Codable & Sendable>: @unchecked Sendable, Codable {
    public let value: T

    public init(_ value: T) { self.value = value }

    public convenience init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        try self.init(container.decode(T.self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(value)
    }
}

public struct CardConfig: Codable, Sendable {
    public var type: String
    public var entity: String?
    public var name: String?
    public var icon: String?
    public var heading: String?
    public var badges: [BadgeConfig]?
    public var visibility: [VisibilityCondition]?
    public var gridOptions: GridOptions?
    public var showState: Bool?
    public var showIcon: Bool?
    public var stateContent: String?

    // auto-entities
    public var filter: AutoEntitiesFilter?
    private var _card: Indirect<CardConfig>?
    public var card: CardConfig? {
        get { _card?.value }
        set { _card = newValue.map { Indirect($0) } }
    }

    // logbook
    public var target: LogbookTarget?
    public var entities: [String]?

    // weather
    public var showForecast: Bool?

    // map card
    public var mapCardEntities: [MapEntity]?
    public var darkMode: Bool?
    public var focusEntity: String?
    public var historyStart: String?
    public var plugins: [MapPlugin]?

    // picture-entity (camera)
    public var cameraImage: String?

    // history-graph
    public var hoursToShow: Int?

    enum CodingKeys: String, CodingKey {
        case type, entity, name, icon, heading, badges, visibility
        case gridOptions = "grid_options"
        case showState = "show_state"
        case showIcon = "show_icon"
        case stateContent = "state_content"
        case filter
        case _card = "card"
        case target, entities
        case showForecast = "show_forecast"
        case mapCardEntities = "entities_config"
        case darkMode = "dark_mode"
        case focusEntity = "focus_entity"
        case historyStart = "history_start"
        case plugins
        case cameraImage = "camera_image"
        case hoursToShow = "hours_to_show"
    }

    public init(
        type: String,
        entity: String? = nil,
        name: String? = nil,
        icon: String? = nil,
        heading: String? = nil,
        badges: [BadgeConfig]? = nil,
        visibility: [VisibilityCondition]? = nil,
        gridOptions: GridOptions? = nil,
        showState: Bool? = nil,
        showIcon: Bool? = nil,
        stateContent: String? = nil,
        filter: AutoEntitiesFilter? = nil,
        card: CardConfig? = nil,
        target: LogbookTarget? = nil,
        entities: [String]? = nil,
        showForecast: Bool? = nil,
        mapCardEntities: [MapEntity]? = nil,
        darkMode: Bool? = nil,
        focusEntity: String? = nil,
        historyStart: String? = nil,
        plugins: [MapPlugin]? = nil,
        cameraImage: String? = nil,
        hoursToShow: Int? = nil
    ) {
        self.type = type
        self.entity = entity
        self.name = name
        self.icon = icon
        self.heading = heading
        self.badges = badges
        self.visibility = visibility
        self.gridOptions = gridOptions
        self.showState = showState
        self.showIcon = showIcon
        self.stateContent = stateContent
        self.filter = filter
        self._card = card.map { Indirect($0) }
        self.target = target
        self.entities = entities
        self.showForecast = showForecast
        self.mapCardEntities = mapCardEntities
        self.darkMode = darkMode
        self.focusEntity = focusEntity
        self.historyStart = historyStart
        self.plugins = plugins
        self.cameraImage = cameraImage
        self.hoursToShow = hoursToShow
    }
}

public struct GridOptions: Codable, Sendable {
    public var columns: Int?
    public var rows: Int?

    public init(columns: Int? = nil, rows: Int? = nil) {
        self.columns = columns
        self.rows = rows
    }
}

public struct BadgeConfig: Codable, Sendable {
    public var type: String?
    public var entity: String?
    public var name: String?
    public var icon: String?
    public var showState: Bool?
    public var showIcon: Bool?
    public var stateContent: String?
    public var visibility: [VisibilityCondition]?

    public var showName: Bool?

    // mushroom-template-badge
    public var content: String?
    public var label: String?
    public var color: String?
    public var picture: String?

    enum CodingKeys: String, CodingKey {
        case type, entity, name, icon, visibility, content, label, color, picture
        case showState = "show_state"
        case showIcon = "show_icon"
        case showName = "show_name"
        case stateContent = "state_content"
    }

    public init(
        type: String? = nil,
        entity: String? = nil,
        name: String? = nil,
        icon: String? = nil,
        showState: Bool? = nil,
        showIcon: Bool? = nil,
        showName: Bool? = nil,
        stateContent: String? = nil,
        visibility: [VisibilityCondition]? = nil,
        content: String? = nil,
        label: String? = nil,
        color: String? = nil,
        picture: String? = nil
    ) {
        self.type = type
        self.entity = entity
        self.name = name
        self.icon = icon
        self.showState = showState
        self.showIcon = showIcon
        self.showName = showName
        self.stateContent = stateContent
        self.visibility = visibility
        self.content = content
        self.label = label
        self.color = color
        self.picture = picture
    }
}

// MARK: - Auto-entities filter

public struct AutoEntitiesFilter: Codable, Sendable {
    public var include: [AutoEntitiesRule]?
    public var exclude: [AutoEntitiesRule]?

    public init(include: [AutoEntitiesRule]? = nil, exclude: [AutoEntitiesRule]? = nil) {
        self.include = include
        self.exclude = exclude
    }
}

public struct AutoEntitiesRule: Codable, Sendable {
    public var entityId: String?
    public var domain: String?
    public var label: String?
    public var integration: String?
    public var attributes: [String: AnyCodable]?
    public var not: AutoEntitiesNot?
    public var options: AutoEntitiesOptions?

    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id"
        case domain, label, integration, attributes, not, options
    }

    public init(
        entityId: String? = nil,
        domain: String? = nil,
        label: String? = nil,
        integration: String? = nil,
        attributes: [String: AnyCodable]? = nil,
        not: AutoEntitiesNot? = nil,
        options: AutoEntitiesOptions? = nil
    ) {
        self.entityId = entityId
        self.domain = domain
        self.label = label
        self.integration = integration
        self.attributes = attributes
        self.not = not
        self.options = options
    }
}

public struct AutoEntitiesNot: Codable, Sendable {
    public var or: [AutoEntitiesCondition]?

    public init(or: [AutoEntitiesCondition]? = nil) {
        self.or = or
    }
}

public struct AutoEntitiesCondition: Codable, Sendable {
    public var state: String?
    public var label: String?

    public init(state: String? = nil, label: String? = nil) {
        self.state = state
        self.label = label
    }
}

public struct AutoEntitiesOptions: Codable, Sendable {
    public var name: String?
    public var icon: String?

    public init(name: String? = nil, icon: String? = nil) {
        self.name = name
        self.icon = icon
    }
}

// MARK: - Map card types

public struct MapEntity: Codable, Sendable {
    public var entity: String?
    public var color: String?
    public var size: Int?
    public var focus: Bool?

    public init(entity: String? = nil, color: String? = nil, size: Int? = nil, focus: Bool? = nil) {
        self.entity = entity
        self.color = color
        self.size = size
        self.focus = focus
    }
}

public struct MapPlugin: Codable, Sendable {
    public var type: String?
    public var url: String?
    public var bounds: [[Double]]?

    public init(type: String? = nil, url: String? = nil, bounds: [[Double]]? = nil) {
        self.type = type
        self.url = url
        self.bounds = bounds
    }
}

// MARK: - Logbook target

public struct LogbookTarget: Codable, Sendable {
    public var entityId: [String]?

    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id"
    }

    public init(entityId: [String]? = nil) {
        self.entityId = entityId
    }
}

// MARK: - Type-erased Codable for attributes

public struct AnyCodable: Codable, Sendable {
    public let value: AnyCodableValue

    public init(_ value: Any) {
        if let s = value as? String {
            self.value = .string(s)
        } else if let i = value as? Int {
            self.value = .int(i)
        } else if let d = value as? Double {
            self.value = .double(d)
        } else if let b = value as? Bool {
            self.value = .bool(b)
        } else {
            self.value = .string(String(describing: value))
        }
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let s = try? container.decode(String.self) {
            value = .string(s)
        } else if let i = try? container.decode(Int.self) {
            value = .int(i)
        } else if let d = try? container.decode(Double.self) {
            value = .double(d)
        } else if let b = try? container.decode(Bool.self) {
            value = .bool(b)
        } else {
            value = .string("")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case .string(let s): try container.encode(s)
        case .int(let i): try container.encode(i)
        case .double(let d): try container.encode(d)
        case .bool(let b): try container.encode(b)
        }
    }

    public var stringValue: String {
        switch value {
        case .string(let s): return s
        case .int(let i): return String(i)
        case .double(let d): return String(d)
        case .bool(let b): return String(b)
        }
    }
}

public enum AnyCodableValue: Sendable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
}
