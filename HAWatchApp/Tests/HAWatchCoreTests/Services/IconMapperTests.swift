import Testing
@testable import HAWatchCore

@Suite("IconMapper")
struct IconMapperTests {
    let mapper = IconMapper.shared

    // MARK: - Direct MDI lookups

    @Test("Direct MDI -> SF Symbol for lighting icons")
    func lightingIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:lightbulb") == "lightbulb.fill")
        #expect(mapper.sfSymbolName(for: "mdi:ceiling-light") == "lamp.ceiling.fill")
        #expect(mapper.sfSymbolName(for: "mdi:floor-lamp") == "lamp.floor.fill")
        #expect(mapper.sfSymbolName(for: "mdi:desk-lamp") == "lamp.desk.fill")
        #expect(mapper.sfSymbolName(for: "mdi:led-strip") == "light.strip.leftright.fill")
        #expect(mapper.sfSymbolName(for: "mdi:track-light") == "light.recessed.fill")
    }

    @Test("Direct MDI -> SF Symbol for door/window icons")
    func doorWindowIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:door") == "door.left.hand.closed")
        #expect(mapper.sfSymbolName(for: "mdi:door-open") == "door.left.hand.open")
        #expect(mapper.sfSymbolName(for: "mdi:garage-variant") == "door.garage.closed")
        #expect(mapper.sfSymbolName(for: "mdi:garage-open-variant") == "door.garage.open")
        #expect(mapper.sfSymbolName(for: "mdi:window-closed") == "window.vertical.closed")
        #expect(mapper.sfSymbolName(for: "mdi:window-open") == "window.vertical.open")
    }

    @Test("Direct MDI -> SF Symbol for climate icons")
    func climateIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:fan") == "fan.fill")
        #expect(mapper.sfSymbolName(for: "mdi:thermometer") == "thermometer.medium")
        #expect(mapper.sfSymbolName(for: "mdi:air-conditioner") == "snowflake")
        #expect(mapper.sfSymbolName(for: "mdi:radiator") == "flame.fill")
    }

    @Test("Direct MDI -> SF Symbol for weather icons")
    func weatherIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:weather-sunny") == "sun.max.fill")
        #expect(mapper.sfSymbolName(for: "mdi:weather-rainy") == "cloud.rain.fill")
        #expect(mapper.sfSymbolName(for: "mdi:weather-snowy") == "cloud.snow.fill")
        #expect(mapper.sfSymbolName(for: "mdi:weather-fog") == "cloud.fog.fill")
    }

    @Test("Direct MDI -> SF Symbol for security icons")
    func securityIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:lock") == "lock.fill")
        #expect(mapper.sfSymbolName(for: "mdi:shield") == "shield.fill")
        #expect(mapper.sfSymbolName(for: "mdi:cctv") == "video.fill")
        #expect(mapper.sfSymbolName(for: "mdi:bell") == "bell.fill")
    }

    @Test("Direct MDI -> SF Symbol for appliance icons")
    func applianceIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:washing-machine") == "washer.fill")
        #expect(mapper.sfSymbolName(for: "mdi:tumble-dryer") == "dryer.fill")
        #expect(mapper.sfSymbolName(for: "mdi:robot-vacuum") == "robot.fill")
        #expect(mapper.sfSymbolName(for: "mdi:stove") == "stove.fill")
    }

    @Test("Direct MDI -> SF Symbol for media icons")
    func mediaIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:television") == "tv.fill")
        #expect(mapper.sfSymbolName(for: "mdi:speaker") == "hifispeaker.fill")
        #expect(mapper.sfSymbolName(for: "mdi:play") == "play.fill")
        #expect(mapper.sfSymbolName(for: "mdi:music") == "music.note")
    }

    @Test("Direct MDI -> SF Symbol for people/pet icons")
    func peoplePetIcons() {
        #expect(mapper.sfSymbolName(for: "mdi:account") == "person.fill")
        #expect(mapper.sfSymbolName(for: "mdi:account-group") == "person.2.fill")
        #expect(mapper.sfSymbolName(for: "mdi:cat") == "cat.fill")
        #expect(mapper.sfSymbolName(for: "mdi:dog") == "dog.fill")
    }

    // MARK: - Case insensitivity

    @Test("MDI prefix is stripped case-insensitively")
    func caseInsensitive() {
        #expect(mapper.sfSymbolName(for: "MDI:lightbulb") == "lightbulb.fill")
        #expect(mapper.sfSymbolName(for: "Mdi:Lock") == "lock.fill")
    }

    // MARK: - Partial match fallback

    @Test("Partial match finds closest icon")
    func partialMatch() {
        // "lightbulb-group" contains "lightbulb"
        #expect(mapper.sfSymbolName(for: "mdi:lightbulb-group") == "lightbulb.2.fill")
    }

    // MARK: - Domain fallback

    @Test("Domain fallback when no icon provided")
    func domainFallback() {
        #expect(mapper.sfSymbolName(for: nil, entityId: "light.test") == "lightbulb.fill")
        #expect(mapper.sfSymbolName(for: nil, entityId: "person.john") == "person.fill")
        #expect(mapper.sfSymbolName(for: nil, entityId: "climate.hvac") == "thermometer.medium")
        #expect(mapper.sfSymbolName(for: nil, entityId: "lock.front_door") == "lock.fill")
    }

    @Test("Empty icon string uses domain fallback")
    func emptyIconString() {
        #expect(mapper.sfSymbolName(for: "", entityId: "light.test") == "lightbulb.fill")
    }

    // MARK: - Device class fallback

    @Test("Device class fallback")
    func deviceClassFallback() {
        #expect(mapper.sfSymbolName(for: nil, entityId: "sensor.temp", deviceClass: "temperature") == "thermometer.medium")
        #expect(mapper.sfSymbolName(for: nil, entityId: "sensor.humidity", deviceClass: "humidity") == "humidity.fill")
        #expect(mapper.sfSymbolName(for: nil, entityId: "binary_sensor.door", deviceClass: "door") == "door.left.hand.closed")
    }

    // MARK: - Last resort fallback

    @Test("Unknown icon falls back to circle.fill")
    func unknownFallback() {
        #expect(mapper.sfSymbolName(for: "mdi:totally-unknown-icon-xyz") == "circle.fill")
    }

    @Test("No icon and no entity falls back to circle.fill")
    func noInfoFallback() {
        #expect(mapper.sfSymbolName(for: nil) == "circle.fill")
    }

    // MARK: - Weather conditions

    @Test("Weather condition symbols")
    func weatherConditions() {
        #expect(mapper.weatherSymbolName(for: "sunny") == "sun.max.fill")
        #expect(mapper.weatherSymbolName(for: "cloudy") == "cloud.fill")
        #expect(mapper.weatherSymbolName(for: "rainy") == "cloud.rain.fill")
        #expect(mapper.weatherSymbolName(for: "partlycloudy") == "cloud.sun.fill")
        #expect(mapper.weatherSymbolName(for: "clear-night") == "moon.stars.fill")
        #expect(mapper.weatherSymbolName(for: "snowy") == "cloud.snow.fill")
    }

    @Test("Unknown weather condition falls back to cloud.fill")
    func unknownWeather() {
        #expect(mapper.weatherSymbolName(for: "unknown") == "cloud.fill")
    }
}
