import Foundation
import HAWatchCore

/// Simple in-memory image cache with TTL to avoid redundant network requests on watchOS.
actor ImageCache {
    static let shared = ImageCache()

    private struct CacheEntry {
        let data: Data
        let timestamp: Date
    }

    private var entries: [String: CacheEntry] = [:]
    private let ttl: TimeInterval = 300 // 5 minutes
    private let maxEntries = 50

    private init() {}

    /// Fetch an image, returning cached data if available and not expired.
    func fetchImage(path: String, using client: HAAPIClient) async throws -> Data {
        // Check cache with TTL
        if let entry = entries[path],
           Date().timeIntervalSince(entry.timestamp) < ttl {
            return entry.data
        }

        let data = try await client.fetchImage(path: path)

        // Evict oldest entries if at capacity
        if entries.count >= maxEntries {
            let sortedKeys = entries.sorted { $0.value.timestamp < $1.value.timestamp }
                .prefix(entries.count - maxEntries + 1)
                .map(\.key)
            for key in sortedKeys {
                entries.removeValue(forKey: key)
            }
        }

        entries[path] = CacheEntry(data: data, timestamp: Date())
        return data
    }
}
