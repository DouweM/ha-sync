/// Maps GPS coordinates to normalized 0..1 positions for image overlay maps.
public struct CoordinateMapper: Sendable {
    public let bounds: MapBounds

    public init(bounds: MapBounds) {
        self.bounds = bounds
    }

    /// Initialize from raw bounds array [[lat1, lon1], [lat2, lon2]].
    public init?(boundsArray: [[Double]]) {
        guard boundsArray.count == 2,
              boundsArray[0].count == 2,
              boundsArray[1].count == 2
        else { return nil }

        self.bounds = MapBounds(
            north: boundsArray[0][0],
            west: boundsArray[0][1],
            south: boundsArray[1][0],
            east: boundsArray[1][1]
        )
    }

    /// Convert GPS coordinates to normalized 0..1 position.
    /// - Parameters:
    ///   - latitude: GPS latitude
    ///   - longitude: GPS longitude
    /// - Returns: Normalized (x, y) where (0,0) is top-left and (1,1) is bottom-right,
    ///           or nil if the coordinate is outside bounds.
    public func normalize(latitude: Double, longitude: Double) -> (x: Double, y: Double)? {
        let latRange = bounds.north - bounds.south
        let lonRange = bounds.east - bounds.west

        guard latRange != 0, lonRange != 0 else { return nil }

        let x = (longitude - bounds.west) / lonRange
        let y = (bounds.north - latitude) / latRange

        return (x: x, y: y)
    }

    /// Check if a coordinate is within the map bounds.
    public func contains(latitude: Double, longitude: Double) -> Bool {
        latitude >= bounds.south && latitude <= bounds.north &&
        longitude >= bounds.west && longitude <= bounds.east
    }
}

public struct MapBounds: Sendable {
    public var north: Double
    public var west: Double
    public var south: Double
    public var east: Double

    public init(north: Double, west: Double, south: Double, east: Double) {
        self.north = north
        self.west = west
        self.south = south
        self.east = east
    }

    public var centerLatitude: Double { (north + south) / 2 }
    public var centerLongitude: Double { (east + west) / 2 }
}
