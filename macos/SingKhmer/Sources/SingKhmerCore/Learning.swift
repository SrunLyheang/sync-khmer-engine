import Foundation

// What the keyboard learns from the person using it. None of this exists in the Python
// engine; it is local to the Mac keyboard and stored as small files the shell reads and
// writes (see Sources/SingKhmerIME/UserStore.swift).

/// One word the user taught the keyboard: a spelling and the Khmer it should become.
public struct UserWord: Equatable {
    public let latin: String
    public let khmer: String

    public init(latin: String, khmer: String) {
        self.latin = latin
        self.khmer = khmer
    }

    /// Parse the "my words" file: one word per line, the spelling followed by the Khmer.
    ///
    ///     # lines starting with # are ignored
    ///     jrern  ច្រើន
    ///     ot ey = អត់អី
    ///
    /// Anything before the first Khmer letter is the spelling (a separating `=`, `,`,
    /// `:` or tab is optional). The same Khmer word may appear on several lines.
    public static func parse(_ text: String) -> [UserWord] {
        var words: [UserWord] = []
        for rawLine in text.split(whereSeparator: { $0 == "\n" || $0 == "\r" }) {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            if line.isEmpty || line.hasPrefix("#") { continue }
            let scalars = Array(line.unicodeScalars)
            guard let split = scalars.firstIndex(where: Composer.isKhmer) else { continue }
            let latin = Engine.string(scalars[..<split])
                .trimmingCharacters(in: CharacterSet(charactersIn: " \t=,:"))
                .lowercased()
                .split(separator: " ").joined(separator: " ")
            let khmer = Engine.string(scalars[split...]).trimmingCharacters(in: .whitespaces)
            let validLatin = !latin.isEmpty && latin.allSatisfy {
                ($0.isASCII && $0.isLetter) || $0 == " " || $0 == "'"
            }
            if validLatin && !khmer.isEmpty && !words.contains(UserWord(latin: latin, khmer: khmer)) {
                words.append(UserWord(latin: latin, khmer: khmer))
            }
        }
        return words
    }
}

/// Remembers which candidate the user picks for each spelling, so the one they actually
/// use rises to the top (`jg` -> ចង់ or ចឹង).
///
/// Every pick fades the older picks for that spelling and adds one to the chosen
/// candidate. In practice: the first time you pick an alternative it becomes the first
/// choice; once a habit exists, a single odd pick does not disturb it, but picking the
/// same alternative twice in a row switches the default.
public final class History {
    static let decay = 0.6
    static let floor = 0.05

    private var weights: [String: [String: Double]]
    /// Called after every change, so the owner can save.
    public var onChange: (() -> Void)?

    public init() {
        weights = [:]
    }

    public init(data: Data) throws {
        weights = try JSONDecoder().decode([String: [String: Double]].self, from: data)
    }

    public func encoded() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(weights)
    }

    public func record(spelling: String, chosen: String) {
        let key = spelling.lowercased()
        var entry = weights[key] ?? [:]
        for (text, weight) in entry {
            let faded = weight * History.decay
            entry[text] = faded < History.floor ? nil : faded
        }
        entry[chosen, default: 0] += 1
        weights[key] = entry
        onChange?()
    }

    public func weight(spelling: String, text: String) -> Double {
        weights[spelling.lowercased()]?[text] ?? 0
    }

    /// `items` with the user's habitual choices first; otherwise the original order.
    func ranked<T>(_ items: [T], spelling: String, text: (T) -> String) -> [T] {
        guard let entry = weights[spelling.lowercased()], !entry.isEmpty else { return items }
        return items.enumerated().sorted { a, b in
            let wa = entry[text(a.element)] ?? 0
            let wb = entry[text(b.element)] ?? 0
            return wa != wb ? wa > wb : a.offset < b.offset
        }.map { $0.element }
    }
}

/// Counts spellings that were typed in Sing Khmer mode, matched nothing, and were not
/// English: the words most worth adding to the dictionary next.
public struct MissLog: Equatable {
    public private(set) var counts: [String: Int] = [:]

    public init() {}

    /// Parse the file written by `formatted()`.
    public init(text: String) {
        for line in text.split(separator: "\n") where !line.hasPrefix("#") {
            let parts = line.split(whereSeparator: { $0 == "\t" || $0 == " " })
            if parts.count == 2, let count = Int(parts[0]) {
                counts[String(parts[1])] = count
            }
        }
    }

    public mutating func record(_ spelling: String) {
        counts[spelling.lowercased(), default: 0] += 1
    }

    public mutating func remove(_ spellings: [String]) {
        for spelling in spellings { counts[spelling.lowercased()] = nil }
    }

    /// Most-typed first, one `count<TAB>spelling` per line.
    public func formatted() -> String {
        let header = "# Spellings you typed that Sing Khmer did not know, most typed first.\n"
            + "# To teach it one, add a line to my_words.txt: the spelling, then the Khmer.\n"
        let rows = counts.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
        return header + rows.map { "\($0.value)\t\($0.key)\n" }.joined()
    }
}
