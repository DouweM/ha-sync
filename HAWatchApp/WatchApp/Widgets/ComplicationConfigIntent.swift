import AppIntents
import HAWatchCore

struct EntityComplicationIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Entity"
    static var description = IntentDescription("Select an entity to display")

    @Parameter(title: "Entity")
    var entity: HAEntity?

    init() {}

    init(entityId: String, entityName: String) {
        self.entity = HAEntity(id: entityId, name: entityName)
    }

    /// Backward-compatible accessor for the entity ID.
    var entityId: String? {
        entity?.id
    }

    /// Backward-compatible accessor for the entity name.
    var entityName: String? {
        entity?.name
    }
}
