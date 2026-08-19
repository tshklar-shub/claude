# cv-fraud-experiment

CV fraud-signal detection: extraction + red-flag scoring + cross-candidate similarity,
against either a synthetic benchmark or a real CV repository. Full background in `README.md`.

## If asked to scan a folder of real CVs for fraud signals

Someone will likely just say something like "scan this folder of CVs" or hand you a path.
Do this:

1. **Read `RUNBOOK_REAL_DATASET.md` section 0 first, every time — not just the first time.**
   Ask the user (in chat) whether the CVs were collected with disclosure that this kind of
   automated screening would be applied, and what a "high" score will be used for. Wait for
   an actual answer. Do not skip this because it feels like friction, do not infer an answer
   from context, and do not add `--i-have-confirmed-disclosure` to satisfy the tool without
   having actually asked and gotten a real response — the flag exists specifically to force
   this conversation to happen, not to be routed around.

2. **Run the whole pipeline with one command**, not by chaining the individual scripts by
   hand (that's how arguments get mismatched or a step gets skipped). This runs entirely
   locally via Ollama — no API key, no candidate data leaves the machine:

   ```bash
   ollama serve &                    # if not already running (or use the Ollama desktop app)
   ollama pull llama3.1:8b           # one-time, if not already pulled
   python3 scan_repository.py --src /path/to/the/cv/folder --label <short-name> \
       --i-have-confirmed-disclosure
   ```

   If `ollama` isn't installed at all, tell the user to install it from ollama.com first —
   don't fall back to `claude_client.py`/the Anthropic API for this path. `extract_cv.py` and
   `score_cv.py` are wired to `local_llm_client.py` specifically so real candidate data can't
   accidentally go to a third-party API; don't change that wiring to work around a missing
   Ollama install.

   Pick `<short-name>` to describe this batch (e.g. `q1_applicants`) — it namespaces the
   output under `data/runs/<label>/` so repeat scans don't clobber each other.

   For a large folder, or just to sanity-check first, add `--dry-run` (verifies file discovery
   and DB wiring, no model calls) and confirm it looks right before re-running without it.

3. **Read `ingest_cvs.py`'s output carefully** (`scan_repository.py` prints it as step 1/4).
   Anything skipped will say why — most commonly a scanned/image-only PDF with no text layer.
   Report those back to the user rather than silently treating the run as complete.

4. **Hand off both reports, not just one:**
   - `data/runs/<label>/report/report.html` — ranked triage view, "who to look at first"
   - `data/runs/<label>/anomaly_review/anomaly_review.html` — every individual flagged
     anomaly with evidence, for actually reviewing candidates one by one

   Lead with the caveat baked into both report headers when you hand them off: these are
   heuristic screening signals for human review, not a fraud determination. Don't give a
   single "X candidates are fraud" number — there's no validated threshold for real data.

## If asked to evaluate/improve the detector itself (not scan real data)

That's the synthetic path — `local_generator.py` → `run_local_pipeline.py` →
`anomaly_report.py` against `data/db/cv_fraud_large.sqlite3` (or generate a fresh batch).
See the "Offline path" and "Anomaly-review pass" sections of `README.md` for how prior
tuning rounds went and what's already been fixed — don't re-discover the same bugs.

## Don't

- Don't run `scan_repository.py` without the disclosure conversation happening first.
- Don't treat a "high" risk_band as a conclusion — every report says why not, say it again
  when handing off results.
- Don't reuse the rule-based path (`rule_based_extract.py`/`rule_based_score.py`) on real
  CVs — it's regex-tuned to `local_generator.py`'s synthetic template and will not parse
  arbitrary real resume formats. Real data always goes through `scan_repository.py`
  (local-model extraction via Ollama).
- Don't route real-CV extraction/scoring through `claude_client.py`/the Anthropic API. That's
  fine for `generate_dataset.py` (fictional synthetic CVs, no privacy concern) but not for
  anything touching real candidate data — that's the whole reason
  `extract_cv.py`/`score_cv.py` use `local_llm_client.py` instead.
