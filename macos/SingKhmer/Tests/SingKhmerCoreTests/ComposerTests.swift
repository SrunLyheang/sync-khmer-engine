import XCTest
@testable import SingKhmerCore

/// The typing behaviour of the input method, driven key by key. Expected Khmer comes
/// from the engine itself, so these tests check the typing rules rather than the
/// dictionary (which changes whenever vocabulary.csv does).
final class ComposerTests: XCTestCase {
    private var engine: Engine!
    private var composer: Composer!

    override func setUpWithError() throws {
        engine = try Fixtures.requireEngine()
        composer = Composer(engine: engine)
    }

    /// Types `text` and returns everything that ended up in the "document".
    @discardableResult
    private func type(_ text: String, into document: inout String) -> String {
        for ch in text {
            let key: Composer.Key = ch == " " ? .space : .character(ch)
            apply(composer.handle(key, precedingIsKhmer: precedingIsKhmer(document)),
                  typed: ch, to: &document)
        }
        return document
    }

    private func press(_ key: Composer.Key, into document: inout String) {
        apply(composer.handle(key, precedingIsKhmer: precedingIsKhmer(document)),
              typed: nil, to: &document)
    }

    /// Confirms a word still underlined at the end of typing (see the multi-word test).
    private func flush(into document: inout String) {
        if composer.isComposing { press(.enter, into: &document) }
    }

    private func apply(_ outcome: Composer.Outcome, typed: Character?, to document: inout String) {
        if let commit = outcome.commit { document += commit }
        if !outcome.handled, let typed = typed { document.append(typed) }
    }

    private func precedingIsKhmer(_ document: String) -> Bool {
        document.unicodeScalars.last.map(Composer.isKhmer) ?? false
    }

    private func khmer(_ latin: String) -> String {
        engine.convertSentenceText(latin)
    }

    func testLettersComposeAndSpaceCommitsTopCandidate() {
        var doc = ""
        type("nh", into: &doc)
        XCTAssertEqual(doc, "", "nothing is committed while composing")
        XCTAssertEqual(composer.buffer, "nh")
        XCTAssertEqual(composer.markedText, "nh")
        XCTAssertEqual(composer.candidates.first, khmer("nh"))
        XCTAssertEqual(composer.candidates.last, "nh", "the Latin as typed is always offered last")
        type(" ", into: &doc)
        XCTAssertEqual(doc, khmer("nh"))
        XCTAssertFalse(composer.isComposing)
    }

    func testKhmerWordsRunTogetherAndSecondSpaceIsReal() {
        var doc = ""
        type("nh srolanh ", into: &doc)
        XCTAssertEqual(doc, khmer("nh") + khmer("srolanh"))
        type(" ", into: &doc)
        XCTAssertEqual(doc, khmer("nh") + khmer("srolanh") + " ")
        type("bong  ", into: &doc)
        XCTAssertEqual(doc, khmer("nh") + khmer("srolanh") + " " + khmer("bong") + " ")
    }

    func testSentenceMatchesEngineOutput() {
        for sentence in ["nh srolanh bong", "soksabay te", "hello bong how are", "ok bong", "nhslbong"] {
            composer.reset()
            var doc = ""
            type(sentence + " ", into: &doc)
            flush(into: &doc)
            let expected = khmer(sentence)
            // The engine output has no trailing space; typing leaves one after a Latin word.
            XCTAssertEqual(doc.trimmingCharacters(in: .whitespaces), expected, sentence)
        }
    }

    func testNumberKeyPicksAHomophone() throws {
        var doc = ""
        type("jg", into: &doc)
        let options = composer.candidates
        try XCTSkipIf(options.count < 3, "jg no longer has two Khmer readings")
        type("2", into: &doc)
        XCTAssertEqual(doc, options[1])
        XCTAssertFalse(composer.isComposing)
    }

