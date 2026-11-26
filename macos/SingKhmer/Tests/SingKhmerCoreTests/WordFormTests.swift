import XCTest
@testable import SingKhmerCore

final class WordFormTests: XCTestCase {
    func testSpellingsSplitOnCommasAndKeepMultiWord() {
        XCTAssertEqual(WordForm.spellings("Kom Tov, komtov,kom+tov"), ["kom tov", "komtov"])
        XCTAssertEqual(WordForm.spellings("  sneha ,, 123, ស្នេហា "), ["sneha"])
        XCTAssertEqual(WordForm.spellings("pha'er"), ["pha'er"])
    }

    func testKhmerIsKeptAsTypedButNotMixedWithLatin() {
        XCTAssertEqual(WordForm.khmer(from: " ស្នេហា ", engine: nil), "ស្នេហា")
        XCTAssertNil(WordForm.khmer(from: "ស្នេហា abc", engine: nil))
        XCTAssertNil(WordForm.khmer(from: "   ", engine: nil))
        XCTAssertNil(WordForm.khmer(from: "sneha", engine: nil))
    }

    func testLatinIsComposedFromKnownWords() throws {
        let engine = try Fixtures.requireEngine()
        let khmer = try XCTUnwrap(WordForm.khmer(from: "nh srolanh bong", engine: engine))
        XCTAssertEqual(khmer, engine.decode("nh srolanh bong").filter { !$0.space }.map { $0.best }.joined())
        XCTAssertFalse(khmer.contains(" "))
        XCTAssertNil(WordForm.khmer(from: "nh qqqzzzx", engine: engine))
    }

    func testNotesWarnAboutExistingSpellings() throws {
        let engine = try Fixtures.requireEngine()
        let top = try XCTUnwrap(engine.index["jg"]?.first?.khmer)
        XCTAssertEqual(WordForm.notes(spellings: ["jg"], khmer: top, engine: engine),
                       ["jg already gives \(top)."])
        let clash = WordForm.notes(spellings: ["jg"], khmer: "ក", engine: engine)
        XCTAssertEqual(clash.count, 1)
        XCTAssertTrue(clash[0].hasSuffix("yours will come first."))
        XCTAssertEqual(WordForm.notes(spellings: ["qqqzzzx"], khmer: "ក", engine: engine), [])
    }

    func testAppendingWritesLinesTheParserReadsBack() throws {
        let start = "# header\njrern ច្រើន"
        let words = [UserWord(latin: "kom tov", khmer: "កុំទៅ"),
                     UserWord(latin: "jrern", khmer: "ច្រើន"),
                     UserWord(latin: "kom tov", khmer: "កុំទៅ")]
        let text = try XCTUnwrap(WordForm.appending(words, to: start))
        XCTAssertEqual(text, "# header\njrern ច្រើន\nkom tov កុំទៅ\n")
        XCTAssertEqual(UserWord.parse(text), [UserWord(latin: "jrern", khmer: "ច្រើន"),
                                              UserWord(latin: "kom tov", khmer: "កុំទៅ")])
        XCTAssertNil(WordForm.appending([UserWord(latin: "jrern", khmer: "ច្រើន")], to: text))
    }

    func testMostMissedOrdersByCount() {
        var log = MissLog()
        ["b", "a", "b", "c", "a", "b"].forEach { log.record($0) }
        XCTAssertEqual(log.mostMissed, ["b", "a", "c"])
    }
}
