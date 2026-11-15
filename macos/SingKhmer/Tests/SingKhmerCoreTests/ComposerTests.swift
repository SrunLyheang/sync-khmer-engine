import XCTest
@testable import SingKhmerCore

/// The typing behaviour of the input method, driven key by key against a pretend
/// document. Expected Khmer comes from the engine itself, so these tests check the
/// typing rules rather than the dictionary (which changes whenever vocabulary.csv does).
final class ComposerTests: XCTestCase {
    private var engine: Engine!
    private var history: History!
    private var composer: Composer!
    private var doc = ""

    override func setUpWithError() throws {
        engine = try Fixtures.requireEngine()
        history = History()
        composer = Composer(engine: engine, history: history)
        doc = ""
    }

    // MARK: - A pretend document, driven the way the macOS shell drives the Composer

    private func type(_ text: String) {
        for ch in text {
            press(ch == " " ? .space : .character(ch), typed: ch)
        }
    }

    private func press(_ key: Composer.Key, typed: Character? = nil) {
        if key == .backspace, !composer.isComposing {
            // Same check the shell makes: undo only if the document still ends with
            // exactly what was inserted.
            if let last = composer.undoable, doc.hasSuffix(last.text), composer.undoLastCommit() {
                doc.removeLast(last.text.count)
                return
            }
            _ = composer.handle(.backspace)
            if !doc.isEmpty { doc.removeLast() }
            return
        }
        let precedingIsKhmer = doc.unicodeScalars.last.map(Composer.isKhmer) ?? false
        let outcome = composer.handle(key, precedingIsKhmer: precedingIsKhmer)
        if let commit = outcome.commit { doc += commit }
        if !outcome.handled, let typed = typed { doc.append(typed) }
    }

    /// Finishes a word still underlined at the end (focus moving away does this).
    private func flush() {
        if let text = composer.commitPending() { doc += text }
    }

    private func khmer(_ latin: String) -> String {
        engine.convertSentenceText(latin)
    }

    private var texts: [String] { composer.candidates.map { $0.text } }

    // MARK: - Basics

    func testLettersComposeAndSpaceTakesTheFirstCandidate() {
        type("nh")
        XCTAssertEqual(doc, "", "nothing is inserted while composing")
        XCTAssertEqual(composer.markedText, "nh")
        XCTAssertEqual(texts.first, khmer("nh"))
        XCTAssertEqual(texts.last, "nh", "the Latin as typed is always offered last")
        type(" ")
        XCTAssertEqual(doc, khmer("nh"))
        XCTAssertFalse(composer.isComposing)
    }

    func testKhmerWordsRunTogetherAndSecondSpaceIsReal() {
        type("nh srolanh ")
        XCTAssertEqual(doc, khmer("nh") + khmer("srolanh"))
        type(" ")
        XCTAssertEqual(doc, khmer("nh") + khmer("srolanh") + " ")
    }

    func testSentencesMatchTheEngine() {
        for sentence in ["nh srolanh bong", "soksabay te", "hello bong how are", "ok bong", "nhslbong"] {
            composer.reset()
            doc = ""
            type(sentence + " ")
            flush()
            // The engine output has no trailing space; typing leaves one after a Latin word.
            XCTAssertEqual(doc.trimmingCharacters(in: .whitespaces), khmer(sentence), sentence)
        }
    }

    func testReturnKeepsTheLatinAndEscapeCancels() {
        type("bong")
        press(.enter)
        XCTAssertEqual(doc, "bong")
        XCTAssertFalse(composer.isComposing)

        type("bong")
        press(.escape)
        XCTAssertEqual(doc, "bong", "escape throws the typed letters away")
        XCTAssertFalse(composer.isComposing)
        XCTAssertFalse(composer.handle(.escape).handled, "idle escape belongs to the app")
    }

    func testPunctuationCommitsThenPassesThrough() {
        type("bong?")
        XCTAssertEqual(doc, khmer("bong") + "?")
        doc = ""
        type("123, ")
        XCTAssertEqual(doc, "123, ", "digits and punctuation are untouched when idle")
    }

    func testEnglishWordsKeepTheirSpaces() {
        type("hello world ")
        XCTAssertEqual(doc, "hello world ")
        doc = ""
        composer.reset()
        type("bong hello bong ")
        flush()
        XCTAssertEqual(doc, khmer("bong") + " hello " + khmer("bong"))
    }

    // MARK: - Picking candidates

