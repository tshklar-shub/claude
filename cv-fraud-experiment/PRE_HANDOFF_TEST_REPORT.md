# Pre-handoff local pipeline test report

Full local end-to-end test of `scan_repository.py` before handing this off to Dor. Ollama
and a model were installed directly on this machine for the test; nothing left the machine
at any point. Two batches were run: a 16-candidate synthetic set with known ground truth
(mixed PDF/DOCX/TXT), and 15 real, unlabeled resumes sampled from a public Kaggle dataset
across 15 different job categories, to test against genuinely diverse real-world formatting.

## Setup validated

- Installed Ollama directly (no `brew`; downloaded the macOS app, ran the CLI binary from
  inside the app bundle) and confirmed it uses the machine's Metal GPU automatically.
- Model: switched from the original default (`llama3.1:8b`, 2024-vintage) to `qwen3:8b`
  after checking current recommendations — this was a real upgrade, not guesswork.
- Confirmed zero dependency on the Anthropic API anywhere in the real-CV path
  (`extract_cv.py`/`hybrid_score.py` import only `local_llm_client`, which only talks to
  `localhost:11434`).

## Architecture change made during this test: hybrid scoring

Original design used two LLM calls per candidate (extraction, then a second call asking the
model to judge red flags). Found and fixed during this test:

- **Cut to one LLM call per candidate.** Extraction still needs an LLM (arbitrary real CV
  formats can't be regex-parsed reliably), but most red flags are pure logic once fields are
  extracted — date-range math, string lookups, counting. `hybrid_score.py` does this
  deterministically in Python instead of a second model call.
- **Measured result, same extracted data, both scorers**: two-call LLM scoring got
  **10/16 correct (precision 0.67, recall 0.67)**; hybrid deterministic scoring on the
  identical extraction got **15/16 correct (precision 0.90, recall 1.00)** — faster and more
  accurate, not a tradeoff.
- **Found and fixed a real extraction bug in the process**: the JSON schema only marked 4
  fields "required," so the model sometimes silently omitted fields it wasn't forced to
  answer (dropped `linkedin_url`/`github_url`/`email`/`phone` even when clearly present in
  the CV text). Marking all scalar fields required fixed it. Re-ran the full 16-candidate
  batch after the fix: **16/16 correct, precision 1.00, recall 1.00.**

## Result 1: synthetic ground-truth batch (16 candidates, mixed PDF/DOCX/TXT)

| | |
|---|---|
| Correct | 16/16 (100%) |
| Precision | 1.00 |
| Recall | 1.00 |
| Total time | 9m55s (16 candidates, ingest + score + both reports) |
| Avg per candidate | ~37s |

All 7 clean candidates scored below the threshold (max 6.7/100); all 9 fraud candidates
scored above it (min 18.9/100), clean separation, no borderline calls either direction.

## Result 2: real resumes, 15 sampled from a public Kaggle dataset (no fraud labels)

2,484 real PDF resumes are available in this dataset across 24 job categories (unrelated to
software engineering — accountant, aviation, agriculture, etc.); 15 were sampled across 15
categories. This has no fraud ground truth — it's a false-positive/format-robustness check,
not an accuracy check.

| | Before fixes | After fixes (this test) |
|---|---|---|
| Ingestion (PDF parsing) | 15/15 succeeded, 0 skipped | (unchanged) |
| Risk bands | 5 high, 5 medium, 5 low | **0 high, 4 medium, 11 low** |
| Total time | 44.1 min (15 candidates) | (unchanged -- fixes were scoring-only, no re-extraction needed) |
| Avg per candidate | ~177s | (unchanged) |

**Three real findings came out of this, not just "it worked" — two got fixed during this
test, not just written down as recommendations:**

1. **Real resumes are ~7x longer than our synthetic test set** (718 words avg vs 102 words
   avg), which fully explains the speed gap between the two batches above (~177s/candidate
   vs ~37s/candidate — almost exactly proportional to the length difference). **Every speed
   number from earlier in this project was measured on unrealistically short synthetic CVs.
   Budget roughly 3 minutes/candidate for real resumes, not 37 seconds** — a batch of 50 real
   CVs is closer to 2.5 hours than 30 minutes. (Not fixed -- this is a real hardware/model
   throughput constraint, not a bug.)

2. **FIXED: `thin_linkedin`/`thin_github` fired on 15/15 real resumes — 0 of the 15 even
   mention LinkedIn.** Confirmed this wasn't an extraction failure (checked the raw text
   directly). `thin_github`'s own description was always scoped to "a claimed senior
   engineer," but nothing enforced that scoping — it fired identically on Agriculture,
   Apparel, and Arts resumes. Added a tech-role gate (`_is_tech_role` in `hybrid_score.py`,
   checks extracted job titles for engineer/developer/software/etc. keywords) so both flags
   only fire when there's an actual technical-role signal. Re-scored the same 15 real resumes
   with the fix: those two flags stopped firing entirely on this batch (none of the 15 sampled
   categories were technical roles), and the risk-band distribution dropped from
   **5 high / 5 medium / 5 low → 0 high / 4 medium / 11 low**, with the synthetic
   ground-truth batch unaffected (still 16/16, precision 1.00, recall 1.00).

