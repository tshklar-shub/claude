"""
Local-LLM client via Ollama, for the real-CV path where candidate data must
not leave the machine it's running on. Same interface as claude_client.py
(complete_text/complete_json) so extract_cv.py/score_cv.py don't need to
know which backend they're talking to -- only the transport differs.

Requires Ollama installed and running locally (https://ollama.com), plus a
model pulled ahead of time:
    ollama pull llama3.1:8b        # or whatever CV_FRAUD_LOCAL_MODEL is set to

Nothing here makes any network call outside localhost. If that's ever not
true, that's a bug -- the whole point of this module is that it isn't
claude_client.py.
"""

import json
import os
import urllib.error
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("CV_FRAUD_LOCAL_MODEL", "llama3.1:8b")

REQUEST_TIMEOUT_SECONDS = 300  # local inference on CPU can be slow


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


def complete_text(system: str, user: str, max_tokens: int = 4000) -> str:
    resp = _post("/api/chat", {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens},
    })
    if "error" in resp:
        raise RuntimeError(
            f"Ollama returned an error: {resp['error']}. If it mentions the model, pull it "
            f"first with `ollama pull {MODEL}`."
        )
    return resp["message"]["content"]


def complete_json(system: str, user: str, max_tokens: int = 4000) -> dict:
    """Ask the local model for strict JSON and parse it, stripping any markdown fencing.
    Local models follow "output only JSON" instructions less reliably than the cloud
    model does -- this is intentionally more defensive about stripping stray prose."""
    text = complete_text(system, user, max_tokens=max_tokens).strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    # Some local models wrap JSON in explanatory text despite instructions -- fall back to
    # extracting the outermost {...} block if a direct parse fails.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise
