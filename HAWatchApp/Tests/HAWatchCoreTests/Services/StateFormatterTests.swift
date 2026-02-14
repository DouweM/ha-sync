import Testing
@testable import HAWatchCore

@Suite("StateFormatter")
struct StateFormatterTests {
    let formatter = StateFormatter.shared

    // MARK: - Person

    @Test("Person home state")
    func personHome() {
        let result = formatter.format(entityId: "person.john", state: "home")
        #expect(result.text == "Home")
        #expect(result.color == .green)
    }

    @Test("Person away state")
    func personAway() {
        let result = formatter.format(entityId: "person.john", state: "not_home")
        #expect(result.text == "Away")
        #expect(result.color == .dim)
    }

    @Test("Person at named location")
    func personNamedLocation() {
        let result = formatter.format(entityId: "person.john", state: "work")
        #expect(result.text == "work")
        #expect(result.color == .cyan)
    }

    // MARK: - Lock

    @Test("Lock locked state")
    func lockLocked() {
        let result = formatter.format(entityId: "lock.front_door", state: "locked")
        #expect(result.text == "Locked")
        #expect(result.color == .green)
    }

    @Test("Lock unlocked state")
    func lockUnlocked() {
        let result = formatter.format(entityId: "lock.front_door", state: "unlocked")
        #expect(result.text == "Unlocked")
        #expect(result.color == .red)
    }

    // MARK: - Cover

    @Test("Cover closed state")
    func coverClosed() {
        let result = formatter.format(entityId: "cover.garage", state: "closed")
        #expect(result.text == "Closed")
        #expect(result.color == .green)
    }

    @Test("Cover open state")
    func coverOpen() {
        let result = formatter.format(entityId: "cover.garage", state: "open")
        #expect(result.text == "Open")
        #expect(result.color == .yellow)
    }

    // MARK: - Binary sensor

    @Test("Binary sensor door open")
    func doorOpen() {
        let result = formatter.format(entityId: "binary_sensor.front_door", state: "on", deviceClass: "door")
        #expect(result.text == "Open")
        #expect(result.color == .yellow)
    }

    @Test("Binary sensor door closed")
    func doorClosed() {
        let result = formatter.format(entityId: "binary_sensor.front_door", state: "off", deviceClass: "door")
        #expect(result.text == "Closed")
        #expect(result.color == .green)
    }

    @Test("Binary sensor motion detected")
    func motionDetected() {
        let result = formatter.format(entityId: "binary_sensor.hallway", state: "on", deviceClass: "motion")
        #expect(result.text == "Motion")
        #expect(result.color == .yellow)
    }

    @Test("Binary sensor motion clear")
    func motionClear() {
        let result = formatter.format(entityId: "binary_sensor.hallway", state: "off", deviceClass: "motion")
        #expect(result.text == "Clear")
        #expect(result.color == .dim)
    }

    @Test("Binary sensor occupancy")
    func occupancy() {
        let result = formatter.format(entityId: "binary_sensor.room", state: "on", deviceClass: "occupancy")
        #expect(result.text == "Occupied")
        #expect(result.color == .yellow)
    }

    @Test("Binary sensor connectivity")
    func connectivity() {
        let result = formatter.format(entityId: "binary_sensor.router", state: "on", deviceClass: "connectivity")
        #expect(result.text == "Connected")
        #expect(result.color == .green)
    }

    @Test("Binary sensor battery low")
    func batteryLow() {
        let result = formatter.format(entityId: "binary_sensor.sensor_battery", state: "on", deviceClass: "battery")
        #expect(result.text == "Low")
        #expect(result.color == .red)
    }

    @Test("Binary sensor problem")
    func problem() {
        let result = formatter.format(entityId: "binary_sensor.washer", state: "on", deviceClass: "problem")
        #expect(result.text == "Problem")
        #expect(result.color == .red)
    }

    @Test("Binary sensor generic on/off")
    func genericBinary() {
        let resultOn = formatter.format(entityId: "binary_sensor.test", state: "on")
        #expect(resultOn.text == "On")
        #expect(resultOn.color == .yellow)

        let resultOff = formatter.format(entityId: "binary_sensor.test", state: "off")
        #expect(resultOff.text == "Off")
        #expect(resultOff.color == .dim)
    }

