import Foundation
import SingKhmerCore

// Try the engine from Terminal without installing the input method:
//
//     swift run sk nh srolanh bong
//     swift run sk nhslbong
//
// Terminals often cannot shape Khmer correctly (the letters may look broken). That is a
// terminal display limit; paste the output into TextEdit to see it properly.

let dataPath = ProcessInfo.processInfo.environment["SINGKHMER_DATA"] ?? "Resources/engine_data.json"
let input = CommandLine.arguments.dropFirst().joined(separator: " ")

guard !input.isEmpty else {
    print("usage: swift run sk <sing khmer text>")
    exit(64)
}

let engine: Engine
do {
    engine = try Engine(contentsOf: URL(fileURLWithPath: dataPath))
} catch {
    print("Could not load \(dataPath): \(error)")
    print("Run `python3 scripts/export_mac_data.py` from the repo root, then run this from macos/SingKhmer.")
    exit(1)
}

print(engine.convertSentenceText(input))
for segment in engine.decode(input) where !segment.space {
    let options = segment.candidates.map { "\($0.khmer) (\($0.source) \($0.score))" }
    print("  \(segment.surface) -> " + (options.isEmpty ? "(kept as typed)" : options.joined(separator: ", ")))
}
let readings = engine.readings(input, k: 3)
if readings.count > 1 {
    print("  other readings: " + readings.dropFirst().joined(separator: " | "))
}
