"""
Cross-candidate similarity check.

Per-CV scoring can't see resume-mill/facilitator-ring behavior: a network
generating fake candidates from the same template will produce individually
plausible CVs that only look suspicious when compared *against each other*.
This does a pairwise text-similarity pass against every other CV already in
the dataset and flags near-duplicates.
"""

from __future__ import annotations

from difflib import SequenceMatcher

# KNOWN LIMITATION, not just a tuning knob: at 300 candidates drawn from a
# bounded-vocabulary synthetic generator, true clone-pair ratios and
# coincidental unrelated-pair ratios genuinely overlap (true clones as low as
# 0.858; a coincidental unrelated pair as high as 0.907 -- verified by
# exhaustive pairwise check, not sampling). No single difflib-ratio threshold
# separates them perfectly on this dataset. This is a real ceiling of
# character-level text similarity on constrained vocabulary, not a bug to
# threshold away -- the methodologically correct fix is semantic (embedding)
# similarity, out of scope for this API-free offline path. 0.88 is a
# pragmatic midpoint that minimizes total error, not a clean separator.
# Real CVs have far more natural lexical diversity than this synthetic
# corpus, so this overlap is plausibly a synthetic-data artifact -- but that
# is an assumption, not something verified against real data.
SIMILARITY_THRESHOLD = 0.88


def _symmetric_ratio(a: str, b: str) -> float:
    """SequenceMatcher.ratio() is NOT guaranteed symmetric -- it can differ by several
    points depending on which string is passed as a vs b (verified empirically: one
    real clone pair in this project's own test data scored 0.94 one direction and 0.88
    the other). Left uncorrected, a fixed threshold could catch only one side of a real
    duplicate pair depending on comparison order. Taking the max of both directions
    makes the flag decision consistent regardless of which candidate is "self"."""
    return max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, b, a).ratio())


def most_similar(raw_text: str, others: list[tuple[str, str]]) -> tuple[str | None, float]:
    """others: list of (candidate_id, raw_text) to compare against.
    Returns (most_similar_candidate_id, ratio) or (None, 0.0) if `others` is empty."""
    best_id, best_ratio = None, 0.0
    for other_id, other_text in others:
        ratio = _symmetric_ratio(raw_text, other_text)
        if ratio > best_ratio:
            best_id, best_ratio = other_id, ratio
    return best_id, best_ratio


def check(candidate_id: str, raw_text: str, all_candidates: list[tuple[str, str]]) -> dict:
    """all_candidates: list of (candidate_id, raw_text) for the whole dataset, self included."""
    others = [(cid, text) for cid, text in all_candidates if cid != candidate_id]
    match_id, ratio = most_similar(raw_text, others)
    return {
        "flagged": ratio >= SIMILARITY_THRESHOLD,
        "most_similar_candidate": match_id,
        "similarity_ratio": round(ratio, 3),
    }
