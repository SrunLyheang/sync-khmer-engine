import Foundation

// A line-for-line port of the RUNTIME half of the Python engine
// (src/sing_khmer_engine/lookup.py, fuzzy.py, english.py).
//
// The reverse index itself is not rebuilt here: scripts/export_mac_data.py builds it
// with the real Python engine and writes it to engine_data.json. Keep this file in step
// with lookup.py; the golden tests (Tests/SingKhmerCoreTests) compare the two on
// thousands of inputs and fail if they drift apart.
//
// Text is handled as arrays of Unicode scalars so that lengths and offsets mean exactly
// what they mean in Python (which indexes strings by code point).

/// One Khmer word suggested for a Latin spelling.
public struct Candidate: Equatable, Decodable {
    public let khmer: String
    public let score: Double
    public let source: String        // "collected" | "generated" | "fuzzy" | "english"

    public init(khmer: String, score: Double, source: String) {
        self.khmer = khmer
        self.score = score
        self.source = source
    }
}

/// One piece of a decoded message: a matched spelling or passed-through text.
public struct Segment: Equatable {
    public var surface: String             // the Latin text this segment covers
    public var candidates: [Candidate]     // empty => unknown / passed through unchanged
    public var lead: String = ""           // leading punctuation to keep
    public var trail: String = ""          // trailing punctuation to keep
    public var display: String? = nil      // explicit rendering override (the repeat sign)
    public var space: Bool = false         // a literal space committed by a double-space

    public var matched: Bool { !candidates.isEmpty }

    public var best: String {
        if space { return " " }
        let khmer = display ?? candidates.first?.khmer ?? surface
        return lead + khmer + trail
    }
}

public enum EngineError: Error {
    case unsupportedVersion(Int)
}

public final class Engine {
    typealias Scalars = [Unicode.Scalar]
    typealias Span = (start: Int, end: Int, key: String?)

    // Segmentation scoring knobs (same values as lookup.py).
    static let lenWeight = 3.0           // reward for covering more characters
    static let unknownPenalty = 2.0      // cost per character left unmatched
    static let wordCost = 6.0            // so one whole word beats splitting it in two
    static let passthroughUnmatched = 0.34
    static let repeatSign = "\u{17D7}"   // ៗ
    static let supportedVersion = 1
    static let space: Unicode.Scalar = " "

    public let index: [String: [Candidate]]
    let maxKeyLen: Int
    let khmerWords: Set<String>
    let english: Set<String>
    private let fuzzyKeys: [(key: [UInt32], candidates: [Candidate])]
    private var multiWordPrefixes: Set<String> = []

    /// Score given to the user's own words: above every dictionary score (max 5), so
    /// a word you added yourself always comes first for its spelling.
    public static let userScore = 6.0

    private struct Payload: Decodable {
        let version: Int
        let index: [String: [Candidate]]
        let khmer_words: [String]
        let english: [String]
    }

    /// Load the file written by scripts/export_mac_data.py.
    public convenience init(data: Data) throws {
        let payload = try JSONDecoder().decode(Payload.self, from: data)
        guard payload.version == Engine.supportedVersion else {
            throw EngineError.unsupportedVersion(payload.version)
        }
        self.init(index: payload.index, khmerWords: Set(payload.khmer_words),
                  english: Set(payload.english))
    }

    public convenience init(contentsOf url: URL) throws {
        try self.init(data: try Data(contentsOf: url))
    }

