/// Maps MDI (Material Design Icons) names to SF Symbol names.
/// Pure string-to-string mapping with no Apple framework dependencies.
public struct IconMapper: Sendable {
    public static let shared = IconMapper()

    // MARK: - Direct MDI -> SF Symbol mapping

    private let mdiToSFSymbol: [String: String] = [
        // Home / Building
        "home": "house.fill",
        "home-circle": "house.circle.fill",
        "home-heart": "house.fill",
        "house": "house.fill",
        "home-account": "person.2.fill",

        // People
        "account": "person.fill",
        "account-group": "person.2.fill",
        "account-multiple": "person.2.fill",
        "human": "person.fill",
        "face-man": "person.fill",
        "face-woman": "person.fill",
        "face": "person.fill",
        "baby-face": "face.smiling",
        "baby-face-outline": "face.smiling",
        "baby-buggy": "stroller.fill",
        "baby-carriage": "stroller.fill",
        "stroller": "stroller.fill",

        // Pets
        "cat": "cat.fill",
        "cats": "cat.fill",
        "dog": "dog.fill",
        "paw": "pawprint.fill",
        "fishbowl": "fish.fill",
        "fishbowl-outline": "fish.fill",

        // Lighting
        "lightbulb": "lightbulb.fill",
        "lightbulb-outline": "lightbulb",
        "lightbulb-group": "lightbulb.2.fill",
        "light": "lightbulb.fill",
        "lamp": "lamp.desk.fill",
        "lamp-outline": "lamp.desk",
        "floor-lamp": "lamp.floor.fill",
        "floor-lamp-dual": "lamp.floor.fill",
        "desk-lamp": "lamp.desk.fill",
        "ceiling-light": "lamp.ceiling.fill",
        "ceiling-fan-light": "lamp.ceiling.fill",
        "track-light": "light.recessed.fill",
        "led-strip": "light.strip.leftright.fill",
        "led-strip-variant": "light.strip.leftright.fill",
        "pillar": "light.cylindrical.ceiling.fill",
        "wall-sconce": "light.panel.fill",
        "wall-sconce-round": "light.panel.fill",
        "outdoor-lamp": "lamp.floor.fill",
        "string-lights": "light.strip.leftright.fill",
        "looks": "sparkles",

        // Doors / Windows
        "door": "door.left.hand.closed",
        "door-open": "door.left.hand.open",
        "door-closed": "door.left.hand.closed",
        "door-closed-lock": "door.left.hand.closed",
        "garage-variant": "door.garage.closed",
        "garage-variant-lock": "door.garage.closed",
        "garage-open-variant": "door.garage.open",
        "window-closed": "window.vertical.closed",
        "window-closed-variant": "window.vertical.closed",
        "window-open": "window.vertical.open",
        "window-open-variant": "window.vertical.open",
        "blinds": "blinds.vertical.closed",
        "blinds-open": "blinds.vertical.open",
        "roller-shade": "blinds.vertical.closed",
        "roller-shade-closed": "blinds.vertical.closed",
        "curtains": "curtains.closed",
        "curtains-closed": "curtains.closed",

        // Climate / HVAC
        "fan": "fan.fill",
        "fan-off": "fan",
        "ceiling-fan": "fan.ceiling.fill",
        "thermometer": "thermometer.medium",
        "thermometer-high": "thermometer.high",
        "thermometer-low": "thermometer.low",
        "home-thermometer": "thermometer.medium",
        "home-thermometer-outline": "thermometer.medium",
        "water-thermometer": "thermometer.medium",
        "coolant-temperature": "thermometer.medium",
        "heat-pump": "thermometer.medium",
        "hvac": "thermometer.medium",
        "air-conditioner": "snowflake",
        "snowflake": "snowflake",
        "fire": "flame.fill",
        "radiator": "flame.fill",
        "radiator-off": "flame",
        "heating-coil": "flame.fill",

        // Weather
        "weather-sunny": "sun.max.fill",
        "weather-night": "moon.fill",
        "weather-cloudy": "cloud.fill",
        "weather-partly-cloudy": "cloud.sun.fill",
        "weather-partly-rainy": "cloud.sun.rain.fill",
        "weather-rainy": "cloud.rain.fill",
        "weather-pouring": "cloud.heavyrain.fill",
        "weather-snowy": "cloud.snow.fill",
        "weather-snowy-rainy": "cloud.sleet.fill",
        "weather-fog": "cloud.fog.fill",
        "weather-hazy": "sun.haze.fill",
        "weather-windy": "wind",
        "weather-windy-variant": "wind",
        "weather-lightning": "cloud.bolt.fill",
        "weather-lightning-rainy": "cloud.bolt.rain.fill",
        "weather-tornado": "tornado",
        "weather-hurricane": "hurricane",
        "weather-sunset-up": "sunrise.fill",
        "weather-sunset-down": "sunset.fill",
        "sun-clock": "sun.max.fill",
        "sun-wireless": "sun.max.fill",
        "sun-wireless-outline": "sun.max.fill",

        // Security
        "lock": "lock.fill",
        "lock-open": "lock.open.fill",
        "lock-smart": "lock.fill",
        "lock-outline": "lock",
        "shield": "shield.fill",
        "shield-home": "shield.fill",
        "shield-moon": "moon.fill",
        "shield-sun": "sun.max.fill",
        "alarm-panel": "bell.shield.fill",
        "cctv": "video.fill",
        "webcam": "camera.fill",
        "bell": "bell.fill",
        "bell-ring": "bell.badge.fill",
        "motion-sensor": "sensor.fill",

        // Appliances
        "washing-machine": "washer.fill",
        "tumble-dryer": "dryer.fill",
        "dryer": "dryer.fill",
        "dishwasher": "dishwasher.fill",
        "stove": "stove.fill",
        "oven": "oven.fill",
        "microwave": "microwave.fill",
        "fridge": "refrigerator.fill",
        "fridge-outline": "refrigerator",
        "robot-vacuum": "robot.fill",
        "robot": "robot.fill",
        "hot-tub": "bathtub.fill",
        "shower": "shower.fill",

        // Media
        "television": "tv.fill",
        "tv": "tv.fill",
        "desktop-tower-monitor": "desktopcomputer",
        "monitor": "display",
        "speaker": "hifispeaker.fill",
        "speaker-wireless": "hifispeaker.fill",
        "music": "music.note",
        "play": "play.fill",
        "pause": "pause.fill",
        "stop": "stop.fill",
        "plex": "play.fill",
        "hdmi-port": "tv.fill",
        "video-input-hdmi": "tv.fill",
        "controller": "gamecontroller.fill",
        "volume": "speaker.wave.2.fill",
        "volume-high": "speaker.wave.3.fill",
        "volume-off": "speaker.slash.fill",

        // Network / Connectivity
        "wifi": "wifi",
        "wifi-off": "wifi.slash",
        "access-point": "wifi.router.fill",
        "access-point-network": "wifi.router.fill",
        "server": "server.rack",
        "printer": "printer.fill",
        "printer-3d": "printer.fill",
        "cellphone": "iphone",
        "phone": "phone.fill",
        "devices": "laptopcomputer.and.iphone",

        // Navigation / Location
        "map": "map.fill",
        "map-marker": "mappin.circle.fill",
        "home-map-marker": "mappin.circle.fill",
        "pin": "mappin",
        "pin-outline": "mappin",
        "airplane": "airplane",

        // Power / Energy
        "power-plug": "powerplug.fill",
        "power-plug-battery": "battery.100.bolt",
        "power-socket": "powerplug.fill",
        "ev-station": "ev.plug.dc.ccs1",
        "battery": "battery.100",
        "battery-charging": "battery.100.bolt",
        "battery-low": "battery.25",
        "battery-medium": "battery.50",
        "battery-high": "battery.75",
        "lightning-bolt": "bolt.fill",
        "solar-power": "sun.max.fill",
        "solar-power-variant": "sun.max.fill",
        "solar-panel": "sun.max.fill",
        "transmission-tower": "bolt.fill",
        "home-lightning-bolt": "house.fill",
        "home-lightning-bolt-outline": "house.fill",

        // Transport
        "car": "car.fill",
        "car-estate": "car.fill",
        "car-door": "car.fill",
        "car-tire-alert": "car.fill",
        "gas-station": "fuelpump.fill",
        "fuel": "fuelpump.fill",

        // Misc
        "sofa": "sofa.fill",
        "bed": "bed.double.fill",
        "bed-outline": "bed.double",
        "bed-king": "bed.double.fill",
        "hanger": "tshirt.fill",
        "glass-cocktail": "wineglass.fill",
        "fountain": "drop.fill",
        "tree": "tree.fill",
        "flower": "leaf.fill",
        "greenhouse": "leaf.fill",
        "water": "drop.fill",
        "water-pump": "drop.fill",
        "waves": "water.waves",
        "air-filter": "aqi.medium",
        "air-purifier": "aqi.medium",
        "gauge": "gauge.with.needle.fill",
        "gauge-empty": "gauge.with.needle",
        "gauge-full": "gauge.with.needle.fill",
        "history": "clock.arrow.circlepath",
        "time": "clock.fill",
        "video": "video.fill",
        "video-off": "video.slash.fill",
        "format-list-bulleted-type": "list.bullet",
        "launch": "arrow.up.right.square",
        "account-question": "questionmark.circle.fill",
        "account-check": "checkmark.circle.fill",
        "rotate": "arrow.triangle.2.circlepath",
        "rotate-3d": "arrow.triangle.2.circlepath",
        "party-popper": "party.popper.fill",
        "exit-run": "figure.walk",
        "run": "figure.run",
        "home-export-outline": "figure.walk",
        "account-arrow-right": "figure.walk",
        "select": "list.bullet",
        "input-boolean": "togglepower",
        "button": "button.horizontal.fill",
        "input-select": "list.bullet",
        "input-button": "button.horizontal.fill",
    ]