    func testArrowsMoveTheHighlightAndWrap() {
        var doc = ""
        type("jg", into: &doc)
        let options = composer.candidates
        press(.next, into: &doc)
        XCTAssertEqual(composer.selected, 1 % options.count)
        press(.previous, into: &doc)
        press(.previous, into: &doc)
        XCTAssertEqual(composer.selected, options.count - 1)
        press(.enter, into: &doc)
        XCTAssertEqual(doc, "jg", "the last option is the Latin as typed")
    }

    func testEscapeKeepsLatinAndEnterCommitsKhmer() {
        var doc = ""
        type("bong", into: &doc)
        press(.escape, into: &doc)
        XCTAssertEqual(doc, "bong")

        doc = ""
        type("bong", into: &doc)
        press(.enter, into: &doc)
        XCTAssertEqual(doc, khmer("bong"))
    }

    func testBackspaceEditsTheBufferThenFallsThrough() {
        var doc = ""
        type("bonh", into: &doc)
        XCTAssertTrue(composer.handle(.backspace).handled)
        XCTAssertEqual(composer.buffer, "bon")
        type("g ", into: &doc)
        flush(into: &doc)
        XCTAssertEqual(doc, khmer("bong"))
        XCTAssertFalse(composer.handle(.backspace).handled, "idle backspace belongs to the app")
    }

    func testPunctuationCommitsThenPassesThrough() {
        var doc = ""
        type("bong?", into: &doc)
        XCTAssertEqual(doc, khmer("bong") + "?")
        doc = ""
        type("123, ", into: &doc)
        XCTAssertEqual(doc, "123, ", "digits and punctuation are untouched when idle")
    }

    func testEnglishWordsKeepTheirSpaces() {
        var doc = ""
        type("hello world ", into: &doc)
        XCTAssertEqual(doc, "hello world ")
        doc = ""
        composer.reset()
        type("bong hello bong ", into: &doc)
        flush(into: &doc)
        XCTAssertEqual(doc, khmer("bong") + " hello " + khmer("bong"))
    }

    func testMultiWordSpellingSurvivesTheSpace() throws {
        try XCTSkipIf(engine.index["msel minh"] == nil, "msel minh is no longer a spelling")
        var doc = ""
        type("msel ", into: &doc)
        XCTAssertEqual(doc, "", "the space might be part of a multi-word spelling")
        XCTAssertEqual(composer.candidates.first, khmer("msel"), "the first word is still offered")
        XCTAssertEqual(composer.markedText, khmer("msel"), "and is shown already converted")
        type("mi", into: &doc)
        XCTAssertEqual(composer.markedText, khmer("msel") + "mi")
        type("nh ", into: &doc)
        XCTAssertEqual(doc, khmer("msel minh"))

        // When the next word rules the multi-word spelling out, the first word commits.
        doc = ""
        composer.reset()
        type("msel nh ", into: &doc)
        XCTAssertEqual(doc, khmer("msel") + khmer("nh"))
    }

    func testCommitPendingAndOtherKeys() {
        var doc = ""
        XCTAssertNil(composer.commitPending())
        type("bong", into: &doc)
        XCTAssertEqual(composer.commitPending(), khmer("bong"))
        XCTAssertFalse(composer.isComposing)

        type("bong", into: &doc)
        let outcome = composer.handle(.other)
        XCTAssertEqual(outcome, Composer.Outcome(handled: false, commit: khmer("bong")))
        XCTAssertEqual(composer.handle(.other), Composer.Outcome(handled: false, commit: nil))
    }

    func testEveryCandidateListIsUsable() {
        for input in ["a", "b", "nh", "jg", "bongrean", "xyzzyq", "Hello", "nhslbong", "muy muy"] {
            composer.reset()
            var doc = ""
            type(input.replacingOccurrences(of: " ", with: ""), into: &doc)
            XCTAssertFalse(composer.candidates.isEmpty, input)
            XCTAssertLessThanOrEqual(composer.candidates.count, Composer.maxCandidates, input)
            XCTAssertEqual(Set(composer.candidates).count, composer.candidates.count, input)
        }
    }
}
