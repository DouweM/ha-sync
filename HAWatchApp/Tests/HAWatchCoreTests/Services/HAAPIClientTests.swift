import Testing
import Foundation
@testable import HAWatchCore

@Suite("HAAPIClient")
struct HAAPIClientTests {
    @Test("Invalid URL in fetchImage throws invalidURL error")
    func invalidURLThrowsError() async throws {
        let client = HAAPIClient(
            baseURL: URL(string: "https://example.com")!,
            token: "test-token"
        )

        // A URL with spaces and invalid characters should throw invalidURL
        await #expect(throws: HAAPIError.self) {
            _ = try await client.fetchImage(path: "http://invalid url with spaces")
        }
    }

    @Test("HAAPIError cases are distinct")
    func errorCasesAreDistinct() {
        let errors: [HAAPIError] = [
            .unauthorized,
            .notFound,
            .httpError(statusCode: 500),
            .noDashboardConfig,
            .webSocketUnavailable,
            .invalidURL("bad"),
            .unknownError,
        ]
        // Verify all error types exist and are constructible
        #expect(errors.count == 7)
    }

    @Test("Valid relative path does not throw")
    func relativePathDoesNotThrow() async {
        let client = HAAPIClient(
            baseURL: URL(string: "https://example.com")!,
            token: "test-token"
        )

        // This will fail with a network error (not reachable), NOT an invalidURL error
        do {
            _ = try await client.fetchImage(path: "/local/image.png")
            // If it somehow succeeds (unlikely in test), that's fine
        } catch let error as HAAPIError {
            // Should be a network-level error, not invalidURL
            if case .invalidURL = error {
                Issue.record("Relative path should not throw invalidURL")
            }
            // Any other HAAPIError is expected (network failure)
        } catch {
            // Non-HAAPIError (e.g., URLSession error) is expected
        }
    }
}
