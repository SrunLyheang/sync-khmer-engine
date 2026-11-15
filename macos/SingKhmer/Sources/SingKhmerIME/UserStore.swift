import Foundation
import SingKhmerCore

/// Everything the keyboard learns, kept as three small files in
/// ~/Library/Application Support/SingKhmer. Nothing here ever leaves the Mac.
///
///   my_words.txt      words the user taught it; edited by hand (menu: Edit My Words)
///   history.json      which candidate the user picks for each spelling
///   missed_words.txt  spellings typed that matched nothing, most typed first
final class UserStore {
    static let wordsTemplate = """
        # Your own Sing Khmer words. One per line: the spelling, then the Khmer.
        # Save the file and the keyboard picks the change up on the next word you type.
        # Your words always come first for their spelling.
        #
        # Examples (remove the # to use one):
        # jrern ច្រើន
        # ot ey អត់អី

        """

    let directory: URL
    let wordsURL: URL
    let historyURL: URL
    let missesURL: URL

    let history: History
    /// The dictionary plus the user's words. Nil if the dictionary failed to load.
    private(set) var engine: Engine?
    /// Goes up each time `engine` is replaced, so open text fields know to switch.
    private(set) var generation = 0

    private let baseEngine: Engine?
    private var wordsModified: Date?
    private var misses: MissLog

    init(baseEngine: Engine?) {
        self.baseEngine = baseEngine
        engine = baseEngine

        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        directory = support.appendingPathComponent("SingKhmer", isDirectory: true)
        wordsURL = directory.appendingPathComponent("my_words.txt")
        historyURL = directory.appendingPathComponent("history.json")
        missesURL = directory.appendingPathComponent("missed_words.txt")

        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: wordsURL.path) {
            try? UserStore.wordsTemplate.write(to: wordsURL, atomically: true, encoding: .utf8)
        }

        history = (try? Data(contentsOf: historyURL)).flatMap { try? History(data: $0) } ?? History()
        misses = (try? String(contentsOf: missesURL, encoding: .utf8)).map { MissLog(text: $0) } ?? MissLog()
        history.onChange = { [weak self] in self?.saveHistory() }
        reloadWordsIfChanged()
    }

    /// Re-read my_words.txt if it was saved since the last look. Cheap enough to call
    /// at the start of every word.
    @discardableResult
    func reloadWordsIfChanged() -> Bool {
        guard let baseEngine = baseEngine else { return false }
        let attributes = try? FileManager.default.attributesOfItem(atPath: wordsURL.path)
        let modified = attributes?[.modificationDate] as? Date
        guard modified != wordsModified else { return false }
        wordsModified = modified

        let text = (try? String(contentsOf: wordsURL, encoding: .utf8)) ?? ""
        let words = UserWord.parse(text)
        engine = baseEngine.addingUserWords(words)
        generation += 1
        NSLog("SingKhmer: loaded \(words.count) of your own words")

        // A word that has now been taught is no longer missing.
        let before = misses
        misses.remove(words.map { $0.latin })
        if misses != before { saveMisses() }
        return true
    }

    func recordMiss(_ spelling: String) {
        misses.record(spelling)
        saveMisses()
    }

    private func saveHistory() {
        guard let data = try? history.encoded() else { return }
        try? data.write(to: historyURL, options: .atomic)
    }

    private func saveMisses() {
        try? misses.formatted().write(to: missesURL, atomically: true, encoding: .utf8)
    }
}
