"""Batch-score every CV in data/cvs/ and store results in SQLite."""

from pathlib import Path

import db
from extract_cv import extract_fields
from score_cv import score_candidate

CV_DIR = Path(__file__).parent / "data" / "cvs"


def main():
    conn = db.connect()
    files = sorted(CV_DIR.glob("*.txt"))
    if not files:
        print(f"No CVs found in {CV_DIR}. Run generate_dataset.py first.")
        return

    for i, path in enumerate(files):
        candidate_id = path.stem.split("_")[-1]
        raw_text = path.read_text()
        # Assumes generate_dataset.py already inserted this candidate (with
        # ground-truth label/flags) -- we don't re-insert here so we don't
        # clobber that ground truth.
        print(f"[{i+1}/{len(files)}] scoring {path.name}...")
        extracted = extract_fields(raw_text)
        result = score_candidate(extracted, raw_text, candidate_id=candidate_id, conn=conn)
        db.insert_extraction(conn, candidate_id, extracted)
        db.insert_score(conn, candidate_id, result["fraud_score"], result["matched_flags"], result["reasoning"])
        print(f"    -> score={result['fraud_score']} flags={result['matched_flags']}")

    conn.close()
    print("\nDone. Run evaluate.py to see accuracy against ground truth.")


if __name__ == "__main__":
    main()
