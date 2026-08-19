# CV Fraud-Signal Detection — Synthetic Benchmark

A small pipeline for testing whether a Claude-based CV screening tool can pick up on
documented candidate-fraud patterns — extraction, red-flag scoring, cross-candidate
similarity, and evaluation against known ground truth.

Covers six categories, grounded in different sources (see below): identity impersonation
(DPRK IT-worker schemes), credential fraud (fabricated degrees/diploma mills), experience
fabrication (invented/overlapping employment, shell companies), reference fraud, AI-generated
boilerplate, and resume-mill/facilitator-ring template reuse across candidates (a
cross-candidate signal — see `similarity_check.py` — that per-CV scoring alone can't catch).

## Important scope note

**Every CV in `data/cvs/` is entirely synthetic and fictional.** None of it comes from real
job applicants. This repo exists to test pipeline *mechanics* — does the extraction schema
hold up, does the scorer find real textual evidence instead of hallucinating, does a score
threshold behave sensibly — not to make any validated claim about real-world fraud detection
accuracy.

**Do not point this at real, undisclosed job applicants.** Running CV-screening/fraud-scoring
tools on real candidates without disclosure raises real privacy-law issues (purpose
limitation under GDPR/CCPA-style regimes) and, if the analysis substantially influences a
hiring decision, may trigger automated-employment-decision-tool disclosure requirements
(e.g. NYC Local Law 144). If you want to use this against a real hiring pipeline, add
explicit applicant disclosure first.

The red-flag list in `redflags.py` is grounded in publicly documented cases and industry
research — DOJ indictments, FBI/CISA joint advisories, KnowBe4's own published incident
writeup about hiring a DPRK operative, and HireRight's 2025 Global Benchmark Report on
resume/background-check discrepancies (see sources at the bottom) — not guesswork. But
grounding the *patterns* in real cases doesn't make results from synthetic data a validated
fraud model; see "What this does and doesn't tell you" below.

## Pipeline

1. `generate_dataset.py` — generates labeled synthetic CVs via the Claude API. Fraud-labeled
   CVs have 2-4 red flags (from `redflags.py`) deliberately, subtly woven in; ground truth
   (which flags, which label) is stored alongside each CV.
2. `extract_cv.py` — Claude call that extracts structured fields (companies, tenure,
   education, references, etc.) from raw CV text.
3. `score_cv.py` / `score_all.py` — Claude call that judges, with evidence, which documented
   red flags are actually present, then computes a weighted 0-100 score.
4. `similarity_check.py` — pairwise text-similarity pass against every other CV already in
   the dataset, flagging near-duplicates (resume-mill/facilitator-ring template reuse). This
   is the one signal that per-CV scoring structurally cannot see.
5. `evaluate.py` — compares scores against ground truth: precision/recall/F1 at a threshold,
   plus per-flag recall.
6. `db.py` — SQLite storage (`data/db/cv_fraud.sqlite3`, gitignored — regenerate by running
   the pipeline).

## A known limitation: score dilution as categories grow

`fraud_score` is a single weighted sum normalized against `MAX_POSSIBLE_SCORE` (the sum of
every flag's weight). As more categories get added, that denominator grows, so a CV tripping
only one or two flags scores lower as a percentage even with the same absolute evidence —
in this project's own test run, two real fraud CVs (overlapping employment, shell company)
fell below a threshold that would have caught them before credential/reference/overemployment
categories were added. If you keep expanding the taxonomy, consider per-category sub-scores
instead of one blended global number.

## Evaluating against a real CV repository

See [`RUNBOOK_REAL_DATASET.md`](RUNBOOK_REAL_DATASET.md) for exact steps: ingesting real
PDF/DOCX CVs (`ingest_cvs.py`), scoring them (`score_real_dataset.py`), and generating a
ranked, human-reviewable report (`report.py`, CSV + self-contained HTML). Read the "before
running anything" section first — real data has no ground truth to validate against, and
disclosure/consent considerations apply that don't exist for the synthetic set.

## Offline path (no API key, scales to hundreds of candidates)

`generate_dataset.py`/`extract_cv.py`/`score_cv.py` need the Claude API. For tuning the
detection logic itself at scale, there's a parallel offline path with no API dependency:

- `local_generator.py` — template-based generator (name/company/institution pools +
  deliberate flag injection), not LLM-written. Renders CVs from structured records so ground
  truth is exact. Decorrelates weak signals (e.g. free email domain) from the fraud label so
  the detector can't shortcut on them, and clones a fraction of fraud CVs verbatim (with a
  swapped name) to simulate resume-mill/facilitator-ring template reuse.
- `rule_based_extract.py` / `rule_based_score.py` — regex-based extraction and deterministic
  flag-matching, tuned specifically to this generator's template format (does not generalize
  to arbitrary real resumes the way the Claude-based path does).
- `run_local_pipeline.py` — runs extraction + scoring + cross-candidate similarity over a
  generated batch and prints a full evaluate.py-style report.
- `anomaly_report.py` — the evaluation-review view: every candidate x flag pair as its own
  row, pre-marked confirmed/unconfirmed against ground truth, plus a per-flag-type breakdown
  (fire count, confirm rate) for spotting which specific heuristics need work. This is what
  actually caught the labeling bug described below — a raw precision/recall number wouldn't
  have surfaced it.

```bash
python3 local_generator.py --n 300 --fraud-rate 0.35 --seed 7 --out data/cvs_large
python3 run_local_pipeline.py --dir data/cvs_large --db data/db/cv_fraud_large.sqlite3 --threshold 13
python3 anomaly_report.py --db data/db/cv_fraud_large.sqlite3 --out data/reports/anomaly_review_large
```

### Tuning results (300 candidates: 105 fraud / 195 clean)

First run surfaced real generator bugs, not scorer bugs: `high_job_turnover` had 0% recall
because the generator anchored turnover jobs 6-12 years in the past regardless of the flag
(so "4+ jobs in the last 5 years" never matched anything); `thin_linkedin` had 50% recall
from a coin-flip that rendered a normal LinkedIn profile even when the flag was injected;
several other flags had partial misses because independently-sampled flags sometimes landed
in combinations that silently overwrote each other's rendering (e.g. `sparse_recent_history`
short-circuits company-building before an `employment_gaps_unexplained` gap can be inserted).
Fixed by clustering conflicting flags so at most one per cluster is sampled onto a candidate,
and anchoring turnover jobs recently. After the fix: **17 of 18 flag categories hit 100%
recall**, one hit 96%.

That still left a threshold-calibration problem: at the previous default (`threshold=25`,
carried over from the earlier hand-built demo set), recall was only 0.324 despite near-perfect
per-flag detection — the "score dilution" issue from the section below, worse at this scale
since most fraud CVs carry only 2-4 of the 18 possible flags. Sweeping thresholds against the
actual score distribution found **threshold=13: precision 1.000, recall 0.924, F1 0.960**,
now the default in `run_local_pipeline.py`. The 8 remaining false negatives at that threshold
all matched every injected flag correctly — they're genuinely weak cases (2 low-weight flags
only, e.g. `thin_linkedin` + `high_job_turnover`), which arguably should score low.

### Anomaly-review pass found two more real bugs that precision/recall alone missed

Running `anomaly_report.py` against this dataset (which pre-marks every matched flag
confirmed/unconfirmed against ground truth) surfaced two issues invisible in the aggregate
precision/recall numbers above, because their effect was symmetric or small enough not to
move candidate-level accuracy:

1. **Clone-pair ground truth was one-sided.** When the generator clones a fraud CV's template
   for a facilitator-ring simulation, only the clone's ground truth said
   `template_reuse_across_candidates` — the parent's didn't, even though a near-duplicate pair
   is symmetric and the detector correctly flagged both sides. Fixed by adding the flag to the
   parent's ground truth too. Separately, the clone was only swapping the name on line 1,
   leaving the email/LinkedIn/GitHub referencing the *parent's* old identity — unrealistic, and
   it coincidentally tripped `name_spelling_inconsistent` for the wrong reason. Fixed by
   regenerating the whole contact block on clone, keeping only the body (summary/experience/
   education/references — the actual "reused template") verbatim.
2. **`similarity_check.py`'s `SequenceMatcher.ratio()` is not symmetric** — verified empirically
   (one real clone pair scored 0.94 one comparison direction, 0.88 the other), meaning a fixed
   threshold could flag only one side of a real duplicate pair depending on comparison order.
   Fixed by taking the max of both directions.

