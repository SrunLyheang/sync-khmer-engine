import Foundation

// The typing logic of the input method, kept free of AppKit so it can be unit-tested
// (and reused by an iOS keyboard later). The macOS shell turns each key press into a
// `Composer.Key`, calls `handle`, and then does what the returned `Outcome` says.
//
// It works the way a Chinese pinyin keyboard does:
//   letters      build up underlined Latin; a numbered row of Khmer candidates follows
//   space        takes the highlighted candidate (the first one unless moved)
//   1-9          takes that candidate
//   arrows/tab   move the highlight
//   return       keeps the Latin exactly as typed
//   escape       cancels: throws the typed letters away
//   backspace    deletes the last typed letter; pressed right after a word was
//                converted, it brings the Latin back so it can be fixed (undo)
//   anything else (punctuation, shortcuts) takes the first candidate, then goes to the
//                app as normal
//
// Also like pinyin: several words can be typed with no spaces (nhjgtov). The row then
// offers the whole phrase first, followed by choices for just the FIRST word; taking
// one of those converts that word and leaves the rest still being typed.
//
// Spacing follows Khmer writing: words run together, so the space that takes a Khmer
// candidate is swallowed and a SECOND space types a real one. Words left in Latin
// (English) keep normal spaces around them.

public final class Composer {
    public enum Key: Equatable {
        case character(Character)   // any printable character
        case space
        case backspace
        case enter
        case escape
        case next                   // right / down / tab
        case previous               // left / up / shift-tab
        case other                  // shortcuts, function keys, forward delete, ...
    }

    public struct Outcome: Equatable {
        /// True if the key was consumed. False means the app should receive it as usual
        /// (after `commit`, if any, has been inserted).
        public var handled: Bool
        /// Text to insert into the document now.
        public var commit: String?

        static let passThrough = Outcome(handled: false, commit: nil)
        static let consumed = Outcome(handled: true, commit: nil)
    }

    /// One entry in the candidate row.
    public struct Option: Equatable {
        /// What gets inserted.
        public let text: String
        /// The typed letters it replaces.
        public let latin: String
        /// True if it covers only the first word, leaving the rest being typed.
        public let isPartial: Bool
        /// A loose guess for a spelling nothing matched (pick-to-teach). Shown marked;
        /// space never takes it, only its number key does.
        public var isGuess: Bool = false
        /// Taking it teaches the keyboard `latin` -> `text` (saved to my_words.txt):
        /// guesses, and words found only through a guessed spelling.
        public var teaches: Bool = false

        public init(text: String, latin: String, isPartial: Bool,
                    isGuess: Bool = false, teaches: Bool = false) {
            self.text = text
            self.latin = latin
            self.isPartial = isPartial
            self.isGuess = isGuess
            self.teaches = teaches
        }
    }

    /// The most recent conversion, while it can still be undone with backspace.
    public struct Undoable: Equatable {
        public let latin: String    // what had been typed
        public let text: String     // what was inserted for it
    }

    public static let maxCandidates = 9
    private static let maxWhole = 6
    /// Pick-to-teach guesses offered when nothing matches.
    public static let maxGuesses = 5

    private var engine: Engine
    private let history: History
    /// Called with a spelling that matched nothing and was kept as Latin (and is not
    /// English): a word the dictionary is missing.
    public var onMiss: ((String) -> Void)?
    /// Called with (spelling, Khmer) when the user takes a guess: the shell saves it to
    /// my_words.txt so the spelling gives that word first from then on.
    public var onTeach: ((String, String) -> Void)?

    /// The Latin text being composed (shown underlined in the document).
    public private(set) var buffer = ""
    /// What the buffer can become, best first.
    public private(set) var candidates: [Option] = []
    public private(set) var selected = 0
    public private(set) var undoable: Undoable?
    /// Whether the last thing this composer inserted ended in Khmer; used only when the
    /// shell cannot read the document to see what precedes the cursor.
    private var lastEndedKhmer = false