    // MARK: - Domain -> SF Symbol fallback

    private let domainToSFSymbol: [String: String] = [
        "person": "person.fill",
        "light": "lightbulb.fill",
        "switch": "powerplug.fill",
        "fan": "fan.fill",
        "climate": "thermometer.medium",
        "lock": "lock.fill",
        "cover": "door.left.hand.closed",
        "sensor": "gauge.with.needle.fill",
        "binary_sensor": "bolt.fill",
        "camera": "video.fill",
        "media_player": "tv.fill",
        "alarm_control_panel": "shield.fill",
        "input_boolean": "togglepower",
        "weather": "sun.max.fill",
        "input_datetime": "clock.fill",
        "input_number": "number",
        "zone": "mappin.circle.fill",
        "device_tracker": "mappin.circle.fill",
        "image": "photo",
        "select": "list.bullet",
        "button": "button.horizontal.fill",
        "number": "number",
        "vacuum": "robot.fill",
        "input_select": "list.bullet",
        "input_button": "button.horizontal.fill",
        "automation": "gearshape.fill",
        "script": "scroll.fill",
        "scene": "theatermasks.fill",
        "group": "rectangle.3.group.fill",
        "timer": "timer",
        "counter": "number.circle.fill",
        "update": "arrow.down.circle.fill",
        "remote": "appletvremote.gen4.fill",
        "siren": "megaphone.fill",
        "water_heater": "flame.fill",
        "humidifier": "humidity.fill",
    ]