Chasing the `template_reuse_across_candidates` threshold further at 300-candidate scale
surfaced a harder, structural limitation: **true clone-pair ratios and coincidental
unrelated-pair ratios genuinely overlap** on this dataset (true clones as low as 0.858 by
character-level similarity; a coincidental unrelated pair as high as 0.907, verified by
exhaustive pairwise check). Expanding the bullet-phrase vocabulary (15 → 240 combinations)
helped but didn't eliminate the overlap. No single `difflib`-ratio threshold separates them
perfectly — 0.88 is a pragmatic midpoint, not a clean separator. The methodologically correct
fix is semantic (embedding) similarity rather than literal character-sequence matching, which
is out of scope for this API-free offline path. Real CVs plausibly have enough natural lexical
diversity that this specific overlap is a synthetic-corpus artifact — but that's an assumption,
not something verified against real data.

Final state after all fixes (300 candidates, same seed): **precision 1.000, recall 0.810,
F1 0.895**, 15 of 16 flag categories at 100% per-flag recall (one at 95%). Recall moved around
across these fix iterations mostly because each generator fix reshuffled the shared random
sequence downstream, not because later fixes made things worse — the flag-level and
false-positive numbers are the more meaningful signal here than the exact recall figure.

This tuning is specific to this generator's flag-weight distribution and the mostly-uniform
CV template style it produces — it's a demonstration that the tuning loop (generate → score →
diagnose false negatives/positives → fix generator or scorer bugs → re-sweep threshold) works,
not a claim that 13 is the right cutoff for real-world CVs.

## Usage

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here

python3 generate_dataset.py --n 40 --fraud-rate 0.35 --seed 1
python3 score_all.py
python3 evaluate.py --threshold 30
```

To score a single CV: `python3 score_cv.py path/to/candidate.txt`

## What this does and doesn't tell you

- **Does tell you**: whether the extraction/scoring pipeline works mechanically — reliable
  field extraction, evidence-based (not hallucinated) flag matching, a threshold that
  produces a real precision/recall tradeoff.
- **Doesn't tell you**: whether these patterns catch real-world fraud, or what the real
  false-positive rate would be against genuinely varied real resumes. The synthetic fraud
  CVs were built by injecting the same flags the scorer checks for, which is close to
  circular by construction. A meaningful validity test needs either real documented fraud
  cases or a real, disclosed hiring pipeline — not more synthetic volume.

## Sources for the red-flag list

**Identity impersonation (DPRK IT-worker schemes)**
- [DOJ: Justice Department Announces Nationwide Actions to Combat Illicit North Korean Government Revenue Generation](https://www.justice.gov/opa/pr/justice-department-announces-nationwide-actions-combat-illicit-north-korean-government)
- [TechCrunch: Five people plead guilty to helping North Koreans infiltrate US companies as remote IT workers](https://techcrunch.com/2025/11/14/five-people-plead-guilty-to-helping-north-koreans-infiltrate-us-companies-as-remote-it-workers/)
- [SecurityWeek: KnowBe4 Hires Fake North Korean IT Worker](https://www.securityweek.com/knowbe4-hires-fake-north-korean-it-worker-catches-new-employee-planting-malware/)
- [KnowBe4: North Korean IT Worker Threat — 10 Critical Updates to Your Hiring Process](https://blog.knowbe4.com/north-korean-it-worker-threat-10-critical-updates-to-your-hiring-process)
- [DeepStrike: Nation-State Impostors — North Korea's Fake Remote IT Workers](https://deepstrike.io/blog/north-korea-fake-remote-it-workers)
- [FBI: North Korean IT Worker Threats to U.S. Businesses](https://www.fbi.gov/investigate/cyber/alerts/2025/north-korean-it-worker-threats-to-u-s-businesses)

**Credential fraud, reference fraud, general resume discrepancies**
- [HireRight: Identity Fraud and Candidate Discrepancies Remain Key Concerns for Employers — 2025 Global Benchmark Report](https://www.hireright.com/company/newsroom/identity-fraud-and-candidate-discrepancies-remain-key-concerns-for-employers)
- [SHRM: Checking Resumes for Fraud](https://www.shrm.org/topics-tools/news/employee-relations/checking-resumes-fraud)

**Overemployment / concealed concurrent roles**
- FTC: job-scam and hiring-fraud losses exceeded $501M in 2024, up from $90M in 2020 (via industry reporting on remote-hiring candidate fraud)

## License

MIT — see `LICENSE`.
