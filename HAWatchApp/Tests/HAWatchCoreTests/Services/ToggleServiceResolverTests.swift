import Testing
@testable import HAWatchCore

@Suite("ToggleServiceResolver")
struct ToggleServiceResolverTests {
    let resolver = ToggleServiceResolver()

    // MARK: - Lock

    @Test("Lock: locked -> unlock")
    func lockLocked() {
        let result = resolver.resolveToggleService(domain: "lock", currentState: "locked")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "lock", service: "unlock"))
    }

    @Test("Lock: unlocked -> lock")
    func lockUnlocked() {
        let result = resolver.resolveToggleService(domain: "lock", currentState: "unlocked")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "lock", service: "lock"))
    }

    // MARK: - Cover

    @Test("Cover: closed -> open_cover")
    func coverClosed() {
        let result = resolver.resolveToggleService(domain: "cover", currentState: "closed")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "cover", service: "open_cover"))
    }

    @Test("Cover: closing -> open_cover")
    func coverClosing() {
        let result = resolver.resolveToggleService(domain: "cover", currentState: "closing")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "cover", service: "open_cover"))
    }

    @Test("Cover: open -> close_cover")
    func coverOpen() {
        let result = resolver.resolveToggleService(domain: "cover", currentState: "open")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "cover", service: "close_cover"))
    }

    @Test("Cover: opening -> close_cover")
    func coverOpening() {
        let result = resolver.resolveToggleService(domain: "cover", currentState: "opening")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "cover", service: "close_cover"))
    }

    // MARK: - Climate

    @Test("Climate: off -> turn_on")
    func climateOff() {
        let result = resolver.resolveToggleService(domain: "climate", currentState: "off")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "climate", service: "turn_on"))
    }

    @Test("Climate: heat -> turn_off")
    func climateHeat() {
        let result = resolver.resolveToggleService(domain: "climate", currentState: "heat")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "climate", service: "turn_off"))
    }

    @Test("Climate: cool -> turn_off")
    func climateCool() {
        let result = resolver.resolveToggleService(domain: "climate", currentState: "cool")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "climate", service: "turn_off"))
    }

    @Test("Climate: heat_cool -> turn_off")
    func climateHeatCool() {
        let result = resolver.resolveToggleService(domain: "climate", currentState: "heat_cool")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "climate", service: "turn_off"))
    }

    @Test("Climate: auto -> turn_off")
    func climateAuto() {
        let result = resolver.resolveToggleService(domain: "climate", currentState: "auto")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "climate", service: "turn_off"))
    }

    // MARK: - Standard toggleable domains

    @Test("Light: on -> turn_off")
    func lightOn() {
        let result = resolver.resolveToggleService(domain: "light", currentState: "on")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "light", service: "turn_off"))
    }

    @Test("Light: off -> turn_on")
    func lightOff() {
        let result = resolver.resolveToggleService(domain: "light", currentState: "off")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "light", service: "turn_on"))
    }

    @Test("Switch: on -> turn_off")
    func switchOn() {
        let result = resolver.resolveToggleService(domain: "switch", currentState: "on")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "switch", service: "turn_off"))
    }

    @Test("Switch: off -> turn_on")
    func switchOff() {
        let result = resolver.resolveToggleService(domain: "switch", currentState: "off")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "switch", service: "turn_on"))
    }

    @Test("Fan: on -> turn_off")
    func fanOn() {
        let result = resolver.resolveToggleService(domain: "fan", currentState: "on")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "fan", service: "turn_off"))
    }

    @Test("Fan: off -> turn_on")
    func fanOff() {
        let result = resolver.resolveToggleService(domain: "fan", currentState: "off")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "fan", service: "turn_on"))
    }

    @Test("Input boolean: on -> turn_off")
    func inputBooleanOn() {
        let result = resolver.resolveToggleService(domain: "input_boolean", currentState: "on")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "input_boolean", service: "turn_off"))
    }

    @Test("Input boolean: off -> turn_on")
    func inputBooleanOff() {
        let result = resolver.resolveToggleService(domain: "input_boolean", currentState: "off")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "input_boolean", service: "turn_on"))
    }

    @Test("Automation: on -> turn_off")
    func automationOn() {
        let result = resolver.resolveToggleService(domain: "automation", currentState: "on")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "automation", service: "turn_off"))
    }

    @Test("Automation: off -> turn_on")
    func automationOff() {
        let result = resolver.resolveToggleService(domain: "automation", currentState: "off")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "automation", service: "turn_on"))
    }

    // MARK: - Script/Scene (always turn_on)

    @Test("Script: any state -> turn_on")
    func scriptAnyState() {
        let result = resolver.resolveToggleService(domain: "script", currentState: "off")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "script", service: "turn_on"))
    }

    @Test("Scene: any state -> turn_on")
    func sceneAnyState() {
        let result = resolver.resolveToggleService(domain: "scene", currentState: "unknown")
        #expect(result == ToggleServiceResolver.ResolvedService(domain: "scene", service: "turn_on"))
    }

    // MARK: - Unknown domain

    @Test("Unknown domain returns nil")
    func unknownDomain() {
        let result = resolver.resolveToggleService(domain: "sensor", currentState: "23")
        #expect(result == nil)
    }
}