    // MARK: - Device class -> SF Symbol fallback

    private let deviceClassToSFSymbol: [String: String] = [
        "temperature": "thermometer.medium",
        "humidity": "humidity.fill",
        "battery": "battery.100",
        "power": "bolt.fill",
        "energy": "bolt.fill",
        "voltage": "bolt.fill",
        "current": "bolt.fill",
        "illuminance": "sun.max.fill",
        "pressure": "gauge.with.needle.fill",
        "carbon_dioxide": "aqi.medium",
        "carbon_monoxide": "aqi.medium",
        "pm25": "aqi.medium",
        "pm10": "aqi.medium",
        "volatile_organic_compounds": "aqi.medium",
        "nitrogen_dioxide": "aqi.medium",
        "motion": "figure.walk",
        "occupancy": "person.fill",
        "door": "door.left.hand.closed",
        "window": "window.vertical.closed",
        "moisture": "drop.fill",
        "gas": "flame.fill",
        "connectivity": "wifi",
        "plug": "powerplug.fill",
        "problem": "exclamationmark.triangle.fill",
        "safety": "exclamationmark.shield.fill",
        "sound": "speaker.wave.2.fill",
        "vibration": "waveform",
        "opening": "door.left.hand.open",
        "garage_door": "door.garage.closed",
    ]

