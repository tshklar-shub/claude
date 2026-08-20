"""
Batch-score a folder of normalized (plain-text) real CVs using local-model
extraction + red-flag scoring + cross-candidate similarity. Unlike
score_all.py (which expects the labeled synthetic naming convention), this
takes an arbitrary folder and stores every candidate with true_label=None
(unknown -- there's no ground truth for real data).

Uses local_llm_client (Ollama) via extract_cv.py, not the Anthropic API --
real candidate CV text must not leave this machine. Requires Ollama installed
and running with a model pulled; no API key needed.

Scoring defaults to hybrid_score.py (one LLM call for extraction, then
deterministic Python for red-flag matching) rather than score_cv.py's second
LLM call for scoring. Measured on a 16-candidate real-formatted (PDF/DOCX/TXT)
test batch against known ground truth: hybrid scoring got 15/16 correct
(precision 0.90, recall 1.00) in half the model calls of two-call LLM scoring,
which got 10/16 correct (precision 0.67, recall 0.67) on the identical
extracted data. Pass --llm-scoring to use the old two-call path instead (e.g.
to compare, or if you want the nuanced-judgment flags LOW-confidence in
hybrid_score.py -- overly_polished_language, education_credential_implausible,
unverifiable_company_shell -- judged by the model instead of a keyword list).

Usage:
    python3 ingest_cvs.py --src /path/to/real/cvs --out data/real_cvs_txt
    python3 score_real_dataset.py --dir data/real_cvs_txt --db data/db/cv_fraud_real.sqlite3

Add --dry-run to verify file discovery / DB wiring without calling the local model.
"""

import argparse
import hashlib
from pathlib import Path

import db
from extract_cv import extract_fields


def stable_id(path: Path) -> str:
    return hashlib.sha256(path.name.encode()).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=str, required=True, help="folder of normalized .txt CVs (see ingest_cvs.py)")
    ap.add_argument("--db", type=str, default="data/db/cv_fraud_real.sqlite3")
    ap.add_argument("--dry-run", action="store_true", help="skip local-model calls, just verify wiring")
    ap.add_argument("--llm-scoring", action="store_true",
                     help="use the slower two-LLM-call path (score_cv.py) instead of hybrid_score.py's "
                          "single-extraction-call + deterministic scoring")
    args = ap.parse_args()

    if args.llm_scoring:
        from score_cv import score_candidate as llm_score_candidate
    else:
        import hybrid_score

    cv_dir = Path(__file__).parent / args.dir
    files = sorted(cv_dir.glob("*.txt"))
    if not files:
        print(f"No .txt CVs found in {cv_dir}. Run ingest_cvs.py first.")
        return

    conn = db.connect(Path(__file__).parent / args.db)

    for i, path in enumerate(files):
        candidate_id = stable_id(path)
        raw_text = path.read_text()
        db.insert_candidate(conn, candidate_id, path.name, raw_text, true_label=None)
        print(f"[{i+1}/{len(files)}] {path.name} (id={candidate_id})")

        if args.dry_run:
            continue

        extracted = extract_fields(raw_text)
        db.insert_extraction(conn, candidate_id, extracted)

        if args.llm_scoring:
            result = llm_score_candidate(extracted, raw_text, candidate_id=candidate_id, conn=conn)
        else:
            all_candidates = db.fetch_all_raw_texts(conn)
            result = hybrid_score.score_candidate(candidate_id, extracted, raw_text, all_candidates)

        db.insert_score(conn, candidate_id, result["fraud_score"], result["matched_flags"], result["reasoning"])
        print(f"    score={result['fraud_score']}  flags={result['matched_flags']}")

    conn.close()
    if args.dry_run:
        print(f"\n[dry-run] {len(files)} candidates registered, no scoring performed.")
    else:
        print(f"\nScored {len(files)} candidates. Run report.py to view results.")


if __name__ == "__main__":
    main()
