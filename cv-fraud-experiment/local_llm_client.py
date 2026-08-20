"""
Local-LLM client via Ollama, for the real-CV path where candidate data must
not leave the machine it's running on. Same interface as claude_client.py
(complete_text/complete_json) so extract_cv.py/score_cv.py don't need to
know which backend they're talking to -- only the transport differs.

Requires Ollama installed and running locally (https://ollama.com), plus a
model pulled ahead of time:
    ollama pull qwen3:4b        # or whatever CV_FRAUD_LOCAL_MODEL is set to

Model choice matters more than it might seem: an initial test run against llama3.1:8b
(2024-vintage) produced factually wrong reasoning (claiming two employment date ranges
overlapped when they didn't, independently, twice) and missed explicit quoted-in-the-CV
evidence. qwen3:8b fixed that. Once hybrid_score.py moved scoring out of the LLM's job
entirely (extraction only now, see hybrid_score.py's docstring), the remaining job is more
mechanical, and qwen3:4b was verified to match qwen3:8b's accuracy exactly on the same
ground-truth batch (16/16 correct either way) and produce identical structured extraction
on a real resume (companies/dates/titles/education all matched), while running ~1.6x faster
(measured on M1/16GB: 40.3s vs 63.4s on a real ~700-word resume). Switched the default to
qwen3:4b on that basis. Re-verify this holds if picking this back up much later -- models
move fast, and this was one real resume's worth of comparison, not an exhaustive one.

Parallel requests (OLLAMA_NUM_PARALLEL): use tune_parallelism.py to find the right setting
for the machine actually running this -- don't assume one. On this M1/16GB with qwen3:4b, the
clean, reproducible answer (after fixing two real bugs along the way -- see
tune_parallelism.py's history) is NUM_PARALLEL=1: level=1 measured 14.8s/candidate, level=2
measured 30.4s effective/candidate -- concurrency made it worse, not better, because this
combination of model size and GPU is already at capacity with one request in flight. A
stronger GPU (e.g. Dor's 2024 MacBook Pro) may get a genuinely different answer; that's the
point of the tuning script existing rather than hardcoding a number here.

Nothing here makes any network call outside localhost. If that's ever not
true, that's a bug -- the whole point of this module is that it isn't
claude_client.py.
"""

import json
import os
import urllib.error
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("CV_FRAUD_LOCAL_MODEL", "qwen3:4b")

REQUEST_TIMEOUT_SECONDS = 600  # measured ~10 tok/s on M1/16GB for qwen3:8b -- a full
                                # max_tokens=4000 budget can take ~7 minutes; 300s wasn't enough


def _post(path: str, payload: dict) -> dict:
    url = f"{OLLAMA_HOST}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Couldn't reach Ollama at {OLLAMA_HOST} ({e}). Is it installed and running? "
            f"Start it with `ollama serve` (or the Ollama desktop app), and make sure the "
            f"model is pulled: `ollama pull {MODEL}`."
        ) from e


def complete_text(system: str, user: str, max_tokens: int = 4000, format: dict = None) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": False,  # hybrid-reasoning models (e.g. qwen3) default to extended
                          # thinking, burning most of max_tokens on hidden reasoning
                          # before ever reaching the schema-constrained answer -- not
                          # needed here, we want the direct constrained JSON output.
        "options": {"num_predict": max_tokens},
    }
    if format is not None:
        payload["format"] = format
    resp = _post("/api/chat", payload)
    if "error" in resp:
        raise RuntimeError(
            f"Ollama returned an error: {resp['error']}. If it mentions the model, pull it "
            f"first with `ollama pull {MODEL}`."
        )
    return resp["message"]["content"]


def complete_json(system: str, user: str, max_tokens: int = 4000, schema: dict = None) -> dict:
    """Ask the local model for JSON and parse it.

    Pass `schema` (a JSON Schema dict) when the caller knows the exact shape it needs --
    Ollama then constrains generation at the token level so the model cannot produce a
    field of the wrong type (e.g. a string field coming back as a list, which happened in
    practice without this). Prefer this over hoping the prompt's shape description alone
    is followed.

    Without a schema, falls back to stripping markdown fencing and extracting the
    outermost {...} block -- local models follow "output only JSON" instructions less
    reliably than the cloud model does.
    """
    text = complete_text(system, user, max_tokens=max_tokens, format=schema).strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise
