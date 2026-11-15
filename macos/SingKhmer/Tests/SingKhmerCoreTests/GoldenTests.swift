import Foundation
import XCTest
@testable import SingKhmerCore

/// Replays inputs through the Swift port and compares every result with what the Python
/// engine produced for the same input (Fixtures/golden.json). If lookup.py changes and
/// Engine.swift is not updated to match, this is the test that fails.
final class GoldenTests: XCTestCase {
    private struct Golden: Decodable {
        let cases: [Case]
    }

    private struct Case: Decodable {
        let input: String
        let text: String
        let readings: [String]
        let convert: [Row]
        let segments: [SegmentRow]
    }

    private struct SegmentRow: Decodable {
        let surface: String
        let best: String
        let matched: Bool
        let candidates: [Row]
    }

    /// A candidate as Python wrote it: `[khmer, score, source]`.
    private struct Row: Decodable, Equatable {
        let khmer: String
        let score: Double
        let source: String

        init(_ c: Candidate) {
            khmer = c.khmer
            score = c.score
            source = c.source
        }

        init(from decoder: Decoder) throws {
            var row = try decoder.unkeyedContainer()
            khmer = try row.decode(String.self)
            score = try row.decode(Double.self)
            source = try row.decode(String.self)
        }
    }

    func testSwiftPortMatchesPythonEngine() throws {
        let engine = try Fixtures.requireEngine()
        let data = try XCTUnwrap(try? Data(contentsOf: Fixtures.goldenURL), Fixtures.missingMessage)
        let golden = try JSONDecoder().decode(Golden.self, from: data)
        XCTAssertGreaterThan(golden.cases.count, 1000)

        var failures: [String] = []
        func check<T: Equatable>(_ what: String, _ input: String, _ got: T, _ want: T) {
            if got != want {
                failures.append("\(what) for \(input.debugDescription):\n  swift:  \(got)\n  python: \(want)")
            }
        }

        for c in golden.cases {
            let segments = engine.decode(c.input)
            check("text", c.input, Engine.joinSegments(segments), c.text)
            check("readings", c.input, engine.readings(c.input, k: 3), c.readings)
            check("convert", c.input, engine.convert(c.input).map(Row.init), c.convert)
            check("segment count", c.input, segments.count, c.segments.count)
            for (got, want) in zip(segments, c.segments) {
                check("segment surface", c.input, got.surface, want.surface)
                check("segment best", c.input, got.best, want.best)
                check("segment matched", c.input, got.matched, want.matched)
                check("segment candidates", c.input, got.candidates.map(Row.init), want.candidates)
            }
        }

        if !failures.isEmpty {
            XCTFail("\(failures.count) mismatches against the Python engine. First few:\n"
                    + failures.prefix(10).joined(separator: "\n"))
        }
    }
}
