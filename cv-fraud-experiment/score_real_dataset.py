"""
Batch-score a folder of normalized (plain-text) real CVs using local-model
extraction + red-flag scoring + cross-candidate similarity. Unlike
score_all.py (which expects the labeled synthetic naming convention), this
takes an arbitrary folder and stores every candidate with true_label=None
(unknown -- there's no ground truth for real data).

Uses local_llm_client (Ollama) via extract_cv.py/score_cv.py, not the
Anthropic API -- real candidate CV text must not leave this machine. Requires
Ollama installed and running with a model pulled; no API key needed.

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
from score_cv import score_candidate


def stable_id(path: Path) -> str:
    return hashlib.sha256(path.name.encode()).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=str, required=True, help="folder of normalized .txt CVs (see ingest_cvs.py)")
    ap.add_argument("--db", type=str, default="data/db/cv_fraud_real.sqlite3")
    ap.add_argument("--dry-run", action="store_true", help="skip local-model calls, just verify wiring")
    args = ap.parse_args()

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
        result = score_candidate(extracted, raw_text, candidate_id=candidate_id, conn=conn)
        db.insert_extraction(conn, candidate_id, extracted)
        db.insert_score(conn, candidate_id, result["fraud_score"], result["matched_flags"], result["reasoning"])
        print(f"    score={result['fraud_score']}  flags={result['matched_flags']}")

    conn.close()
    if args.dry_run:
        print(f"\n[dry-run] {len(files)} candidates registered, no scoring performed.")
    else:
        print(f"\nScored {len(files)} candidates. Run report.py to view results.")


if __name__ == "__main__":
    main()
