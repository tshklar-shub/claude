# Runbook: evaluating this tool against a real CV repository

Instructions for a Claude Code session (or a person) to follow, step by step, to run this
pipeline against an existing, real folder of CVs instead of the synthetic benchmark.

## 0. Before running anything — check this first

This tool was built and tuned entirely on synthetic, fictional data (see `README.md`,
"What this does and doesn't tell you"). Before pointing it at real people's CVs, confirm with
whoever owns this data:

1. **Where did these CVs come from, and were candidates told they'd be screened this way?**
   If they were collected through a real hiring process without disclosure that automated
   fraud/consistency screening would be applied, stop and flag this to the user rather than
   proceeding — this can trigger disclosure obligations under laws like NYC Local Law 144 and
   similar automated-employment-decision-tool rules, and raises purpose-limitation issues
   under GDPR/CCPA-style privacy law if the CVs were collected for a different stated purpose.
2. **What will a "high" score be used for?** This tool has never been validated against
   confirmed real fraud cases (see README). A score is a prioritization signal for human
   review, never a basis for auto-rejecting a candidate.

If the answers check out, continue below. If unsure, ask the user before proceeding — don't
assume silence means it's fine.

## 1. Set up

```bash
cd cv-fraud-experiment
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

## 2. Normalize the real CVs to plain text

Real CVs will be PDFs, DOCX, or occasionally plain text. `ingest_cvs.py` converts whatever's
in the source folder into normalized `.txt` files the rest of the pipeline expects:

```bash
python3 ingest_cvs.py --src /path/to/the/real/cv/folder --out data/real_cvs_txt
```

Read its output carefully. Anything it skips will say why — the most common cause is a
scanned/image-only PDF with no extractable text layer, which needs OCR first (out of scope
for this tool; flag those files back to the user rather than silently dropping them from the
analysis).

## 3. Score every CV

This calls the Claude API once per CV for extraction, once for red-flag judgment, plus a
local cross-candidate similarity pass (useful on real data too — it's what would catch a
resume-mill/facilitator ring reusing one template across multiple applicants):

```bash
python3 score_real_dataset.py --dir data/real_cvs_txt --db data/db/cv_fraud_real.sqlite3
```

For a large folder, sanity-check the wiring first with `--dry-run` (no API calls, just
confirms every file is discovered and registered) before spending API budget on the real run.

## 4. Generate the report

```bash
python3 report.py --db data/db/cv_fraud_real.sqlite3 --out data/reports/real_run
```

This writes two files:
- `data/reports/real_run/report.csv` — every candidate, ranked by score, for spreadsheet review
- `data/reports/real_run/report.html` — the same data as a self-contained, color-coded page —
  open it directly in any browser (`open data/reports/real_run/report.html` on macOS)

`report.py` is for triage (which candidates need a closer look). For the actual review —
going through every individual anomaly with its evidence — generate the anomaly review
report instead:

```bash
python3 anomaly_report.py --db data/db/cv_fraud_real.sqlite3 --out data/reports/anomaly_review
```

This writes one row per candidate-x-flag pair (a candidate with 3 matched flags gets 3 rows),
each with the flag's plain-language description and the model's reasoning, plus a blank
`reviewer_verdict`/`reviewer_notes` column in the CSV for recording the human review. Real
data has no ground truth, so nothing is pre-marked correct/incorrect — every row needs actual
judgment. (Run the same script against a synthetic run, e.g.
`data/db/cv_fraud_large.sqlite3`, and it *will* pre-mark each flag confirmed/unconfirmed
against known ground truth plus a per-flag-type breakdown table — that's the view for
evaluating the detector itself, not for reviewing real candidates.)

## 5. How to show the results to the person who asked for this

- **Default**: hand them `report.html` directly, or `report.csv` if they want to pivot/filter
  in a spreadsheet. Both are self-contained — no server or extra setup needed.
- **If your Claude environment has an artifact/publish tool available** (e.g. Claude.ai's
  Artifact feature), you can additionally render `report.html`'s content there for a
  shareable link — but treat this as a convenience layer, not a replacement for the caveat in
  the report header. Do not strip that caveat out when re-rendering elsewhere.
- **Lead with the caveat, not the ranking.** The report header already says this, but say it
  again out loud when handing off results: these are heuristic screening signals from a tool
  calibrated on synthetic data, not a fraud determination. "High" means "look at this one
  first," not "this person is committing fraud." Every score needs a human to actually read
  the CV and the `matched_flags`/`reasoning` columns before anyone acts on it.
- If asked for a single number ("how many are fraud?"), don't give one — there is no validated
  threshold for real data (the threshold=13 default from the synthetic benchmark is not
  proven to transfer). Report the score distribution and let the human set their own review
  cutoff based on how many candidates they have capacity to manually review.
