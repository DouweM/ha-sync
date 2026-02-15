// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "HAWatchApp",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .library(
            name: "HAWatchCore",
            targets: ["HAWatchCore"]
        ),
    ],
    targets: [
        .target(
            name: "HAWatchCore",
            path: "Sources/HAWatchCore"
        ),
        .testTarget(
            name: "HAWatchCoreTests",
            dependencies: ["HAWatchCore"],
            path: "Tests/HAWatchCoreTests"
        ),
    ]
)
