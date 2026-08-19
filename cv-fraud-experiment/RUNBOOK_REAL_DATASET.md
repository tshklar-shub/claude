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
assume silence means it's fine. This check is required every time this runbook is followed,
not just the first time a given person uses it.

## 1. Set up (one-time)

```bash
cd cv-fraud-experiment
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

## 2. Run the whole pipeline with one command

`scan_repository.py` chains ingestion, scoring, and both reports so nothing gets skipped or
mismatched:

```bash
python3 scan_repository.py --src /path/to/the/real/cv/folder --label <short-name> \
    --i-have-confirmed-disclosure
```

- `--i-have-confirmed-disclosure` is required and the command refuses to run without it — that
  flag exists to force step 0's conversation to actually happen, not to be added reflexively.
  If you're an agent running this on someone's behalf, only add it after you've actually asked
  the questions in step 0 in chat and gotten a real answer.
- `<short-name>` labels this batch (e.g. `q1_applicants`) and namespaces the output under
  `data/runs/<short-name>/`, so repeat scans don't overwrite each other.
- Add `--dry-run` on a large folder to verify file discovery and DB wiring with zero API calls
  before spending budget on the real run, then re-run without it.

Read the ingest step's output carefully (printed as step 1/4). Anything skipped will say why
— the most common cause is a scanned/image-only PDF with no extractable text layer, which
needs OCR first (out of scope for this tool). Report those back to whoever asked for this scan
rather than silently treating the run as complete.

The command prints exactly where the two output reports landed when it finishes.

## 3. How to show the results to the person who asked for this

Two reports come out of every scan, both under `data/runs/<short-name>/`:

- **`report/report.html`** (+ `.csv`) — ranked triage view: every candidate, sorted by score,
  color-coded by risk band. This is "who to look at first," not a verdict.
- **`anomaly_review/anomaly_review.html`** (+ `.csv`) — the actual review view: one row per
  individual flagged anomaly with its plain-language description and evidence, for working
  through candidates one by one. The CSV has a blank `reviewer_verdict`/`reviewer_notes`
  column for recording the human review — real data has no ground truth, so nothing here is
  pre-verified, unlike a synthetic run.

Hand-off guidance:
- Both are self-contained HTML/CSV — no server needed, open directly in a browser.
- **If your Claude environment has an artifact/publish tool available** (e.g. Claude.ai's
  Artifact feature), you can additionally render either report there for a shareable link —
  but treat this as a convenience layer, not a replacement for the caveat in the report
  header. Do not strip that caveat out when re-rendering elsewhere.
- **Lead with the caveat, not the ranking**, every time you hand these off: these are
  heuristic screening signals from a tool calibrated on synthetic data, not a fraud
  determination. "High" means "look at this one first," not "this person is committing
  fraud." Every score needs a human to actually read the CV and the reasoning before anyone
  acts on it.
- If asked for a single number ("how many are fraud?"), don't give one — there is no validated
  threshold for real data (the threshold=13 default from the synthetic benchmark is not
  proven to transfer). Report the score distribution and let the human set their own review
  cutoff based on how many candidates they have capacity to manually review.

## Advanced: running individual stages

`scan_repository.py` is a thin wrapper around four independently-runnable scripts, useful if
you need to re-run just one stage (e.g. re-generate reports after manually editing the DB):

```bash
python3 ingest_cvs.py --src /path/to/cvs --out data/real_cvs_txt
python3 score_real_dataset.py --dir data/real_cvs_txt --db data/db/cv_fraud_real.sqlite3
python3 report.py --db data/db/cv_fraud_real.sqlite3 --out data/reports/real_run
python3 anomaly_report.py --db data/db/cv_fraud_real.sqlite3 --out data/reports/anomaly_review
```

For normal use, prefer `scan_repository.py` — chaining these by hand is exactly how a step
gets skipped or an argument gets mismatched.