    private init(index: [String: [Candidate]], khmerWords: Set<String>, english: Set<String>) {
        self.index = index
        self.khmerWords = khmerWords
        self.english = english
        maxKeyLen = max(index.keys.map { $0.unicodeScalars.count }.max() ?? 1, 1)
        fuzzyKeys = index.map { (key: $0.key.unicodeScalars.map { $0.value }, candidates: $0.value) }

        // Multi-word spellings that only come out right if the words are looked up
        // TOGETHER (bong rean -> one word, not two). The typing logic keeps the space
        // "open" for these. Most multi-word spellings do not need it: typing their
        // words one at a time already produces the same Khmer.
        var prefixes = Set<String>()
        for (key, candidates) in index {
            let scalars = Array(key.unicodeScalars)
            guard let firstSpace = scalars.firstIndex(of: Engine.space),
                  let target = candidates.first?.khmer else { continue }
            let oneAtATime = key.split(separator: " ").map { convertSentenceText(String($0)) }.joined()
            if oneAtATime == target { continue }
            for end in (firstSpace + 1)...scalars.count {
                prefixes.insert(Engine.string(scalars[0..<end]))
            }
        }
        multiWordPrefixes = prefixes
    }

    /// A copy of this engine that also knows the user's own words. Each one is ranked
    /// first for its spelling.
    public func addingUserWords(_ words: [UserWord]) -> Engine {
        guard !words.isEmpty else { return self }
        var merged = index
        var known = khmerWords
        for word in words {
            let candidate = Candidate(khmer: word.khmer, score: Engine.userScore, source: "user")
            var keys = [word.latin]
            if word.latin.contains(" ") { keys.append(word.latin.replacingOccurrences(of: " ", with: "")) }
            for key in keys {
                var list = (merged[key] ?? []).filter { $0.khmer != word.khmer }
                list.insert(candidate, at: 0)
                merged[key] = list
            }
            known.insert(word.khmer)
        }
        return Engine(index: merged, khmerWords: known, english: english)
    }

    /// True if `text` (containing a space) could still grow into a multi-word spelling
    /// that has to be looked up as a whole.
    public func isMultiWordPrefix(_ text: String) -> Bool {
        multiWordPrefixes.contains(text.lowercased())
    }

    /// True if `word` is in the common-English list (so it is left as typed).
    public func isEnglishWord(_ word: String) -> Bool {
        isEnglish(Array(word.unicodeScalars))
    }

    // MARK: - Single-spelling lookup (exact, then fuzzy)

    /// Ranked Khmer candidates for one Latin spelling. Empty = no match.
    public func convert(_ text: String, limit: Int = 5, fuzzy: Bool = true) -> [Candidate] {
        let key = Engine.string(Engine.lower(Engine.strip(Array(text.unicodeScalars))))
        if key.isEmpty { return [] }
        if let exact = index[key], !exact.isEmpty { return Array(exact.prefix(limit)) }
        if !fuzzy { return [] }
        return fuzzyMatch(key, limit: limit)
    }

    private func fuzzyMatch(_ key: String, limit: Int) -> [Candidate] {
        let query = key.unicodeScalars.map { $0.value }
        let threshold = query.count <= 3 ? 1 : 2
        var best: [String: (d: Int, score: Double)] = [:]
        for entry in fuzzyKeys {
            guard let d = Fuzzy.within(query, entry.key, threshold) else { continue }
            for c in entry.candidates {
                if let cur = best[c.khmer] {
                    if d < cur.d || (d == cur.d && c.score > cur.score) {
                        best[c.khmer] = (d, c.score)
                    }
                } else {
                    best[c.khmer] = (d, c.score)
                }
            }
        }
        let ranked = best.sorted { a, b in
            if a.value.d != b.value.d { return a.value.d < b.value.d }
            if a.value.score != b.value.score { return a.value.score > b.value.score }
            return Engine.codePointLess(a.key, b.key)
        }
        return ranked.prefix(limit).map {
            Candidate(khmer: $0.key,
                      score: Engine.round3($0.value.score / (1.0 + Double($0.value.d))),
                      source: "fuzzy")
        }
    }

    // MARK: - Whole-message decoding (segmentation)

    private func keyScore(_ key: String) -> Double {
        index[key]![0].score + Engine.lenWeight * Double(key.unicodeScalars.count) - Engine.wordCost
    }

