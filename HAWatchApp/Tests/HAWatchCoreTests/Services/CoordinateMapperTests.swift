import Testing
@testable import HAWatchCore

@Suite("CoordinateMapper")
struct CoordinateMapperTests {
    // Example bounds: top-left (52.1, 4.3) to bottom-right (52.0, 4.4)
    let bounds = MapBounds(north: 52.1, west: 4.3, south: 52.0, east: 4.4)

    @Test("Center of bounds maps to (0.5, 0.5)")
    func centerPoint() {
        let mapper = CoordinateMapper(bounds: bounds)
        let result = mapper.normalize(latitude: 52.05, longitude: 4.35)

        #expect(result != nil)
        #expect(abs(result!.x - 0.5) < 0.001)
        #expect(abs(result!.y - 0.5) < 0.001)
    }

    @Test("Top-left corner maps to (0, 0)")
    func topLeft() {
        let mapper = CoordinateMapper(bounds: bounds)
        let result = mapper.normalize(latitude: 52.1, longitude: 4.3)

        #expect(result != nil)
        #expect(abs(result!.x - 0.0) < 0.001)
        #expect(abs(result!.y - 0.0) < 0.001)
    }

    @Test("Bottom-right corner maps to (1, 1)")
    func bottomRight() {
        let mapper = CoordinateMapper(bounds: bounds)
        let result = mapper.normalize(latitude: 52.0, longitude: 4.4)

        #expect(result != nil)
        #expect(abs(result!.x - 1.0) < 0.001)
        #expect(abs(result!.y - 1.0) < 0.001)
    }

    @Test("Quarter point")
    func quarterPoint() {
        let mapper = CoordinateMapper(bounds: bounds)
        let result = mapper.normalize(latitude: 52.075, longitude: 4.325)

        #expect(result != nil)
        #expect(abs(result!.x - 0.25) < 0.001)
        #expect(abs(result!.y - 0.25) < 0.001)
    }

    @Test("Contains point inside bounds")
    func containsInside() {
        let mapper = CoordinateMapper(bounds: bounds)
        #expect(mapper.contains(latitude: 52.05, longitude: 4.35))
    }

    @Test("Does not contain point outside bounds")
    func containsOutside() {
        let mapper = CoordinateMapper(bounds: bounds)
        #expect(!mapper.contains(latitude: 53.0, longitude: 4.35))
        #expect(!mapper.contains(latitude: 52.05, longitude: 5.0))
    }

    @Test("Contains point on boundary")
    func containsOnBoundary() {
        let mapper = CoordinateMapper(bounds: bounds)
        #expect(mapper.contains(latitude: 52.1, longitude: 4.3))
        #expect(mapper.contains(latitude: 52.0, longitude: 4.4))
    }

    @Test("Init from bounds array")
    func initFromArray() {
        let mapper = CoordinateMapper(boundsArray: [[52.1, 4.3], [52.0, 4.4]])

        #expect(mapper != nil)
        #expect(mapper!.bounds.north == 52.1)
        #expect(mapper!.bounds.west == 4.3)
        #expect(mapper!.bounds.south == 52.0)
        #expect(mapper!.bounds.east == 4.4)
    }

    @Test("Init from invalid bounds array returns nil")
    func initFromInvalidArray() {
        #expect(CoordinateMapper(boundsArray: [[52.1]]) == nil)
        #expect(CoordinateMapper(boundsArray: []) == nil)
        #expect(CoordinateMapper(boundsArray: [[52.1, 4.3]]) == nil)
    }

    @Test("MapBounds center calculation")
    func boundsCenter() {
        #expect(abs(bounds.centerLatitude - 52.05) < 0.001)
        #expect(abs(bounds.centerLongitude - 4.35) < 0.001)
    }

    @Test("Zero-range bounds returns nil")
    func zeroRange() {
        let zeroBounds = MapBounds(north: 52.0, west: 4.3, south: 52.0, east: 4.3)
        let mapper = CoordinateMapper(bounds: zeroBounds)
        #expect(mapper.normalize(latitude: 52.0, longitude: 4.3) == nil)
    }
}
