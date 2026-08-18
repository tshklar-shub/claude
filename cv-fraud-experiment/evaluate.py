"""
Evaluate the scoring pipeline against synthetic ground truth.

Reports, at a chosen score threshold:
  - precision / recall / F1 for the binary fraud/clean classification
  - per-flag recall: of the flags we deliberately injected, how many did the
    scorer actually catch (this is the real pipeline-correctness signal)
"""

import argparse
import json

import db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=30.0, help="fraud_score >= threshold => predicted fraud")
    ap.add_argument("--db", type=str, default=None, help="path to a specific sqlite db (default: data/db/cv_fraud.sqlite3)")
    args = ap.parse_args()

    conn = db.connect(args.db)
    rows = db.fetch_all_results(conn)
    conn.close()

    if not rows:
        print("No results yet. Run generate_dataset.py then score_all.py first.")
        return

    tp = fp = tn = fn = 0
    flag_hits, flag_total = {}, {}

    for candidate_id, true_label, true_flags_json, fraud_score, matched_flags_json in rows:
        if true_label is None or fraud_score is None:
            continue
        true_flags = set(json.loads(true_flags_json or "[]"))
        matched_flags = set(json.loads(matched_flags_json or "[]"))
        predicted_fraud = fraud_score >= args.threshold
        actual_fraud = true_label == "fraud"

        if predicted_fraud and actual_fraud:
            tp += 1
        elif predicted_fraud and not actual_fraud:
            fp += 1
        elif not predicted_fraud and not actual_fraud:
            tn += 1
        else:
            fn += 1

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
    print(f"  Precision: {precision:.2f}")
    print(f"  Recall:    {recall:.2f}")
    print(f"  F1:        {f1:.2f}")

    print("\nPer-flag recall (of injected flags, how many did the scorer catch):")
    for flag in sorted(flag_total):
        hits, tot = flag_hits.get(flag, 0), flag_total[flag]
        print(f"  {flag:35s} {hits}/{tot}  ({hits/tot:.0%})")


if __name__ == "__main__":
    main()
