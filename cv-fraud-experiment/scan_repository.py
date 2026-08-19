"""
One-command entry point: point this at a folder of real CVs and it runs the
whole pipeline (ingest -> score -> both reports) and prints where to find
the results. This exists so a Claude session can run one command instead of
correctly chaining ingest_cvs.py -> score_real_dataset.py -> report.py ->
anomaly_report.py by hand.

Usage:
    export ANTHROPIC_API_KEY=...
    python3 scan_repository.py --src /path/to/cv/folder --label q1_batch --i-have-confirmed-disclosure

Deliberately requires --i-have-confirmed-disclosure and does nothing without
it. This is not a formality -- see the printed message and
RUNBOOK_REAL_DATASET.md section 0. A Claude session running this on someone
else's behalf should have actually asked that question and gotten an answer
before adding the flag, not add it reflexively to make the command run.
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

DISCLOSURE_REMINDER = """
Refusing to run without --i-have-confirmed-disclosure.

Before scanning real people's CVs for fraud signals, confirm with whoever owns this data:

  1. Where did these CVs come from, and were candidates told they'd be screened this way?
     If collected through a real hiring process without disclosure that automated
     fraud/consistency screening would be applied, STOP and flag this to the user instead
     of proceeding -- this can trigger disclosure obligations under laws like NYC Local Law
     144 and similar automated-employment-decision-tool rules, and raises purpose-limitation
     issues under GDPR/CCPA-style privacy law if the CVs were collected for a different
     stated purpose.
  2. What will a "high" score be used for? This tool has never been validated against
     confirmed real fraud cases. A score is a prioritization signal for human review, never
     a basis for auto-rejecting a candidate.

If you are a Claude session running this on someone's behalf: ask them these questions in
chat and wait for a real answer before re-running with the flag. Do not add the flag
yourself just to make the command succeed -- see RUNBOOK_REAL_DATASET.md, section 0.
"""


def run(cmd, label):
    print(f"\n=== {label} ===", flush=True)
    result = subprocess.run([sys.executable] + cmd, cwd=HERE)
    if result.returncode != 0:
        print(f"\n[scan_repository] '{label}' failed (exit {result.returncode}). Stopping.")
        sys.exit(result.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=str, required=True, help="folder containing the real CVs")
    ap.add_argument("--label", type=str, default="run", help="short name for this scan, used to namespace output")
    ap.add_argument("--dry-run", action="store_true", help="skip API calls, just verify ingestion + wiring")
    ap.add_argument("--i-have-confirmed-disclosure", action="store_true",
                     help="required -- see the printed message if omitted")
    args = ap.parse_args()

    if not args.i_have_confirmed_disclosure:
        print(DISCLOSURE_REMINDER)
        sys.exit(1)

    run_dir = HERE / "data" / "runs" / args.label
    txt_dir = run_dir / "real_cvs_txt"
    db_path = run_dir / "cv_fraud.sqlite3"
    report_dir = run_dir / "report"
    anomaly_dir = run_dir / "anomaly_review"

    run(["ingest_cvs.py", "--src", args.src, "--out", str(txt_dir.relative_to(HERE))], "1/4 Ingest")

    score_cmd = ["score_real_dataset.py", "--dir", str(txt_dir.relative_to(HERE)), "--db", str(db_path.relative_to(HERE))]
    if args.dry_run:
        score_cmd.append("--dry-run")
    run(score_cmd, "2/4 Score" + (" (dry run, no API calls)" if args.dry_run else ""))

    if args.dry_run:
        print(f"\n[scan_repository] Dry run complete. Ingestion and wiring verified for '{args.label}'. "
              f"Re-run without --dry-run to actually score against the API.")
        return

    run(["report.py", "--db", str(db_path.relative_to(HERE)), "--out", str(report_dir.relative_to(HERE))],
        "3/4 Triage report")
    run(["anomaly_report.py", "--db", str(db_path.relative_to(HERE)), "--out", str(anomaly_dir.relative_to(HERE))],
        "4/4 Anomaly review report")

    print(f"""
=== Done: '{args.label}' ===
Triage report (rank candidates, decide who to look at first):
  {report_dir / 'report.html'}
  {report_dir / 'report.csv'}

Anomaly review (every flagged anomaly with evidence, for actual review):
  {anomaly_dir / 'anomaly_review.html'}
  {anomaly_dir / 'anomaly_review.csv'}

Hand off report.html first for the overview, anomaly_review.html/csv for the actual review
work. Lead with the caveat in both reports' headers: heuristic screening signals for human
review, not a fraud determination.
""")


if __name__ == "__main__":
    main()