    func testNumberKeyPicksAHomophone() throws {
        type("jg")
        let options = texts
        try XCTSkipIf(options.count < 3, "jg no longer has two Khmer readings")
        type("2")
        XCTAssertEqual(doc, options[1])
        XCTAssertFalse(composer.isComposing)
    }

    func testArrowsMoveTheHighlightAndWrap() {
        type("jg")
        let options = texts
        press(.next)
        XCTAssertEqual(composer.selected, 1 % options.count)
        press(.previous)
        press(.previous)
        XCTAssertEqual(composer.selected, options.count - 1)
        type(" ")
        XCTAssertEqual(doc, "jg ", "the last option is the Latin as typed")
    }

    func testRunTogetherTypingOffersTheFirstWordOnItsOwn() throws {
        type("jgnh")
        XCTAssertEqual(texts.first, khmer("jgnh"), "the whole phrase comes first")
        let partials = composer.candidates.filter { $0.isPartial }
        try XCTSkipIf(partials.isEmpty, "jg no longer has a second reading")
        XCTAssertTrue(partials.allSatisfy { $0.latin == "jg" })

        let index = try XCTUnwrap(composer.candidates.firstIndex(of: partials[0]))
        type(String(index + 1))
        XCTAssertEqual(doc, partials[0].text, "only the first word is converted")
        XCTAssertEqual(composer.buffer, "nh", "the rest is still being typed")
        type(" ")
        XCTAssertEqual(doc, partials[0].text + khmer("nh"))
    }

    func testEveryCandidateListIsUsable() {
        for input in ["a", "b", "nh", "jg", "bongrean", "xyzzyq", "Hello", "nhslbong", "muymuy", "nhjgtovpsar"] {
            composer.reset()
            type(input)
            XCTAssertFalse(texts.isEmpty, input)
            XCTAssertLessThanOrEqual(texts.count, Composer.maxCandidates, input)
            XCTAssertFalse(composer.candidates[0].isPartial, input)
            XCTAssertEqual(texts.filter { $0 == input }.count, 1, "the Latin is offered once: \(input)")
            let whole = composer.candidates.filter { !$0.isPartial }.map { $0.text }
            XCTAssertEqual(Set(whole).count, whole.count, input)
        }
    }

    // MARK: - Undo

    func testBackspaceEditsWhileComposing() {
        type("bonh")
        press(.backspace)
        XCTAssertEqual(composer.buffer, "bon")
        type("g")
        flush()
        XCTAssertEqual(doc, khmer("bong"))
    }

    func testBackspaceRightAfterAConversionBringsTheLatinBack() {
        type("nh srolan ")
        let converted = doc
        XCTAssertNotNil(composer.undoable)
        press(.backspace)
        XCTAssertEqual(doc, khmer("nh"), "the converted word is removed from the document")
        XCTAssertEqual(composer.buffer, "srolan", "and is being typed again")
        type("h ")
        XCTAssertEqual(doc, khmer("nh") + khmer("srolanh"))
        XCTAssertEqual(converted, doc, "srolan was a typo for the same word")
    }

    func testUndoIsOnlyForTheVeryNextKey() {
        type("nh ")
        type("!")
        XCTAssertNil(composer.undoable)
        press(.backspace)
        XCTAssertEqual(doc, khmer("nh"), "a normal backspace: it deleted the !")
        XCTAssertFalse(composer.isComposing)
    }

    func testUndoRestoresALatinWordWithItsSpace() {
        type("hello ")
        XCTAssertEqual(doc, "hello ")
        press(.backspace)
        XCTAssertEqual(doc, "")
        XCTAssertEqual(composer.buffer, "hello")
    }

    // MARK: - Multi-word spellings

    func testMultiWordSpellingSurvivesTheSpace() throws {
        let key = "bong rean"
        try XCTSkipIf(engine.index[key] == nil || !engine.isMultiWordPrefix("bong "),
                      "bong rean is no longer a spelling that needs its words together")
        type("bong ")
        XCTAssertEqual(doc, "", "the space might be part of a multi-word spelling")
        XCTAssertEqual(composer.markedText, khmer("bong"), "but the word shows converted")
        type("re")
        XCTAssertEqual(composer.markedText, khmer("bong") + "re")
        type("an ")
        XCTAssertEqual(doc, khmer(key))

        // When the next word rules the multi-word spelling out, the first word commits.
        doc = ""
        composer.reset()
        type("bong nh ")
        XCTAssertEqual(doc, khmer("bong") + khmer("nh"))
    }

