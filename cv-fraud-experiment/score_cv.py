"""
CLI: python score_cv.py path/to/candidate.txt

Runs extraction, then asks the local model to judge which documented red
flags (redflags.py) are present given the extracted fields + raw text,
computes a weighted fraud score, and stores everything in SQLite.

Uses local_llm_client (Ollama), not claude_client -- see extract_cv.py's
module docstring for why. This is the module that handles real candidate
CVs; keep it local.
"""

import argparse
import json
import uuid
from pathlib import Path

import db
import similarity_check
from local_llm_client import complete_json
from extract_cv import extract_fields
from redflags import RED_FLAGS, RED_FLAG_IDS, MAX_POSSIBLE_SCORE, flags_by_id

# Constrains matched_flags to {flag_id, evidence_quote} objects at the token level --
# flag_id restricted to actual known ids, evidence_quote required (forces the model to
# cite something rather than assert a bare conclusion).
SCORING_SCHEMA = {
    "type": "object",
    "properties": {
        "matched_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "flag_id": {"type": "string", "enum": RED_FLAG_IDS},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["flag_id", "evidence_quote"],
            },
        },
        "reasoning": {"type": "string"},
    },
    "required": ["matched_flags", "reasoning"],
}

SCORING_SYSTEM = """You are a hiring-fraud screening assistant. Given a candidate's extracted CV
fields and the raw CV text, judge which of the listed red-flag patterns are actually present.
Be conservative: only flag a pattern if there is real textual evidence for it, not because it's
merely possible. For any date-based flag (overlapping_employment_dates, employment_gaps_unexplained,
high_job_turnover, illogical_progression, seniority_experience_mismatch), you must quote the exact
literal date strings you are comparing as your evidence_quote -- do not assert an overlap or gap
without quoting both dates side by side. If you cannot quote specific supporting text, do not
include that flag. Output strict JSON only, no commentary or markdown fencing."""


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

For each red flag you believe is present, quote the exact text from the CV that supports it --
this is mandatory, not optional. If a flag involves comparing two dates (overlap, gap, timeline),
quote both date strings verbatim.

Return JSON: {{
  "matched_flags": [
    {{"flag_id": "<one of the red flag ids above>", "evidence_quote": "<exact text from the CV supporting this, verbatim>"}}
  ],
  "reasoning": "2-4 sentences summarizing the overall assessment"
}}"""


def score_candidate(extracted: dict, raw_text: str, candidate_id: str = None, conn=None) -> dict:
    # Generous max_tokens: some local models emit reasoning/preamble before the
    # actual JSON despite instructions not to, and a tight budget can cut that off
    # before any usable output is produced. See local_llm_client.complete_json for
    # the fallback JSON-extraction logic that also compensates for this. SCORING_SCHEMA
    # constrains matched_flags to {flag_id, evidence_quote} objects so a claimed flag
    # always carries its cited evidence, not just a bare id.
    judged = complete_json(SCORING_SYSTEM, build_scoring_prompt(extracted, raw_text),
                            max_tokens=4000, schema=SCORING_SCHEMA)
    by_id = flags_by_id()

    # Still defensive about shape even with a schema -- constrained decoding reduces but
    # doesn't guarantee zero drift (seen in practice pre-schema: reasoning came back as a
    # list of strings instead of a single string).
    raw_matched = judged.get("matched_flags", [])
    if not isinstance(raw_matched, list):
        raw_matched = [raw_matched]
    matched, evidence_by_flag = [], {}
    for item in raw_matched:
        if isinstance(item, dict):
            flag_id, quote = item.get("flag_id"), item.get("evidence_quote", "")
        elif isinstance(item, str):
            flag_id, quote = item, ""
        else:
            continue
        if isinstance(flag_id, str) and flag_id in by_id and flag_id not in matched:
            matched.append(flag_id)
            if quote:
                evidence_by_flag[flag_id] = str(quote)

    raw_reasoning = judged.get("reasoning", "")
    if isinstance(raw_reasoning, list):
        reasoning = " ".join(str(r) for r in raw_reasoning)
    else:
        reasoning = str(raw_reasoning) if raw_reasoning else ""
    if evidence_by_flag:
        quotes = "; ".join(f"{fid}: \"{q}\"" for fid, q in evidence_by_flag.items())
        reasoning = f"{reasoning} [evidence: {quotes}]".strip()

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
