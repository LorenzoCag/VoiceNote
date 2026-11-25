// swift-tools-version: 6.0
//
// Command-line tests for the app's pure-logic layer. `Sources/VoiceNoteCore` is a symlink to the
// app's `Core/` folder, so these tests exercise exactly the files the iOS app compiles.
//
//     cd ios/CoreTests && swift test

import PackageDescription

let package = Package(
    name: "VoiceNoteCore",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "VoiceNoteCore", targets: ["VoiceNoteCore"])],
    targets: [
        .target(name: "VoiceNoteCore", swiftSettings: [.swiftLanguageMode(.v5)]),
        .testTarget(name: "VoiceNoteCoreTests", dependencies: ["VoiceNoteCore"], swiftSettings: [.swiftLanguageMode(.v5)]),
    ]
)
