"""
CLI: python score_cv.py path/to/candidate.txt

Runs extraction, then asks Claude to judge which documented red flags
(redflags.py) are present given the extracted fields + raw text, computes a
weighted fraud score, and stores everything in SQLite.
"""

import argparse
import json
import uuid
from pathlib import Path

import db
import similarity_check
from claude_client import complete_json
from extract_cv import extract_fields
from redflags import RED_FLAGS, MAX_POSSIBLE_SCORE, flags_by_id

SCORING_SYSTEM = """You are a hiring-fraud screening assistant. Given a candidate's extracted CV
fields and the raw CV text, judge which of the listed red-flag patterns are actually present.
Be conservative: only flag a pattern if there is real textual evidence for it, not because it's
merely possible. Output strict JSON only, no commentary or markdown fencing."""


def build_scoring_prompt(extracted: dict, raw_text: str) -> str:
    flag_list = "\n".join(f"- {f['id']}: {f['description']}" for f in RED_FLAGS)
    return f"""RED FLAG DEFINITIONS:
{flag_list}

EXTRACTED FIELDS:
{json.dumps(extracted, indent=2)}

RAW CV TEXT:
---
{raw_text}
---

Return JSON: {{
  "matched_flags": [list of red flag ids that are actually present, evidence-based],
  "reasoning": "2-4 sentences explaining the key evidence for each matched flag"
}}"""


def score_candidate(extracted: dict, raw_text: str, candidate_id: str = None, conn=None) -> dict:
    # 4000, not 1000: this model's internal reasoning consumes tokens from the same
    # max_tokens budget before it produces the final answer, so a tight budget can
    # exhaust itself mid-thinking and return zero actual output (seen in practice).
    judged = complete_json(SCORING_SYSTEM, build_scoring_prompt(extracted, raw_text), max_tokens=4000)
    by_id = flags_by_id()
    matched = [f for f in judged.get("matched_flags", []) if f in by_id]
    reasoning = judged.get("reasoning", "")

    sim_note = ""
    if conn is not None and candidate_id is not None:
        all_candidates = db.fetch_all_raw_texts(conn)
        sim = similarity_check.check(candidate_id, raw_text, all_candidates)
        if sim["flagged"]:
            matched.append("template_reuse_across_candidates")
            sim_note = (f" Near-duplicate text found (similarity={sim['similarity_ratio']:.2f}) "
                        f"vs candidate {sim['most_similar_candidate']}.")

    raw_score = sum(by_id[f]["weight"] for f in matched)
    fraud_score = round(100 * raw_score / MAX_POSSIBLE_SCORE, 1)
    return {
        "matched_flags": matched,
        "fraud_score": fraud_score,
        "reasoning": reasoning + sim_note,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cv_path", type=str, help="path to a plain-text CV file")
    args = ap.parse_args()

    path = Path(args.cv_path)
    raw_text = path.read_text()

    conn = db.connect()
    candidate_id = path.stem.split("_")[-1] if "_" in path.stem else str(uuid.uuid4())[:8]
    true_label = "fraud" if path.stem.startswith("fraud_") else ("clean" if path.stem.startswith("clean_") else None)
    db.insert_candidate(conn, candidate_id, path.name, raw_text, true_label=true_label)

    print(f"Extracting fields from {path.name}...")
    extracted = extract_fields(raw_text)

    print("Scoring against documented red flags + cross-candidate similarity...")
    result = score_candidate(extracted, raw_text, candidate_id=candidate_id, conn=conn)

    print(f"\nFraud score: {result['fraud_score']}/100")
    print(f"Matched flags: {result['matched_flags']}")
    print(f"Reasoning: {result['reasoning']}")

    db.insert_extraction(conn, candidate_id, extracted)
    db.insert_score(conn, candidate_id, result["fraud_score"], result["matched_flags"], result["reasoning"])
    conn.close()


if __name__ == "__main__":
    main()