    // MARK: - Light / Switch / Fan

    @Test("Light on/off")
    func lightOnOff() {
        let on = formatter.format(entityId: "light.living_room", state: "on")
        #expect(on.text == "On")
        #expect(on.color == .yellow)

        let off = formatter.format(entityId: "light.living_room", state: "off")
        #expect(off.text == "Off")
        #expect(off.color == .dim)
    }

    @Test("Switch on/off")
    func switchOnOff() {
        let on = formatter.format(entityId: "switch.pump", state: "on")
        #expect(on.text == "On")
        #expect(on.color == .yellow)
    }

    @Test("Fan on/off")
    func fanOnOff() {
        let on = formatter.format(entityId: "fan.bedroom", state: "on")
        #expect(on.text == "On")
        #expect(on.color == .yellow)
    }

    @Test("Input boolean on/off")
    func inputBooleanOnOff() {
        let on = formatter.format(entityId: "input_boolean.guest_mode", state: "on")
        #expect(on.text == "On")
        #expect(on.color == .yellow)
    }

    // MARK: - Alarm

    @Test("Alarm states")
    func alarmStates() {
        #expect(formatter.format(entityId: "alarm_control_panel.home", state: "disarmed").text == "Disarmed")
        #expect(formatter.format(entityId: "alarm_control_panel.home", state: "armed_home").text == "Armed")
        #expect(formatter.format(entityId: "alarm_control_panel.home", state: "armed_away").text == "Armed")

        let triggered = formatter.format(entityId: "alarm_control_panel.home", state: "triggered")
        #expect(triggered.text == "TRIGGERED")
        #expect(triggered.color == .red)
    }

    // MARK: - Climate

    @Test("Climate states")
    func climateStates() {
        let heat = formatter.format(entityId: "climate.living_room", state: "heat")
        #expect(heat.text == "Heating")
        #expect(heat.color == .red)

        let cool = formatter.format(entityId: "climate.living_room", state: "cool")
        #expect(cool.text == "Cooling")
        #expect(cool.color == .blue)

        let auto = formatter.format(entityId: "climate.living_room", state: "auto")
        #expect(auto.text == "Auto")
        #expect(auto.color == .cyan)
    }

    // MARK: - Sensor

    @Test("Sensor with integer value")
    func sensorInteger() {
        let result = formatter.format(entityId: "sensor.temperature", state: "23.0", unit: "°C")
        #expect(result.text == "23°C")
    }

    @Test("Sensor with decimal value")
    func sensorDecimal() {
        let result = formatter.format(entityId: "sensor.humidity", state: "45.7", unit: "%")
        #expect(result.text == "45.7%")
    }

    @Test("Sensor with no unit")
    func sensorNoUnit() {
        let result = formatter.format(entityId: "sensor.count", state: "42")
        #expect(result.text == "42")
    }

    @Test("Sensor with non-numeric state")
    func sensorNonNumeric() {
        let result = formatter.format(entityId: "sensor.status", state: "active")
        #expect(result.text == "active")
    }

    // MARK: - Weather

    @Test("Weather state formatting")
    func weatherState() {
        let result = formatter.format(entityId: "weather.home", state: "sunny")
        #expect(result.text == "Sunny")
        #expect(result.color == .cyan)
    }

    @Test("Weather partly cloudy")
    func weatherPartlyCloudy() {
        let result = formatter.format(entityId: "weather.home", state: "partlycloudy")
        #expect(result.color == .cyan)
    }

    // MARK: - Unavailable / Unknown

    @Test("Unavailable state")
    func unavailable() {
        let result = formatter.format(entityId: "light.test", state: "unavailable")
        #expect(result.text == "?")
        #expect(result.color == .dim)
    }

    @Test("Unknown state")
    func unknown() {
        let result = formatter.format(entityId: "light.test", state: "unknown")
        #expect(result.text == "?")
        #expect(result.color == .dim)
    }

    // MARK: - Image

    @Test("Image returns empty text")
    func imageState() {
        let result = formatter.format(entityId: "image.photo", state: "2024-01-01")
        #expect(result.text == "")
    }
}