    // MARK: - Weather condition -> SF Symbol

    private let weatherConditionToSFSymbol: [String: String] = [
        "clear-night": "moon.stars.fill",
        "cloudy": "cloud.fill",
        "exceptional": "exclamationmark.triangle.fill",
        "fog": "cloud.fog.fill",
        "hail": "cloud.hail.fill",
        "lightning": "cloud.bolt.fill",
        "lightning-rainy": "cloud.bolt.rain.fill",
        "partlycloudy": "cloud.sun.fill",
        "pouring": "cloud.heavyrain.fill",
        "rainy": "cloud.rain.fill",
        "snowy": "cloud.snow.fill",
        "snowy-rainy": "cloud.sleet.fill",
        "sunny": "sun.max.fill",
        "windy": "wind",
        "windy-variant": "wind",
    ]

    public init() {}

    /// Map an MDI icon name to an SF Symbol name.
    /// - Parameters:
    ///   - icon: The MDI icon string (e.g. "mdi:lightbulb" or "lightbulb")
    ///   - entityId: Optional entity ID for domain/device-class fallback
    ///   - deviceClass: Optional device class for fallback
    /// - Returns: SF Symbol name string
    public func sfSymbolName(
        for icon: String?,
        entityId: String? = nil,
        deviceClass: String? = nil
    ) -> String {
        // If no icon given, try device class and domain fallbacks
        guard let icon = icon, !icon.isEmpty else {
            if let dc = deviceClass, !dc.isEmpty, let symbol = deviceClassToSFSymbol[dc] {
                return symbol
            }
            if let eid = entityId {
                let domain = eid.split(separator: ".").first.map(String.init) ?? ""
                return domainToSFSymbol[domain] ?? "circle.fill"
            }
            return "circle.fill"
        }

        let iconName = icon
            .replacingOccurrences(of: "mdi:", with: "")
            .lowercased()

        // 1. Direct lookup
        if let symbol = mdiToSFSymbol[iconName] {
            return symbol
        }

        // 2. Partial match (substring)
        for (key, symbol) in mdiToSFSymbol {
            if iconName.contains(key) || key.contains(iconName) {
                return symbol
            }
        }

        // 3. Device class fallback
        if let dc = deviceClass, !dc.isEmpty, let symbol = deviceClassToSFSymbol[dc] {
            return symbol
        }

        // 4. Domain fallback
        if let eid = entityId {
            let domain = eid.split(separator: ".").first.map(String.init) ?? ""
            if let symbol = domainToSFSymbol[domain] {
                return symbol
            }
        }

        // 5. Last resort
        return "circle.fill"
    }

    /// Get SF Symbol for a weather condition string.
    public func weatherSymbolName(for condition: String) -> String {
        weatherConditionToSFSymbol[condition] ?? "cloud.fill"
    }
}
