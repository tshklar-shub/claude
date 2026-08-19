"""
Anomaly review report: surfaces every individual flagged anomaly (one row per
candidate x matched-flag) with its evidence, for a human to review one by one.

Different purpose from report.py (which ranks whole candidates for triage):
this is granular -- every flag instance gets its own row, with the flag's
description/category so a reviewer doesn't need this codebase open to judge
it, plus a blank verdict/notes column for recording the review.

Where ground truth exists (the synthetic datasets, not real data), each flag
instance is also marked confirmed/unconfirmed against it and a per-flag-type
breakdown table is added -- this is what lets you evaluate the *detector*,
not just triage candidates: e.g. "unverifiable_company_shell fired 12 times,
11 confirmed, 1 unconfirmed" tells you that heuristic is trustworthy, while a
flag with a lot of "unconfirmed" hits needs recalibration.

Usage:
    python3 anomaly_report.py --db data/db/cv_fraud_large.sqlite3 --out data/reports/anomaly_review
    python3 anomaly_report.py --db data/db/cv_fraud_real.sqlite3 --out data/reports/anomaly_review_real
"""

import argparse
import csv
import json
from pathlib import Path

import db
from redflags import flags_by_id

BY_ID = flags_by_id()

HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>CV Anomaly Review</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #1a1a1a; background: #fff; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  .caveat {{ background: #fff3cd; border: 1px solid #ffe69c; padding: 0.75rem 1rem; border-radius: 6px; margin: 1rem 0; font-size: 0.9rem; }}
  .summary {{ margin-bottom: 1rem; font-size: 0.95rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.83rem; margin-bottom: 1rem; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f5f5f5; position: sticky; top: 0; }}
  tr.confirmed {{ background: #f0f9f0; }}
  tr.unconfirmed {{ background: #fde2e1; }}
  tr.unknown {{ background: #fff; }}
  .badge {{ display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }}
  .badge.confirmed {{ background: #c8e6c9; color: #1b5e20; }}
  .badge.unconfirmed {{ background: #f8bbd0; color: #880e4f; }}
  .badge.unknown {{ background: #eee; color: #555; }}
  .cat {{ font-size: 0.75rem; color: #777; }}
  .desc {{ font-size: 0.78rem; color: #444; max-width: 320px; }}
  .verdict-col {{ width: 90px; }}
</style></head>
<body>
<h1>CV Anomaly Review</h1>
<div class="summary">{n_candidates} candidates &middot; {n_anomalies} flagged anomalies across {n_flagged_candidates} candidates</div>
<div class="caveat">
  Each row is one flagged anomaly with its evidence. {gt_note}
  Use the blank <strong>Verdict</strong> column (in the CSV) to record your own review --
  it's intentionally not pre-filled.
</div>

<h2>Per-flag-type breakdown{gt_suffix}</h2>
<table>
<tr><th>Flag</th><th>Category</th><th>Times fired</th>{gt_cols}</tr>
{breakdown_rows}
</table>

<h2>All flagged anomalies (one row per candidate &times; flag)</h2>
<table>
<tr><th>Score</th><th>Candidate</th><th>Source file</th><th>Flag</th><th>Category</th><th>Description</th>{gt_col}<th>Reasoning</th></tr>
{anomaly_rows}
</table>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, required=True)
    ap.add_argument("--out", type=str, default="data/reports/anomaly_review")
    args = ap.parse_args()

    conn = db.connect(Path(__file__).parent / args.db)
    rows = conn.execute(
        """
        SELECT c.id, c.source_file, c.true_label, c.true_injected_flags,
               s.fraud_score, s.matched_flags, s.reasoning
        FROM candidates c LEFT JOIN scores s ON s.candidate_id = c.id
        WHERE s.fraud_score IS NOT NULL
        ORDER BY s.fraud_score DESC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No scored candidates found in {args.db}.")
        return

    has_ground_truth = any(true_label is not None for _, _, true_label, *_ in rows)

    out_dir = Path(__file__).parent / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    anomaly_instances = []  # (score, cid, src, flag_id, verdict)
    flag_counts = {}        # flag_id -> {"total": n, "confirmed": n, "unconfirmed": n}

    for cid, src, true_label, true_flags_json, score, matched_json, reasoning in rows:
        true_flags = set(json.loads(true_flags_json or "[]"))
        matched = json.loads(matched_json or "[]")
        for flag_id in matched:
            if has_ground_truth and true_label is not None:
                verdict = "confirmed" if flag_id in true_flags else "unconfirmed"
            else:
                verdict = "unknown"
            anomaly_instances.append((score, cid, src, flag_id, verdict, reasoning))
            fc = flag_counts.setdefault(flag_id, {"total": 0, "confirmed": 0, "unconfirmed": 0})
            fc["total"] += 1
            if verdict != "unknown":
                fc[verdict] += 1

    flagged_candidates = {cid for _, cid, *_ in anomaly_instances}

    # CSV: one row per anomaly instance, with a blank verdict column for manual review
    csv_path = out_dir / "anomaly_review.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        header = ["score", "candidate_id", "source_file", "flag_id", "category", "description"]
        if has_ground_truth:
            header.append("ground_truth")
        header += ["reasoning", "reviewer_verdict", "reviewer_notes"]
        w.writerow(header)
        for score, cid, src, flag_id, verdict, reasoning in anomaly_instances:
            meta = BY_ID.get(flag_id, {})
            row = [score, cid, src, flag_id, meta.get("category", ""), meta.get("description", "")]
            if has_ground_truth:
                row.append(verdict)
            row += [reasoning or "", "", ""]
            w.writerow(row)

    # HTML: breakdown + full anomaly table
    gt_cols = "<th>Confirmed</th><th>Unconfirmed</th><th>Confirm rate</th>" if has_ground_truth else ""
    breakdown_rows = []
    for flag_id, counts in sorted(flag_counts.items(), key=lambda kv: -kv[1]["total"]):
        meta = BY_ID.get(flag_id, {})
        extra = ""
        if has_ground_truth:
            rate = counts["confirmed"] / counts["total"] if counts["total"] else 0
            extra = f"<td>{counts['confirmed']}</td><td>{counts['unconfirmed']}</td><td>{rate:.0%}</td>"
        breakdown_rows.append(
            f"<tr><td>{flag_id}</td><td class='cat'>{meta.get('category','')}</td>"
            f"<td>{counts['total']}</td>{extra}</tr>"
        )

    gt_col = "<th>Ground truth</th>" if has_ground_truth else ""
    anomaly_rows = []
    for score, cid, src, flag_id, verdict, reasoning in anomaly_instances:
        meta = BY_ID.get(flag_id, {})
        badge = f'<span class="badge {verdict}">{verdict}</span>' if has_ground_truth else ""
        gt_cell = f"<td>{badge}</td>" if has_ground_truth else ""
        anomaly_rows.append(
            f'<tr class="{verdict}"><td>{score}</td><td>{cid}</td><td>{src}</td>'
            f'<td>{flag_id}</td><td class="cat">{meta.get("category","")}</td>'
            f'<td class="desc">{meta.get("description","")}</td>{gt_cell}'
            f'<td class="desc">{(reasoning or "").replace("<", "&lt;")}</td></tr>'
        )

    gt_note = (
        "Rows are pre-marked confirmed/unconfirmed against known synthetic ground truth "
        "(green = the flag was genuinely injected; red = the detector fired but the flag "
        "wasn't actually present -- a real false positive worth investigating)."
        if has_ground_truth else
        "This dataset has no ground truth (real data) -- every row needs independent human "
        "judgment; nothing here is pre-verified."
    )

    html = HTML_TEMPLATE.format(
        n_candidates=len(rows), n_anomalies=len(anomaly_instances), n_flagged_candidates=len(flagged_candidates),
        gt_note=gt_note, gt_suffix=" (vs. ground truth)" if has_ground_truth else "",
        gt_cols=gt_cols, breakdown_rows="\n".join(breakdown_rows),
        gt_col=gt_col, anomaly_rows="\n".join(anomaly_rows),
    )
    html_path = out_dir / "anomaly_review.html"
    html_path.write_text(html)

    print(f"Wrote {csv_path}")
    print(f"Wrote {html_path}  (open directly in a browser)")
    print(f"\n{len(rows)} candidates scored, {len(flagged_candidates)} with at least one flag, "
          f"{len(anomaly_instances)} total flagged anomalies.")
    if has_ground_truth:
        total_confirmed = sum(c["confirmed"] for c in flag_counts.values())
        total_unconfirmed = sum(c["unconfirmed"] for c in flag_counts.values())
        print(f"Against ground truth: {total_confirmed} confirmed, {total_unconfirmed} unconfirmed (possible false positives).")


if __name__ == "__main__":
    main()
