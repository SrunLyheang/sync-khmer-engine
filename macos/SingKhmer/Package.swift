// swift-tools-version:5.9
import PackageDescription

// SingKhmerCore  the engine port + typing logic. Pure Foundation, so it also builds and
//                tests on Linux.
// SingKhmerCLI   `swift run sk "nh srolanh bong"` to try the engine without installing.
// SingKhmerIME   the macOS input method itself (InputMethodKit, macOS only).

var products: [Product] = [
    .library(name: "SingKhmerCore", targets: ["SingKhmerCore"]),
    .executable(name: "sk", targets: ["SingKhmerCLI"]),
]

var targets: [Target] = [
    .target(name: "SingKhmerCore"),
    .executableTarget(name: "SingKhmerCLI", dependencies: ["SingKhmerCore"]),
    .testTarget(
        name: "SingKhmerCoreTests",
        dependencies: ["SingKhmerCore"],
        exclude: ["Fixtures"]
    ),
]

#if os(macOS)
products.append(.executable(name: "SingKhmerIME", targets: ["SingKhmerIME"]))
targets.append(.executableTarget(name: "SingKhmerIME", dependencies: ["SingKhmerCore"]))
#endif

let package = Package(
    name: "SingKhmer",
    platforms: [.macOS(.v11)],
    products: products,
    targets: targets
)
