import Foundation

/// The rules behind the "Add Word…" window, kept free of AppKit so they are tested on
/// Linux with the rest of the core. The window (SingKhmerIME/AddWordWindow.swift) only
/// shows fields and calls these.
///
/// What the window saves is ordinary `my_words.txt` lines (`spelling Khmer`), so a word
/// added there behaves exactly like one typed into the file by hand.
public enum WordForm {
    /// The spellings typed in the window. Alternatives are separated by commas;
    /// a space (or `+`, the vocabulary.csv habit) inside one alternative makes a
    /// multi-word spelling: `kom tov, komtov` -> ["kom tov", "komtov"].
    /// Lower-cased, de-duplicated, invalid ones dropped (see `isValidSpelling`).
    public static func spellings(_ text: String) -> [String] {
        var out: [String] = []
        for part in text.split(whereSeparator: { $0 == "," || $0 == "\n" || $0 == ";" }) {
            let spelling = part.replacingOccurrences(of: "+", with: " ")
                .lowercased()
                .split(separator: " ")
                .joined(separator: " ")
            if isValidSpelling(spelling) && !out.contains(spelling) { out.append(spelling) }
        }
        return out
    }

    /// Same rule as `UserWord.parse`: ASCII letters, spaces and apostrophes only.
    public static func isValidSpelling(_ spelling: String) -> Bool {
        !spelling.isEmpty && spelling.contains(where: { $0.isLetter })
            && spelling.allSatisfy { ($0.isASCII && $0.isLetter) || $0 == " " || $0 == "'" }
    }

    /// The Khmer to save for what was typed in the Khmer field.
    ///
    /// Khmer text (pasted, or typed with a Khmer keyboard) is used as is. Latin text is
    /// converted with the engine, so a phrase built from words the keyboard already
    /// knows can be composed without a Khmer keyboard: `bong srey` -> បងស្រី. The window
    /// shows the result first, because an unknown word can be split into known ones
    /// (`dombong` -> ដុំ + បង, not ដំបូង).
    /// Returns nil when there is nothing usable, or when part of the Latin is unknown
    /// (saving a half-Latin "Khmer" word would be worse than refusing).
    public static func khmer(from text: String, engine: Engine?) -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        let scalars = trimmed.unicodeScalars
        if scalars.contains(where: Composer.isKhmer) {
            // Khmer must not carry Latin letters: they would never be typed back.
            let latin = scalars.contains { $0.isASCII && CharacterSet.letters.contains($0) }
            return latin ? nil : trimmed
        }
        guard let engine = engine else { return nil }
        let segments = engine.decode(trimmed)
        let words = segments.filter { !$0.space && !$0.surface.trimmingCharacters(in: .whitespaces).isEmpty }
        if words.isEmpty || words.contains(where: { !$0.matched }) { return nil }
        return words.map { $0.best }.joined()
    }

    /// What each spelling gives today, for the window to show before saving, e.g.
    /// "jg already gives ចង់, ចឹង — yours will come first". Empty when nothing clashes.
    public static func notes(spellings: [String], khmer: String, engine: Engine?) -> [String] {
        guard let engine = engine else { return [] }
        var notes: [String] = []
        for spelling in spellings {
            let key = spelling.replacingOccurrences(of: " ", with: "")
            let exact = engine.index[spelling] ?? engine.index[key] ?? []
            if exact.first?.khmer == khmer {
                notes.append("\(spelling) already gives \(khmer).")
            } else if !exact.isEmpty {
                let others = exact.prefix(3).map { $0.khmer }.joined(separator: ", ")
                notes.append("\(spelling) already gives \(others) — yours will come first.")
            }
        }
        return notes
    }

    /// `existing` (the my_words.txt text) with one line per new word appended. Words
    /// already in the file are not repeated. Returns nil when there is nothing to add.
    public static func appending(_ words: [UserWord], to existing: String) -> String? {
        let have = UserWord.parse(existing)
        var lines: [String] = []
        for word in words where !have.contains(word) {
            let line = "\(word.latin) \(word.khmer)"
            if !lines.contains(line) { lines.append(line) }
        }
        if lines.isEmpty { return nil }
        var text = existing
        if !text.isEmpty && !text.hasSuffix("\n") { text += "\n" }
        return text + lines.joined(separator: "\n") + "\n"
    }
}

extension MissLog {
    /// Missed spellings, most typed first: what the window suggests adding next.
    public var mostMissed: [String] {
        counts.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }.map { $0.key }
    }
}
