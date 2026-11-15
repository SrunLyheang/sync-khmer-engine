// Edit-distance helpers for fuzzy matching (port of src/sing_khmer_engine/fuzzy.py).

enum Fuzzy {
    /// Number of single-character edits to turn `a` into `b`.
    static func levenshtein(_ a: [UInt32], _ b: [UInt32]) -> Int {
        if a == b { return 0 }
        if a.isEmpty { return b.count }
        if b.isEmpty { return a.count }
        var prev = Array(0...b.count)
        var cur = [Int](repeating: 0, count: b.count + 1)
        for i in 1...a.count {
            cur[0] = i
            for j in 1...b.count {
                let cost = a[i - 1] == b[j - 1] ? 0 : 1
                cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            }
            swap(&prev, &cur)
        }
        return prev[b.count]
    }

    /// Edit distance if it is `<= k`, else nil. Skips the work when the lengths alone
    /// rule it out.
    static func within(_ a: [UInt32], _ b: [UInt32], _ k: Int) -> Int? {
        if abs(a.count - b.count) > k { return nil }
        let d = levenshtein(a, b)
        return d <= k ? d : nil
    }
}
