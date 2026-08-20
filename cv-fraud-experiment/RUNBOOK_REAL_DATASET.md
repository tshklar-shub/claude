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

This runs entirely locally — extraction/scoring uses a local model via
[Ollama](https://ollama.com), not the Anthropic API, so real candidate CV text never leaves
this machine. No API key, no billing account.

```bash
cd cv-fraud-experiment
pip install -r requirements.txt

# install Ollama (macOS: brew install ollama, or download from ollama.com), then:
ollama serve &                 # or use the Ollama desktop app instead
ollama pull qwen3:4b   # one-time download, a few GB
```

`qwen3:4b` is the default. Verified (not assumed) to match `qwen3:8b`'s accuracy on the
ground-truth batch (16/16 either way) and produce identical structured extraction on a real
resume, while running ~1.6x faster — worth it specifically because `hybrid_score.py` moved
scoring out of the model's job, leaving only the more mechanical extraction step. Set
`export CV_FRAUD_LOCAL_MODEL=<other-model>` to use a different one.

**Speed**: real resumes average ~700 words (vs ~100 for this project's synthetic test set) --
budget roughly 1-3 min/candidate depending on hardware, not the much faster numbers a
synthetic-CV benchmark would suggest. For a large batch (hundreds of real CVs), find the right
`OLLAMA_NUM_PARALLEL` setting for the machine actually running this:

```bash
python3 tune_parallelism.py --model qwen3:4b --levels 1,2,3,4,6,8
```

This restarts Ollama at each level, fires that many concurrent extraction requests against a
realistic-length CV, and measures actual throughput -- then recommends the level with the best
verified result. Don't guess a parallelism setting from a one-off timing test: an early ad-hoc
test on this project's own dev machine suggested a real gain from parallelism, but a rigorous
sweep on the same machine got wildly inconsistent numbers between runs, traced to a mix of a
real bug (`ollama serve`'s child process surviving a naive kill and competing with the next run
for GPU memory -- fixed in this script) and ordinary background load (browser, other apps) on a
machine that isn't dedicated to this. Run the tuning script with as little else competing for
the GPU as possible, and treat its output as specific to that machine and that model -- re-run
if either changes.

The cloud API would be faster still, but reintroduces exactly the privacy tradeoff this
local-only setup exists to avoid -- not a default to reach for without an explicit decision to
accept that tradeoff.

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
- Add `--dry-run` on a large folder to verify file discovery and DB wiring with zero model
  calls before running the real scan (which, being local, has no billing cost — but local
  inference is slower than a cloud API, so this still saves time on a bad folder path).

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
- One more caveat specific to the local-model path, verified by actually running it against
  real API calls (not just theorized): a genuinely clean test CV came back with 5 matched
  flags at `qwen3:8b`, all citing real quoted text (the schema-constrained evidence-quote
  requirement works -- nothing was fabricated), but several of those quotes didn't actually
  support the flag they were attached to (e.g. `thin_linkedin` citing the LinkedIn URL as
  evidence it was *thin*, when its mere presence doesn't establish that; a 1-month gap
  between two roles called "unexplained"; a reference line naming a company phone line
  called "unverifiable"). The failure mode isn't hallucinated evidence anymore -- it's
  misjudging evidence that's actually there. That's a real, current gap versus the cloud-API
  path's behavior. Read the `reasoning`/evidence-quote text on every flagged candidate before
  trusting it, especially on borderline scores.

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