    /// Merge adjacent tokens that together form a multi-word index key
    /// (`msel` + `minh` -> `msel minh`).
    private func mergeMultiWord(_ tokens: [Scalars]) -> [Scalars] {
        var merged: [Scalars] = []
        var i = 0
        while i < tokens.count {
            var bestLen = 1
            var j = i + 1
            while j < min(i + 4, tokens.count + 1) {
                let candidate = Engine.join(tokens[i..<j])
                if index[Engine.string(Engine.lower(candidate))] != nil { bestLen = j - i }
                j += 1
            }
            merged.append(Engine.join(tokens[i..<(i + bestLen)]))
            i += bestLen
        }
        return merged
    }

    /// Top-`k` ways to cover `lower` with known spellings (Viterbi k-best). A span with
    /// a key is an exact index hit; a span without one is a single unmatched character.
    private func segmentKBest(_ lower: Scalars, _ k: Int) -> [[Span]] {
        typealias Entry = (score: Double, prev: Int, prevRank: Int, key: String?)
        let n = lower.count
        var dp: [[Entry]] = Array(repeating: [], count: n + 1)
        dp[0] = [(0.0, -1, -1, nil)]
        if n > 0 {
            for i in 1...n {
                var cands: [Entry] = []
                let step = lower[i - 1] == Engine.space ? 0.0 : -Engine.unknownPenalty
                for (rank, entry) in dp[i - 1].enumerated() {
                    cands.append((entry.score + step, i - 1, rank, nil))
                }
                for j in max(0, i - maxKeyLen)..<i {
                    if dp[j].isEmpty { continue }
                    let sub = Engine.string(lower[j..<i])
                    if index[sub] == nil { continue }
                    if i - j == 1 {
                        let startsToken = j == 0 || lower[j - 1] == Engine.space
                        let endsToken = i == n || lower[i] == Engine.space
                        if !(startsToken && endsToken) { continue }
                    }
                    let ks = keyScore(sub)
                    for (rank, entry) in dp[j].enumerated() {
                        cands.append((entry.score + ks, j, rank, sub))
                    }
                }
                // Python's sort is stable; keep insertion order on equal scores.
                let order = cands.indices.sorted {
                    cands[$0].score != cands[$1].score ? cands[$0].score > cands[$1].score : $0 < $1
                }
                dp[i] = order.prefix(k).map { cands[$0] }
            }
        }

        var paths: [[Span]] = []
        for startRank in dp[n].indices {
            var spans: [Span] = []
            var i = n
            var rank = startRank
            while i > 0 {
                let entry = dp[i][rank]
                spans.append((entry.prev, i, entry.key))
                i = entry.prev
                rank = entry.prevRank
            }
            spans.reverse()
            paths.append(spans)
        }
        return paths
    }

    private func isEnglish(_ word: Scalars) -> Bool {
        english.contains(Engine.string(Engine.lower(Engine.strip(word))))
    }

    /// Whitespace tokens that should stay Latin: a word that can only be "matched" by
    /// chopping it into gibberish, or a real English word that is not a strong Khmer match.
    private func lowConfidenceTokens(_ lower: Scalars, _ spans: [Span]) -> [(Int, Int)] {
        var forced: [(Int, Int)] = []
        for (ts, te) in Engine.nonSpaceRuns(lower[...]) {
            if spans.contains(where: { $0.start < te && $0.end > ts && ($0.start < ts || $0.end > te) }) {
                continue                              // a spelling crosses this token's edge
            }
            let inside = spans.filter { ts <= $0.start && $0.end <= te }
            let strong = inside.count == 1 && inside[0].key != nil
                && inside[0].start == ts && inside[0].end == te
            if isEnglish(Array(lower[ts..<te])) && !strong {
                forced.append((ts, te))
                continue
            }
            let unmatched = inside.reduce(0) { $0 + ($1.key == nil ? $1.end - $1.start : 0) }
            let matched = inside.filter { $0.key != nil }.count
            if matched > 0 && unmatched > 0
                && Double(unmatched) / Double(te - ts) >= Engine.passthroughUnmatched {
                forced.append((ts, te))
            }
        }
        return forced
    }

