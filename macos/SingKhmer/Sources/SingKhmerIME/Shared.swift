import Foundation
import SingKhmerCore

/// State shared by every text field: the dictionary is loaded once, and there is one
/// candidate window.
enum Shared {
    static let engine: Engine? = {
        guard let url = Bundle.main.url(forResource: "engine_data", withExtension: "json") else {
            NSLog("SingKhmer: engine_data.json is missing from the app bundle")
            return nil
        }
        do {
            let engine = try Engine(contentsOf: url)
            NSLog("SingKhmer: loaded \(engine.index.count) spellings")
            return engine
        } catch {
            NSLog("SingKhmer: could not read engine_data.json: \(error)")
            return nil
        }
    }()

    static let panel = CandidatePanel()
}