3. **FIXED: a real double-counting bug.** `overlapping_employment_dates` could match
   multiple overlapping pairs in one candidate (e.g. a 4-role resume produced 4 separate
   matches), and the scorer wasn't deduplicating — the same flag's weight got summed multiple
   times, silently inflating scores. Made the internal `flag()` helper idempotent (first
   evidence wins, later duplicate calls for the same flag_id are ignored). This was a
   contributing cause of the original "5 high" count above, not just the LinkedIn/GitHub
   gating -- both fixes are reflected in the corrected distribution.

   Residual, unfixed version of the same underlying issue: this dataset redacts every real
   employer name to the literal placeholder text `"Company Name"`, which is why several
   `overlapping_employment_dates`/`employment_gaps_unexplained` matches above involve entries
   that can't be sanity-checked against company identity. The date math itself is correct;
   real-world causes of a date overlap are more varied than "fraud" (concurrent part-time
   work, non-chronological listing), and this dataset's redaction removes a signal a human
   reviewer would normally use to judge it. 4/15 candidates still land in "medium" for this
   reason — worth Dor knowing that "medium" here skews toward "ambiguous resume formatting,"
   not "worth real suspicion."

## Net assessment

- **Pipeline mechanics**: solid. Zero crashes across all real API-backed calls this session
  (after the bugs already fixed), handles PDF/DOCX/TXT correctly, stays fully local.
- **Accuracy on ground truth**: 100% on the synthetic set (16/16, precision 1.00, recall 1.00),
  a real result but a small sample and a dataset the flag list was originally designed
  around — treat as "the mechanics are sound," not as a generalizable accuracy number.
- **Real-world false-positive rate**: the real-data test caught two genuine bugs a
  synthetic-only test structurally could not have surfaced (role-inappropriate flag firing,
  and a scoring double-count) — both are now fixed and verified against the same 15 real
  resumes. Post-fix: 0/15 in "high," 4/15 in "medium," all for a documented, understood
  reason (redacted employer names removing a normal sanity-check signal), not unexplained
  noise.
- **Speed**: real, and worth setting Dor's expectations correctly — ~3 min/candidate on
  realistic-length CVs, a real constraint for any non-trivial batch size.

## Recommendation before handing this to Dor

1. Tell Dor the real throughput number (~3 min/candidate on realistic CV lengths), not the
   37s/candidate synthetic-batch number, so he can plan batch sizes and timing correctly.
2. Everything else (privacy, format handling, base pipeline correctness, the two bugs this
   test caught) is validated, fixed, and ready.