    private func spansToSegments(_ text: Scalars, _ spans: [Span], limit: Int) -> [Segment] {
        let lower = Engine.lower(text)
        let forced = lowConfidenceTokens(lower, spans)
        var segments: [Segment] = []
        var rawStart: Int? = nil

        func flushRaw(_ end: Int) {
            guard let start = rawStart else { return }
            rawStart = nil
            let chunk = text[start..<end]
            for (ts, te) in Engine.nonSpaceRuns(chunk) {        // fuzzy-match leftover words
                let tok = Array(text[ts..<te])
                let (lead, core, trail) = Engine.splitPunctuation(tok)
                if core.isEmpty {                               // pure punctuation
                    segments.append(Segment(surface: Engine.string(tok), candidates: []))
                    continue
                }
                if core.count == 1 {                            // a stray leftover character
                    segments.append(Segment(surface: Engine.string(tok), candidates: []))
                    continue
                }
                let coreText = Engine.string(core)
                segments.append(Segment(surface: coreText,
                                        candidates: convert(coreText, limit: limit),
                                        lead: Engine.string(lead),
                                        trail: Engine.string(trail)))
            }
        }

        var idx = 0
        while idx < spans.count {
            let (j, i, key) = spans[idx]
            if let region = forced.first(where: { $0.0 <= j && i <= $0.1 }) {
                flushRaw(region.0)                              // low-confidence -> passthrough
                segments.append(Segment(surface: Engine.string(text[region.0..<region.1]),
                                        candidates: []))
                while idx < spans.count && region.0 <= spans[idx].start && spans[idx].end <= region.1 {
                    idx += 1
                }
                continue
            }
            if let key = key {
                flushRaw(j)
                let surface = Array(text[j..<i])
                var cands = Array(index[key]!.prefix(limit))
                // A whole-token spelling that is also a real English word gets the
                // English original as its LAST option (never auto-picked).
                let boundary = (j == 0 || lower[j - 1] == Engine.space)
                    && (i == text.count || lower[i] == Engine.space)
                if boundary && isEnglish(surface) {
                    cands.append(Candidate(khmer: Engine.string(surface), score: 0.0, source: "english"))
                }
                segments.append(Segment(surface: Engine.string(surface), candidates: cands))
            } else if rawStart == nil {
                rawStart = j
            }
            idx += 1
        }
        flushRaw(text.count)
        return segments
    }

    /// If `khmer` is a known word written twice, return the single word.
    private func reduplicationBase(_ khmer: String) -> String? {
        let scalars = Array(khmer.unicodeScalars)
        guard scalars.count % 2 == 0 else { return nil }
        let half = scalars.count / 2
        guard Array(scalars[..<half]) == Array(scalars[half...]) else { return nil }
        let base = Engine.string(scalars[..<half])
        return khmerWords.contains(base) ? base : nil
    }

    /// Render a repeated word with the repetition sign instead of writing it twice.
    private func applyRepetition(_ segments: [Segment]) -> [Segment] {
        var out: [Segment] = []
        var prevWord: String? = nil
        for s in segments {
            let word = s.matched ? s.candidates[0].khmer : nil
            let canFold = word != nil && s.display == nil && s.lead.isEmpty && s.trail.isEmpty
            let base = canFold ? reduplicationBase(word!) : nil
            var copy = s
            if canFold, let base = base {                       // a doubled entry
                copy.display = base + Engine.repeatSign
                out.append(copy)
                prevWord = base
            } else if canFold && word == prevWord {             // two adjacent words
                copy.display = Engine.repeatSign
                out.append(copy)
                prevWord = word
            } else {
                out.append(s)
                prevWord = word
            }
        }
        return out
    }

