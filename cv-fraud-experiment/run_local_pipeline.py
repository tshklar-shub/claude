"""
End-to-end offline pipeline: load a local_generator.py dataset (CVs +
_manifest.json with ground truth), run rule_based_extract + rule_based_score
(with cross-candidate similarity) on every candidate, store in a dedicated
sqlite DB, and print an evaluate.py-style report. No API key required.

Usage:
    python3 local_generator.py --n 300 --seed 1 --out data/cvs_large
    python3 run_local_pipeline.py --dir data/cvs_large --db data/db/cv_fraud_large.sqlite3
"""

import argparse
import json
from pathlib import Path

import db
import rule_based_score
from rule_based_extract import extract_fields


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=str, default="data/cvs_large")
    ap.add_argument("--db", type=str, default="data/db/cv_fraud_large.sqlite3")
    ap.add_argument("--threshold", type=float, default=13.0,
                     help="calibrated against a 300-candidate run: precision 1.00, recall 0.92, F1 0.96 (see README)")
    args = ap.parse_args()

    cv_dir = Path(__file__).parent / args.dir
    manifest = json.loads((cv_dir / "_manifest.json").read_text())

    conn = db.connect(Path(__file__).parent / args.db)

    for entry in manifest:
        raw_text = (cv_dir / entry["file"]).read_text()
        db.insert_candidate(conn, entry["id"], entry["file"], raw_text,
                             true_label=entry["label"], true_injected_flags=entry["injected_flags"])

    all_texts = db.fetch_all_raw_texts(conn)

    for entry in manifest:
        raw_text = (cv_dir / entry["file"]).read_text()
        extracted = extract_fields(raw_text)
        result = rule_based_score.score_candidate(entry["id"], extracted, raw_text, all_texts)
        db.insert_extraction(conn, entry["id"], extracted)
        db.insert_score(conn, entry["id"], result["fraud_score"], result["matched_flags"], result["reasoning"])

    rows = db.fetch_all_results(conn)
    conn.close()

    tp = fp = tn = fn = 0
    flag_hits, flag_total = {}, {}
    fp_ids, fn_ids = [], []

    for candidate_id, true_label, true_flags_json, fraud_score, matched_flags_json in rows:
        true_flags = set(json.loads(true_flags_json or "[]"))
        matched_flags = set(json.loads(matched_flags_json or "[]"))
        predicted_fraud = fraud_score >= args.threshold
        actual_fraud = true_label == "fraud"

        if predicted_fraud and actual_fraud:
            tp += 1
        elif predicted_fraud and not actual_fraud:
            fp += 1
            fp_ids.append(candidate_id)
        elif not predicted_fraud and not actual_fraud:
            tn += 1
        else:
            fn += 1
            fn_ids.append(candidate_id)

        for flag in true_flags:
            flag_total[flag] = flag_total.get(flag, 0) + 1
            if flag in matched_flags:
                flag_hits[flag] = flag_hits.get(flag, 0) + 1

    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"Scored candidates: {total}  (threshold={args.threshold})")
    print(f"  TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall:    {recall:.3f}")
    print(f"  F1:        {f1:.3f}")
    print(f"  False positives: {fp_ids}")
    print(f"  False negatives: {fn_ids}")

    print("\nPer-flag recall:")
    for flag in sorted(flag_total):
        hits, tot = flag_hits.get(flag, 0), flag_total[flag]
        print(f"  {flag:35s} {hits}/{tot}  ({hits/tot:.0%})")


if __name__ == "__main__":
    main()
