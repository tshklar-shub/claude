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