    public init(engine: Engine, history: History = History()) {
        self.engine = engine
        self.history = history
    }

    public var isComposing: Bool { !buffer.isEmpty }

    /// What to show underlined in the document. Normally the Latin being typed. Once a
    /// space has been typed but kept (because a multi-word spelling may follow), the
    /// words before it are shown already converted, so a space always visibly converts.
    public var markedText: String {
        guard let lastSpace = buffer.lastIndex(of: " ") else { return buffer }
        let tail = String(buffer[buffer.index(after: lastSpace)...])
        if tail.isEmpty { return implicitOption.text }
        return engine.convertSentenceText(String(buffer[..<lastSpace])) + tail
    }

    /// Swap in a new engine (the user's word list changed). Keeps what is being typed.
    public func replaceEngine(_ new: Engine) {
        engine = new
        let current = buffer
        setBuffer(current)
    }

    /// Handle one key press.
    ///
    /// - Parameter precedingIsKhmer: whether the character just before the composition
    ///   is Khmer, if the shell could read it from the document; nil if unknown.
    public func handle(_ key: Key, precedingIsKhmer: Bool? = nil) -> Outcome {
        guard isComposing else { return handleIdle(key) }
        switch key {
        case .character(let ch) where Composer.isLetter(ch) || ch == "'":
            // A space is kept in the buffer only while it might be part of a multi-word
            // spelling (bong rean). The moment the new letter rules that out, the
            // word(s) before the space are committed and the letter starts a new word.
            if buffer.hasSuffix(" ") && !engine.isMultiWordPrefix(buffer + String(ch)) {
                let option = implicitOption
                learn(option)
                let text = commitText(option.text, boundary: true, precedingIsKhmer)
                setBuffer(ch == "'" ? "" : String(ch))
                return Outcome(handled: ch != "'", commit: text)
            }
            setBuffer(buffer + String(ch))
            return .consumed

        case .character(let ch):
            if let digit = ch.wholeNumberValue, ch.isASCII, digit >= 1, digit <= candidates.count {
                return choose(digit - 1, precedingIsKhmer)
            }
            // Punctuation, or a digit with no matching candidate: commit, then let the
            // app type the character itself.
            return finish(implicitOption, boundary: false, handled: false, precedingIsKhmer)

        case .space:
            if buffer.hasSuffix(" ") {
                // A second space: commit and type a real space.
                let option = implicitOption
                learn(option)
                let text = commitText(option.text, boundary: false, precedingIsKhmer)
                setBuffer("")
                lastEndedKhmer = false
                return Outcome(handled: true, commit: text.hasSuffix(" ") ? text : text + " ")
            }
            if selected == 0 && engine.isMultiWordPrefix(buffer + " ") {
                setBuffer(buffer + " ")          // might be a multi-word spelling: wait
                return .consumed
            }
            return choose(selected, precedingIsKhmer)

        case .backspace:
            setBuffer(String(buffer.dropLast()))
            return .consumed

        case .enter:
            let typed = Composer.trimmed(buffer)
            return finish(Option(text: typed, latin: typed, isPartial: false),
                          boundary: false, handled: true, precedingIsKhmer)

        case .escape:
            setBuffer("")
            return .consumed

        case .next:
            selected = (selected + 1) % candidates.count
            return .consumed

        case .previous:
            selected = (selected + candidates.count - 1) % candidates.count
            return .consumed

        case .other:
            return finish(implicitOption, boundary: false, handled: false, precedingIsKhmer)
        }
    }

    /// End the composition because the app asked for it (focus moved, input source
    /// switched). Returns the text to insert, or nil if nothing was being composed.
    public func commitPending(precedingIsKhmer: Bool? = nil) -> String? {
        guard isComposing else { return nil }
        let commit = finish(implicitOption, boundary: false, handled: true, precedingIsKhmer).commit
        undoable = nil
        return commit
    }

