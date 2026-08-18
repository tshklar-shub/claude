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

# Two resumes for the same *role* will share boilerplate (section headers,
# generic phrasing) even when written by unrelated people -- calibrated
# empirically against this project's own synthetic set. A naive 0.55 cutoff
# produced a false positive between two unrelated but short, sparsely-worded
# CVs (ratio 0.63-0.64, driven by shared headers/boilerplate rather than real
# duplication), while the deliberately cloned pair in this dataset scored
# 0.88-0.94. 0.75 sits with margin above the false-positive case and below
# the real clone.
SIMILARITY_THRESHOLD = 0.75


def most_similar(raw_text: str, others: list[tuple[str, str]]) -> tuple[str | None, float]:
    """others: list of (candidate_id, raw_text) to compare against.
    Returns (most_similar_candidate_id, ratio) or (None, 0.0) if `others` is empty."""
    best_id, best_ratio = None, 0.0
    for other_id, other_text in others:
        ratio = SequenceMatcher(None, raw_text, other_text).ratio()
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
