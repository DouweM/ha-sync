import Foundation
import HAWatchCore

/// Simple in-memory image cache to avoid redundant network requests on watchOS.
actor ImageCache {
    static let shared = ImageCache()

    private let cache = NSCache<NSString, NSData>()

    private init() {
        cache.countLimit = 50
    }

    /// Fetch an image, returning cached data if available.
    func fetchImage(path: String, using client: HAAPIClient) async throws -> Data {
        let key = path as NSString

        if let cached = cache.object(forKey: key) {
            return cached as Data
        }

        let data = try await client.fetchImage(path: path)
        cache.setObject(data as NSData, forKey: key)
        return data
    }
}
