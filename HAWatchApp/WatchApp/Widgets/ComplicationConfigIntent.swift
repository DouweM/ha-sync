import AppIntents
import HAWatchCore

struct EntityComplicationIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Entity"
    static var description = IntentDescription("Select an entity to display")

    @Parameter(title: "Entity ID")
    var entityId: String?

    @Parameter(title: "Entity Name")
    var entityName: String?

    init() {}

    init(entityId: String, entityName: String) {
        self.entityId = entityId
        self.entityName = entityName
    }
}