    func testSpaceConvertsImmediatelyWhenWordsNeedNotStayTogether() throws {
        // msel minh gives the same Khmer typed as one spelling or as two words, so
        // there is no reason to hold msel back.
        try XCTSkipIf(khmer("msel") + khmer("minh") != khmer("msel minh"), "data changed")
        type("msel ")
        XCTAssertEqual(doc, khmer("msel"))
        type("minh ")
        XCTAssertEqual(doc, khmer("msel minh"))
    }

    // MARK: - Learning

    func testTheKeyboardLearnsWhichHomophoneYouUse() throws {
        type("jg")
        let before = texts
        try XCTSkipIf(before.count < 3, "jg no longer has two Khmer readings")
        press(.escape)

        // An established habit: the default has been accepted several times.
        for _ in 0..<3 { type("jg ") }
        type("jg")
        type("2")
        type("jg")
        XCTAssertEqual(texts.first, before[0], "one odd pick does not change an established default")
        let index = try XCTUnwrap(texts.firstIndex(of: before[1]))
        type(String(index + 1))
        type("jg")
        XCTAssertEqual(texts.first, before[1], "picked twice in a row: now the default")
        press(.escape)

        // The habit also applies inside a longer run of words.
        composer.reset()
        doc = ""
        type("nhjg ")
        XCTAssertEqual(doc, khmer("nh") + before[1])
    }

    func testKeepingAWordInLatinIsLearnedToo() {
        for _ in 0..<2 {
            type("you")
            press(.enter)
        }
        type("you")
        XCTAssertEqual(texts.first, "you")
        type(" ")
        XCTAssertTrue(doc.hasSuffix("you "))
    }

    func testHistorySurvivesSaving() throws {
        history.record(spelling: "JG", chosen: "x")
        let restored = try History(data: history.encoded())
        XCTAssertEqual(restored.weight(spelling: "jg", text: "x"), 1)
        XCTAssertEqual(restored.weight(spelling: "jg", text: "y"), 0)
    }

    func testUnknownWordsAreReportedButEnglishIsNot() {
        var misses: [String] = []
        composer.onMiss = { misses.append($0) }
        type("xyzzyq hello nh ")
        XCTAssertEqual(misses, ["xyzzyq"])
    }

    // MARK: - The user's own words

    func testUserWordsParse() {
        let words = UserWord.parse("""
            # my words
            jrern  ច្រើន
            Ot Ey = អត់អី

            broken line with no khmer
            ១២៣
            """)
        XCTAssertEqual(words, [UserWord(latin: "jrern", khmer: "ច្រើន"),
                               UserWord(latin: "ot ey", khmer: "អត់អី")])
    }

    func testUserWordsComeFirstAndWorkInsideSentences() {
        let taught = engine.addingUserWords(UserWord.parse("xyzzyq តេស្ត\nnh តេស្ត\nqq ww តេស្ត"))
        XCTAssertEqual(taught.convertSentenceText("xyzzyq"), "តេស្ត")
        XCTAssertEqual(taught.convertSentenceText("nh"), "តេស្ត", "a user word outranks the dictionary")
        XCTAssertEqual(taught.convert("nh").dropFirst().first?.khmer, khmer("nh"), "which stays available")
        XCTAssertEqual(taught.convertSentenceText("bongxyzzyq"), khmer("bong") + "តេស្ត")
        XCTAssertEqual(taught.convertSentenceText("qq ww"), "តេស្ត")
        XCTAssertEqual(taught.convertSentenceText("qqww"), "តេស្ត")
        XCTAssertEqual(engine.convertSentenceText("xyzzyq"), "xyzzyq", "the original engine is untouched")

        composer.replaceEngine(taught)
        type("xyzzyq ")
        XCTAssertEqual(doc, "តេស្ត")
    }

    func testMissLogRoundTrips() {
        var log = MissLog()
        ["tov", "Tov", "ey"].forEach { log.record($0) }
        XCTAssertEqual(MissLog(text: log.formatted()), log)
        XCTAssertTrue(log.formatted().contains("2\ttov\n1\tey\n"))
        log.remove(["TOV"])
        XCTAssertEqual(log.counts, ["ey": 1])
    }
}

extension ComposerTests {
    func testFirstEverPickIsRememberedStraightAway() throws {
        type("jg")
        let before = texts
        try XCTSkipIf(before.count < 3, "jg no longer has two Khmer readings")
        type("2")
        type("jg")
        XCTAssertEqual(texts.first, before[1], "with no habit yet, the pick becomes the default")
    }
}