    /// Bring back the Latin of the last conversion. The shell calls this for a
    /// backspace pressed right after a conversion, once it has removed `undoable.text`
    /// from the document. Returns false if there is nothing to undo.
    public func undoLastCommit() -> Bool {
        guard let last = undoable else { return false }
        undoable = nil
        lastEndedKhmer = false
        setBuffer(last.latin)
        return true
    }

    /// Forget everything (the cursor moved somewhere this composer knows nothing about).
    public func reset() {
        setBuffer("")
        lastEndedKhmer = false
        undoable = nil
    }

    // MARK: - Internals

    private func handleIdle(_ key: Key) -> Outcome {
        undoable = nil                           // only the very next key can undo
        if case .character(let ch) = key, Composer.isLetter(ch) {
            setBuffer(String(ch))
            return .consumed
        }
        // Not ours. The cursor may move or other text may be typed, so what we last
        // inserted is no longer a reliable guide to what precedes the cursor.
        lastEndedKhmer = false
        return .passThrough
    }

    /// The candidate a non-explicit commit uses (punctuation, focus change): the
    /// highlighted one, unless that covers only part of what was typed.
    private var implicitOption: Option {
        if !candidates[selected].isPartial { return candidates[selected] }
        return candidates.first { !$0.isPartial } ?? candidates[selected]
    }

    /// Take candidate `index` because the user picked it (space or a number key).
    private func choose(_ index: Int, _ precedingIsKhmer: Bool?) -> Outcome {
        let option = candidates[index]
        guard option.isPartial else {
            return finish(option, boundary: true, handled: true, precedingIsKhmer)
        }
        learn(option)
        let text = commitText(option.text, boundary: true, precedingIsKhmer)
        setBuffer(String(buffer.dropFirst(option.latin.count)))   // keep typing the rest
        return Outcome(handled: true, commit: text)
    }

    private func finish(_ option: Option, boundary: Bool, handled: Bool,
                        _ precedingIsKhmer: Bool?) -> Outcome {
        learn(option)
        let commit = commitText(option.text, boundary: boundary, precedingIsKhmer)
        setBuffer("")
        if handled {
            undoable = Undoable(latin: option.latin, text: commit)
        } else {
            lastEndedKhmer = false               // the app is about to type something itself
        }
        return Outcome(handled: handled, commit: commit)
    }

    /// Remember the choice, and report a spelling the dictionary does not know.
    private func learn(_ option: Option) {
        history.record(spelling: option.latin, chosen: option.text)
        if option.teaches {
            onTeach?(option.latin.lowercased(), option.text)
            return
        }
        let isOnlyLatin = candidates.allSatisfy { $0.isGuess || $0.text == $0.latin }
            && option.text == option.latin
        if isOnlyLatin, option.latin.count >= 2, option.latin.allSatisfy(Composer.isLetter),
           !engine.isEnglishWord(option.latin) {
            onMiss?(option.latin.lowercased())
        }
    }

    /// Add the spaces Khmer writing does not need but Latin words do.
    private func commitText(_ text: String, boundary: Bool, _ precedingIsKhmer: Bool?) -> String {
        var out = text
        if let first = text.unicodeScalars.first, Composer.isLatinWordScalar(first),
           precedingIsKhmer ?? lastEndedKhmer {
            out = " " + out                      // Latin right after Khmer
        }
        if boundary, let last = text.unicodeScalars.last, Composer.isLatinWordScalar(last) {
            out += " "                           // the space that ended a Latin word
        }
        lastEndedKhmer = out.unicodeScalars.last.map(Composer.isKhmer) ?? false
        return out
    }

    private func setBuffer(_ new: String) {
        buffer = new
        selected = 0
        candidates = buffer.isEmpty ? [] : makeCandidates(Composer.trimmed(buffer))
    }

