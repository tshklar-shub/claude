"""
Generate a ranked, human-reviewable report from a scored dataset (real or
synthetic). Unlike evaluate.py, this doesn't assume ground truth exists --
it just ranks candidates by fraud_score and shows the evidence, for a human
to actually look at.

Usage:
    python3 report.py --db data/db/cv_fraud_real.sqlite3 --out data/reports/real_run
"""

import argparse
import csv
import json
from pathlib import Path

import db

RISK_BANDS = [(0, 10, "low"), (10, 20, "medium"), (20, 1000, "high")]


def risk_band(score):
    for lo, hi, label in RISK_BANDS:
        if lo <= score < hi:
            return label
    return "high"


HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>CV Fraud-Signal Report</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #1a1a1a; background: #fff; }}
  h1 {{ font-size: 1.4rem; }}
  .caveat {{ background: #fff3cd; border: 1px solid #ffe69c; padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1.5rem; font-size: 0.9rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f5f5f5; position: sticky; top: 0; }}
  tr.high {{ background: #fde2e1; }}
  tr.medium {{ background: #fff6db; }}
  tr.low {{ background: #f0f9f0; }}
  .flags {{ font-size: 0.78rem; color: #444; }}
  .reasoning {{ font-size: 0.78rem; color: #555; max-width: 340px; }}
  .summary {{ margin-bottom: 1rem; font-size: 0.95rem; }}
</style></head>
<body>
<h1>CV Fraud-Signal Report</h1>
<div class="caveat">
  <strong>Read before acting on this:</strong> scores are heuristic signals from an
  automated screen, not a fraud determination. The scoring weights were calibrated
  against a synthetic benchmark, not this dataset -- treat "high" as "review first,"
  not "reject." Any hiring decision meaningfully influenced by this tool should be
  disclosed to candidates per applicable law (e.g. NYC Local Law 144 and similar
  automated-employment-decision-tool rules), and false positives are expected.
</div>
<div class="summary">{n} candidates scored &middot; {n_high} high &middot; {n_medium} medium &middot; {n_low} low</div>
<table>
<tr><th>Rank</th><th>Score</th><th>Risk</th><th>Source file</th><th>Matched flags</th><th>Reasoning</th></tr>
{rows}
</table>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, required=True)
    ap.add_argument("--out", type=str, default="data/reports/run")
    args = ap.parse_args()

    conn = db.connect(Path(__file__).parent / args.db)
    rows = conn.execute(
        """
        SELECT c.id, c.source_file, s.fraud_score, s.matched_flags, s.reasoning
        FROM candidates c LEFT JOIN scores s ON s.candidate_id = c.id
        WHERE s.fraud_score IS NOT NULL
        ORDER BY s.fraud_score DESC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No scored candidates found in {args.db}. Run score_real_dataset.py first.")
        return

    out_dir = Path(__file__).parent / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "report.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "candidate_id", "source_file", "fraud_score", "risk_band", "matched_flags", "reasoning"])
        for i, (cid, src, score, flags_json, reasoning) in enumerate(rows, 1):
            flags = json.loads(flags_json or "[]")
            w.writerow([i, cid, src, score, risk_band(score), "; ".join(flags), reasoning or ""])

    band_counts = {"high": 0, "medium": 0, "low": 0}
    html_rows = []
    for i, (cid, src, score, flags_json, reasoning) in enumerate(rows, 1):
        flags = json.loads(flags_json or "[]")
        band = risk_band(score)
        band_counts[band] += 1
        html_rows.append(
            f'<tr class="{band}"><td>{i}</td><td>{score}</td><td>{band}</td><td>{src}</td>'
            f'<td class="flags">{", ".join(flags) or "&mdash;"}</td>'
            f'<td class="reasoning">{(reasoning or "").replace("<", "&lt;")}</td></tr>'
        )

    html = HTML_TEMPLATE.format(
        n=len(rows), n_high=band_counts["high"], n_medium=band_counts["medium"], n_low=band_counts["low"],
        rows="\n".join(html_rows),
    )
    html_path = out_dir / "report.html"
    html_path.write_text(html)

    print(f"Wrote {csv_path}")
    print(f"Wrote {html_path}  (open directly in a browser)")
    print(f"\n{len(rows)} candidates: {band_counts['high']} high, {band_counts['medium']} medium, {band_counts['low']} low risk")


if __name__ == "__main__":
    main()