    /// Decode a whole message into matched/unknown segments (best reading). Works with
    /// or without spaces between words; a run of 2+ spaces commits one real space.
    public func decode(_ text: String, limit: Int = 5) -> [Segment] {
        var segments: [Segment] = []
        for (idx, part) in Engine.splitDoubleSpaces(Array(text.unicodeScalars)).enumerated() {
            if idx > 0 {
                segments.append(Segment(surface: " ", candidates: [], space: true))
            }
            if part.isEmpty { continue }
            let tokens = mergeMultiWord(Engine.nonSpaceRuns(part[...]).map { Array(part[$0.0..<$0.1]) })
            for token in tokens {
                let lower = Engine.lower(token)
                let spans = segmentKBest(lower, 1).first ?? []
                // Not a known spelling and only partly coverable: keep the token as typed
                // rather than emitting a half-Khmer, half-Latin mix.
                if index[Engine.string(lower)] == nil && spans.contains(where: { $0.key == nil }) {
                    segments.append(Segment(surface: Engine.string(token), candidates: []))
                } else {
                    segments.append(contentsOf: spansToSegments(token, spans, limit: limit))
                }
            }
        }
        return applyRepetition(segments)
    }

    /// Render segments the way Khmer is written: Khmer words run together with no
    /// space, passed-through Latin keeps spaces around it, punctuation attaches.
    public static func joinSegments(_ segments: [Segment]) -> String {
        var result = ""
        var prevKhmer = false
        var attachNext = false
        for s in segments {
            if s.space {
                if !result.isEmpty && !result.hasSuffix(" ") { result += " " }
                prevKhmer = false
                attachNext = true
                continue
            }
            let isKhmer = s.matched
            let isPunct = !isKhmer && !s.surface.isEmpty
                && !s.surface.unicodeScalars.contains(where: Engine.isAlnum)
            let piece = s.best
            if result.isEmpty || attachNext {
                result += piece
            } else if isPunct || (prevKhmer && isKhmer) {
                result += piece
            } else {
                result += " " + piece
            }
            prevKhmer = isKhmer
            attachNext = false
        }
        return result
    }

    /// Up to `k` distinct whole-message readings, best first (compound vs. split,
    /// folded repetition vs. doubled form).
    public func readings(_ text: String, k: Int = 3) -> [String] {
        var out: [String] = []
        let base = decode(text)
        out.append(Engine.joinSegments(base))
        if base.contains(where: { ($0.display ?? "").hasSuffix(Engine.repeatSign) }) {
            let doubled = base.map { s -> Segment in
                var copy = s
                if let d = s.display, d.hasSuffix(Engine.repeatSign) { copy.display = nil }
                return copy
            }
            let reading = Engine.joinSegments(doubled)
            if !out.contains(reading) { out.append(reading) }
        }
        let scalars = Array(text.unicodeScalars)
        if !Engine.hasDoubleSpace(scalars) {
            for spans in segmentKBest(Engine.lower(scalars), k * 2) {
                let segs = applyRepetition(spansToSegments(scalars, spans, limit: 1))
                let reading = Engine.joinSegments(segs)
                if !out.contains(reading) { out.append(reading) }
                if out.count >= k { break }
            }
        }
        return out.count > k ? Array(out.prefix(k)) : out
    }

    /// Top-pick Khmer for a whole message.
    public func convertSentenceText(_ text: String) -> String {
        Engine.joinSegments(decode(text))
    }
}

// MARK: - Text helpers that mirror Python's str / re behaviour

extension Engine {
    static func string<S: Sequence>(_ scalars: S) -> String where S.Element == Unicode.Scalar {
        var view = String.UnicodeScalarView()
        view.append(contentsOf: scalars)
        return String(view)
    }

    static func join(_ tokens: ArraySlice<Scalars>) -> Scalars {
        var out: Scalars = []
        for (n, token) in tokens.enumerated() {
            if n > 0 { out.append(space) }
            out.append(contentsOf: token)
        }
        return out
    }

