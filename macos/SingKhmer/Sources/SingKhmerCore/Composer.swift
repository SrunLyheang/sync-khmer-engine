import Foundation

// The typing logic of the input method, kept free of AppKit so it can be unit-tested
// (and reused by an iOS keyboard later). The macOS shell turns each key press into a
// `Composer.Key`, calls `handle`, and then does what the returned `Outcome` says.
//
// Behaviour, as decided in CLAUDE.md ("Text Replacement style, with a suggestion strip"):
//   letters      build up an underlined Latin word; the candidate list updates live
//   space        commits the highlighted candidate (the top one unless changed). If the
//                word could be the start of a multi-word spelling (msel minh), it is
//                shown converted but stays underlined until the next key settles it.
//   1-9          commits that candidate
//   arrows/tab   move the highlight
//   return       commits the highlighted candidate (does not also send the message)
//   escape       keeps the Latin exactly as typed
//   backspace    deletes the last typed letter
//   anything else (punctuation, shortcuts) commits, then goes to the app as normal
//
// Spacing follows the engine's own rule: Khmer words run together, so the space that
// commits a Khmer word is swallowed and a SECOND space types a real one. Words left in
// Latin (English) keep normal spaces around them.

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

    public static let maxCandidates = 9

    private let engine: Engine
    /// The Latin text being composed (shown underlined in the document).
    public private(set) var buffer = ""
    /// What the buffer can become, best first. The last entry is always the Latin as typed.
    public private(set) var candidates: [String] = []
    public private(set) var selected = 0
    /// Whether the last thing this composer inserted ended in Khmer; used only when the
    /// shell cannot read the document to see what precedes the cursor.
    private var lastEndedKhmer = false

    public init(engine: Engine) {
        self.engine = engine
    }

    public var isComposing: Bool { !buffer.isEmpty }

    /// What to show underlined in the document. Normally the Latin being typed. Once a
    /// space has been typed but kept (because a multi-word spelling may follow), the
    /// words before it are shown already converted, so a space always visibly converts.
    public var markedText: String {
        guard let lastSpace = buffer.lastIndex(of: " ") else { return buffer }
        let tail = String(buffer[buffer.index(after: lastSpace)...])
        if tail.isEmpty { return candidates[selected] }
        return engine.convertSentenceText(String(buffer[..<lastSpace])) + tail
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
            // spelling (msel minh). The moment the new letter rules that out, the
            // word(s) before the space are committed and the letter starts a new word.
            if buffer.hasSuffix(" ") && !engine.isMultiWordPrefix(buffer + String(ch)) {
                let text = commitText(candidates[selected], boundary: true, precedingIsKhmer)
                setBuffer(ch == "'" ? "" : String(ch))
                return Outcome(handled: ch != "'", commit: text)
            }
            setBuffer(buffer + String(ch))
            return .consumed

        case .character(let ch):
            if let digit = ch.wholeNumberValue, ch.isASCII, digit >= 1, digit <= candidates.count {
                return finish(candidates[digit - 1], boundary: true, handled: true, precedingIsKhmer)
            }
            // Punctuation, or a digit with no matching candidate: commit, then let the
            // app type the character itself.
            return finish(candidates[selected], boundary: false, handled: false, precedingIsKhmer)

        case .space:
            if buffer.hasSuffix(" ") {
                // A second space: commit and type a real space.
                let text = commitText(candidates[selected], boundary: false, precedingIsKhmer)
                setBuffer("")
                lastEndedKhmer = false
                return Outcome(handled: true, commit: text.hasSuffix(" ") ? text : text + " ")
            }
            if selected == 0 && engine.isMultiWordPrefix(buffer + " ") {
                setBuffer(buffer + " ")          // might be a multi-word spelling: wait
                return .consumed
            }
            return finish(candidates[selected], boundary: true, handled: true, precedingIsKhmer)

        case .backspace:
            setBuffer(String(buffer.dropLast()))
            return .consumed

        case .enter:
            return finish(candidates[selected], boundary: false, handled: true, precedingIsKhmer)

        case .escape:
            return finish(Composer.trimmed(buffer), boundary: false, handled: true, precedingIsKhmer)

        case .next:
            selected = (selected + 1) % candidates.count
            return .consumed

        case .previous:
            selected = (selected + candidates.count - 1) % candidates.count
            return .consumed

        case .other:
            return finish(candidates[selected], boundary: false, handled: false, precedingIsKhmer)
        }
    }

    /// End the composition because the app asked for it (focus moved, input source
    /// switched). Returns the text to insert, or nil if nothing was being composed.
    public func commitPending(precedingIsKhmer: Bool? = nil) -> String? {
        guard isComposing else { return nil }
        return finish(candidates[selected], boundary: false, handled: true, precedingIsKhmer).commit
    }

    /// Forget everything (the cursor moved somewhere this composer knows nothing about).
    public func reset() {
        setBuffer("")
        lastEndedKhmer = false
    }

    // MARK: - Internals

    private func handleIdle(_ key: Key) -> Outcome {
        if case .character(let ch) = key, Composer.isLetter(ch) {
            setBuffer(String(ch))
            return .consumed
        }
        // Not ours. The cursor may move or other text may be typed, so what we last
        // inserted is no longer a reliable guide to what precedes the cursor.
        lastEndedKhmer = false
        return .passThrough
    }

    private func finish(_ text: String, boundary: Bool, handled: Bool,
                        _ precedingIsKhmer: Bool?) -> Outcome {
        let commit = commitText(text, boundary: boundary, precedingIsKhmer)
        setBuffer("")
        if !handled { lastEndedKhmer = false }   // the app is about to type something itself
        return Outcome(handled: handled, commit: commit)
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

    private func makeCandidates(_ text: String) -> [String] {
        var out: [String] = []
        func add(_ s: String) {
            if !s.isEmpty && !out.contains(s) { out.append(s) }
        }
        let segments = engine.decode(text, limit: Composer.maxCandidates)
        add(Engine.joinSegments(segments))
        if segments.count == 1, let only = segments.first, only.matched {
            for c in only.candidates.dropFirst() {          // homophones, then English
                add(only.lead + c.khmer + only.trail)
            }
        }
        for reading in engine.readings(text, k: 4) {        // compound vs. split, etc.
            add(reading)
        }
        out = Array(out.prefix(Composer.maxCandidates - 1))
        add(text)                                           // always: the Latin as typed
        return out
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
