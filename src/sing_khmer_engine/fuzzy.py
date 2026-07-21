"""Edit-distance helpers for fuzzy matching (step 1.8).

Sing Khmer has no fixed spelling, so a typed word often won't match a collected
spelling exactly (`srolan` vs `srolanh`). Levenshtein (edit) distance measures how
many single-character insert/delete/substitute edits separate two strings; the
lookup uses it to find the closest known spellings when there's no exact hit.
"""

from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Number of single-character edits to turn ``a`` into ``b``."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def within(a: str, b: str, k: int) -> int | None:
    """Edit distance between ``a`` and ``b`` if it is ``<= k``, else ``None``.

    A quick length-difference check skips the full computation when the strings
    are too different in length to possibly be within ``k`` edits.
    """
    if abs(len(a) - len(b)) > k:
        return None
    d = levenshtein(a, b)
    return d if d <= k else None