    /// Lowercase one scalar at a time so offsets into the original stay valid.
    static func lower(_ scalars: Scalars) -> Scalars {
        scalars.map { scalar in
            if scalar.isASCII {
                return (65...90).contains(scalar.value) ? Unicode.Scalar(scalar.value + 32)! : scalar
            }
            let lowered = String(scalar).lowercased().unicodeScalars
            return lowered.count == 1 ? lowered.first! : scalar
        }
    }

    /// Python's `str.isspace()` for one code point.
    static func isSpace(_ scalar: Unicode.Scalar) -> Bool {
        scalar.properties.isWhitespace || (0x1C...0x1F).contains(scalar.value)
    }

    /// Python's `str.isalnum()` for one code point.
    static func isAlnum(_ scalar: Unicode.Scalar) -> Bool {
        switch scalar.properties.generalCategory {
        case .uppercaseLetter, .lowercaseLetter, .titlecaseLetter, .modifierLetter, .otherLetter,
             .decimalNumber, .letterNumber, .otherNumber:
            return true
        default:
            return false
        }
    }

    /// Python regex `\w`.
    static func isWordChar(_ scalar: Unicode.Scalar) -> Bool {
        isAlnum(scalar) || scalar == "_"
    }

    static func strip(_ scalars: Scalars) -> Scalars {
        guard let first = scalars.firstIndex(where: { !isSpace($0) }),
              let last = scalars.lastIndex(where: { !isSpace($0) }) else { return [] }
        return Array(scalars[first...last])
    }

    /// `re.finditer(r"\S+", ...)`: (start, end) of each run of non-whitespace, as
    /// offsets into the slice's base array.
    static func nonSpaceRuns(_ scalars: ArraySlice<Unicode.Scalar>) -> [(Int, Int)] {
        var runs: [(Int, Int)] = []
        var start: Int? = nil
        for i in scalars.indices {
            if isSpace(scalars[i]) {
                if let s = start { runs.append((s, i)); start = nil }
            } else if start == nil {
                start = i
            }
        }
        if let s = start { runs.append((s, scalars.endIndex)) }
        return runs
    }

    /// `re.split(r" {2,}", ...)`: split on runs of two or more spaces.
    static func splitDoubleSpaces(_ scalars: Scalars) -> [Scalars] {
        var parts: [Scalars] = []
        var current: Scalars = []
        var i = 0
        while i < scalars.count {
            if scalars[i] == space {
                var j = i
                while j < scalars.count && scalars[j] == space { j += 1 }
                if j - i >= 2 {
                    parts.append(current)
                    current = []
                } else {
                    current.append(space)
                }
                i = j
            } else {
                current.append(scalars[i])
                i += 1
            }
        }
        parts.append(current)
        return parts
    }

    static func hasDoubleSpace(_ scalars: Scalars) -> Bool {
        guard scalars.count >= 2 else { return false }
        for i in 1..<scalars.count where scalars[i] == space && scalars[i - 1] == space {
            return true
        }
        return false
    }

    /// `^(\W*)(.*?)(\W*)$`: leading punctuation, core, trailing punctuation.
    static func splitPunctuation(_ tok: Scalars) -> (Scalars, Scalars, Scalars) {
        guard let first = tok.firstIndex(where: isWordChar),
              let last = tok.lastIndex(where: isWordChar) else { return (tok, [], []) }
        return (Array(tok[..<first]), Array(tok[first...last]), Array(tok[(last + 1)...]))
    }

    /// Python compares strings by code point; Swift's `<` does not.
    static func codePointLess(_ a: String, _ b: String) -> Bool {
        a.unicodeScalars.lexicographicallyPrecedes(b.unicodeScalars) { $0.value < $1.value }
    }

    /// Python's `round(x, 3)`: correctly rounded from the exact binary value.
    static func round3(_ x: Double) -> Double {
        Double(String(format: "%.3f", x)) ?? x
    }
}
