import Foundation
import XCTest
@testable import SingKhmerCore

/// Locates the files written by scripts/export_mac_data.py, relative to this source file.
enum Fixtures {
    static let packageRoot = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()      // SingKhmerCoreTests
        .deletingLastPathComponent()      // Tests
        .deletingLastPathComponent()      // SingKhmer

    static let dataURL = packageRoot.appendingPathComponent("Resources/engine_data.json")
    static let goldenURL = packageRoot
        .appendingPathComponent("Tests/SingKhmerCoreTests/Fixtures/golden.json")

    static let missingMessage =
        "Generated data not found. Run `python3 scripts/export_mac_data.py` from the repo root first."

    static let engine: Engine? = try? Engine(contentsOf: dataURL)

    static func requireEngine() throws -> Engine {
        try XCTUnwrap(engine, missingMessage)
    }
}
