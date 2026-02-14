import Testing
@testable import HAWatchCore

@Suite("TemplateService Parsing")
struct TemplateServiceTests {
    // MARK: - Entity state parsing (fetchEntityStates output format)

    @Test("Entity state with entity_picture is parsed correctly")
    func entityStateWithEntityPicture() {
        // Simulate the template output format that fetchEntityStates produces
        // entity_id|||state|||name|||unit|||icon|||device_class|||entity_picture
        let state = EntityState(
            entityId: "person.john",
            state: "home",
            name: "John",
            unit: "",
            icon: "mdi:account",
            deviceClass: "",
            attributes: ["entity_picture": "/local/john.jpg"]
        )
        #expect(state.attributes["entity_picture"] == "/local/john.jpg")
    }

    @Test("Entity state without entity_picture has empty attributes")
    func entityStateWithoutEntityPicture() {
        let state = EntityState(
            entityId: "sensor.temp",
            state: "22.5",
            name: "Temperature",
            unit: "°C",
            icon: "mdi:thermometer",
            deviceClass: "temperature"
        )
        #expect(state.attributes["entity_picture"] == nil)
        #expect(state.attributes.isEmpty)
    }

    @Test("EntityState displayName fallback from entity_id")
    func displayNameFallback() {
        let state = EntityState(entityId: "sensor.living_room_temp", state: "22")
        #expect(state.displayName == "Living Room Temp")
    }

    @Test("EntityState domain extraction")
    func domainExtraction() {
        let state = EntityState(entityId: "binary_sensor.front_door", state: "on")
        #expect(state.domain == "binary_sensor")
    }
}