    private func makeCandidates(_ text: String) -> [Option] {
        // Per word, put the user's habitual choice first.
        let segments = engine.decode(text, limit: Composer.maxCandidates).map { segment -> Segment in
            guard segment.candidates.count > 1, segment.display == nil else { return segment }
            var copy = segment
            copy.candidates = history.ranked(segment.candidates, spelling: segment.surface) { $0.khmer }
            return copy
        }

        let words = segments.filter { !$0.space }
        if words.count == 1, let only = words.first, !only.matched, only.lead.isEmpty,
           only.trail.isEmpty, only.surface == text {
            return guessOptions(text)
        }
        // A single word found only through a guessed spelling: taking it teaches it.
        let guessed: Set<String> = words.count == 1 && !text.contains(" ")
            ? Set(words[0].candidates.filter { $0.source == "generated" }.map { $0.khmer }) : []

        // Whole-buffer candidates.
        var whole: [String] = []
        func add(_ s: String) {
            if !s.isEmpty && !whole.contains(s) { whole.append(s) }
        }
        add(Engine.joinSegments(segments))
        if words.count == 1, let only = words.first, only.matched {
            for c in only.candidates.dropFirst() {          // homophones, then English
                add(only.lead + c.khmer + only.trail)
            }
        }
        for reading in engine.readings(text, k: 4) {        // compound vs. split, etc.
            add(reading)
        }
        whole = Array(whole.filter { $0 != text }.prefix(Composer.maxWhole))
        // The Latin as typed is always offered, last unless the user habitually keeps it.
        let ranked = history.ranked(whole + [text], spelling: text) { $0 }
        let latinFirst = ranked.first == text && whole.count > 0
        whole = ranked.filter { $0 != text }

        // Candidates for just the first word, when several were typed run together.
        var partial: [Option] = []
        if words.count > 1, !text.contains(" "), let first = words.first, first.matched,
           first.lead.isEmpty, first.trail.isEmpty, text.hasPrefix(first.surface) {
            for c in first.candidates where !whole.contains(c.khmer) {
                partial.append(Option(text: c.khmer, latin: first.surface, isPartial: true))
            }
        }

        var out: [Option] = []
        let latin = Option(text: text, latin: text, isPartial: false)
        if latinFirst { out.append(latin) }
        out += whole.map {
            Option(text: $0, latin: text, isPartial: false, teaches: guessed.contains($0))
        }
        out += partial.prefix(Composer.maxCandidates - 1 - out.count)
        if !latinFirst { out.append(latin) }
        return out
    }

    /// Nothing matched `text`: offer the Latin first (so space keeps it, as before),
    /// then the closest words by loose matching, guessed spellings included. English is
    /// never guessed at. Taking a guess teaches it (see `Option.teaches`).
    private func guessOptions(_ text: String) -> [Option] {
        let latin = Option(text: text, latin: text, isPartial: false)
        guard text.count >= 2, text.allSatisfy(Composer.isLetter),
              !engine.isEnglishWord(text) else { return [latin] }
        let guesses = engine.convert(text, limit: Composer.maxGuesses, fuzzy: true, strict: false)
            .filter { $0.source != "english" && $0.khmer != text }
            .map { Option(text: $0.khmer, latin: text, isPartial: false, isGuess: true, teaches: true) }
        return [latin] + guesses
    }

    private static func trimmed(_ s: String) -> String {
        s.hasSuffix(" ") ? String(s.dropLast()) : s
    }

    static func isLetter(_ ch: Character) -> Bool {
        ch.isASCII && ch.isLetter
    }

    public static func isKhmer(_ scalar: Unicode.Scalar) -> Bool {
        (0x1780...0x17FF).contains(scalar.value) || (0x19E0...0x19FF).contains(scalar.value)
    }

    static func isLatinWordScalar(_ scalar: Unicode.Scalar) -> Bool {
        Engine.isAlnum(scalar) && !isKhmer(scalar)
    }
}
