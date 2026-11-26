import XCTest
@testable import SingKhmerCore

/// Pick-to-teach: a spelling nothing matches offers loose guesses; taking one saves the
/// spelling (onTeach). Inputs are found in the real dictionary at test time, because the
/// dictionary changes whenever vocabulary.csv or wordlist_general.csv does.
final class PickToTeachTests: XCTestCase {
    private var engine: Engine!
    private var composer: Composer!
    private var taught: [(String, String)] = []
    private var misses: [String] = []
    private var doc = ""

    override func setUpWithError() throws {
        engine = try Fixtures.requireEngine()
        composer = Composer(engine: engine, history: History())
        taught = []
        misses = []
        composer.onTeach = { [unowned self] in self.taught.append(($0, $1)) }
        composer.onMiss = { [unowned self] in self.misses.append($0) }
        doc = ""
    }

    private func type(_ text: String) {
        for ch in text {
            let outcome = composer.handle(ch == " " ? .space : .character(ch), precedingIsKhmer: false)
            if let commit = outcome.commit { doc += commit }
            if !outcome.handled { doc.append(ch) }
        }
    }

    /// A non-English spelling that decodes to nothing but has loose guesses.
    private func unmatchedWithGuesses() throws -> String {
        for key in engine.index.keys.sorted() where key.count >= 6 && !key.contains(" ") {
            for i in key.indices.dropFirst(2) {
                var probe = key
                probe.replaceSubrange(i...i, with: "q")
                probe += "q"
                guard !engine.isEnglishWord(probe), engine.index[probe] == nil else { continue }
                let decoded = engine.decode(probe).filter { !$0.space }
                if decoded.count == 1, !decoded[0].matched,
                   !engine.convert(probe, limit: 5, fuzzy: true, strict: false).isEmpty {
                    return probe
                }
            }
        }
        throw XCTSkip("no suitable spelling in this dictionary")
    }

    func testUnmatchedSpellingOffersMarkedGuessesAfterTheLatin() throws {
        let probe = try unmatchedWithGuesses()
        type(probe)
        let options = composer.candidates
        XCTAssertEqual(options.first?.text, probe, "the Latin stays first")
        XCTAssertFalse(options[0].isGuess)
        XCTAssertGreaterThan(options.count, 1)
        XCTAssertTrue(options.dropFirst().allSatisfy { $0.isGuess && $0.teaches })
        XCTAssertLessThanOrEqual(options.count, 1 + Composer.maxGuesses)
    }

    func testSpaceKeepsTheLatinAndStillReportsAMiss() throws {
        let probe = try unmatchedWithGuesses()
        type(probe + " ")
        XCTAssertEqual(doc, probe + " ")
        XCTAssertTrue(taught.isEmpty, "space never takes a guess")
        XCTAssertEqual(misses, [probe])
    }

    func testANumberKeyTakesAGuessAndTeachesIt() throws {
        let probe = try unmatchedWithGuesses()
        type(probe)
        let guess = composer.candidates[1].text
        type("2")
        XCTAssertEqual(doc, guess)
        XCTAssertEqual(taught.count, 1)
        XCTAssertEqual(taught.first?.0, probe)
        XCTAssertEqual(taught.first?.1, guess)
        XCTAssertTrue(misses.isEmpty)

        // What the shell then does: the spelling now gives that word first.
        composer.replaceEngine(engine.addingUserWords([UserWord(latin: probe, khmer: guess)]))
        doc = ""
        type(probe + " ")
        XCTAssertEqual(doc, guess)
    }

    func testEnglishGetsNoGuesses() {
        type("hello")
        XCTAssertEqual(composer.candidates.map { $0.text }, ["hello"])
    }

    func testAWordFoundOnlyByAGuessedSpellingIsTaughtWhenTaken() throws {
        guard let (key, khmer) = engine.index.lazy
            .filter({ !$0.key.contains(" ") && $0.key.count >= 4 && !self.engine.isEnglishWord($0.key) })
            .compactMap({ k, cands -> (String, String)? in
                guard cands.count == 1, cands[0].source == "generated" else { return nil }
                return (k, cands[0].khmer)
            })
            .first(where: { self.engine.convertSentenceText($0.0) == $0.1 })
        else { throw XCTSkip("no guessed-only spelling in this dictionary") }
        type(key + " ")
        XCTAssertEqual(doc, khmer)
        XCTAssertEqual(taught.first?.0, key)
        XCTAssertEqual(taught.first?.1, khmer)
    }

    func testACollectedSpellingTeachesNothing() {
        type("nh ")
        XCTAssertTrue(taught.isEmpty)
    }
}
