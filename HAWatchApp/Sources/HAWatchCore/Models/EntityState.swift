import Foundation

public struct EntityState: Codable, Sendable {
    public var entityId: String
    public var state: String
    public var name: String
    public var unit: String
    public var icon: String
    public var deviceClass: String
    public var lastChanged: Date?
    public var attributes: [String: String]

    public init(
        entityId: String,
        state: String,
        name: String = "",
        unit: String = "",
        icon: String = "",
        deviceClass: String = "",
        lastChanged: Date? = nil,
        attributes: [String: String] = [:]
    ) {
        self.entityId = entityId
        self.state = state
        self.name = name
        self.unit = unit
        self.icon = icon
        self.deviceClass = deviceClass
        self.lastChanged = lastChanged
        self.attributes = attributes
    }

    public var domain: String {
        entityId.split(separator: ".").first.map(String.init) ?? ""
    }

    public var displayName: String {
        if !name.isEmpty { return name }
        let objectId = entityId.split(separator: ".").dropFirst().joined(separator: ".")
        return objectId.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
