// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "omnivo-audio-capture",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "omnivo-audio-capture",
            path: "Sources"
        )
    ]
)
