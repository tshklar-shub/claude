"""Thin wrapper around the Anthropic SDK, shared by generation/extraction/scoring."""

import json
import os

import anthropic

MODEL = os.environ.get("CV_FRAUD_MODEL", "claude-sonnet-5")

_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def complete_text(system: str, user: str, max_tokens: int = 2000, temperature: float = 1.0) -> str:
    resp = client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def complete_json(system: str, user: str, max_tokens: int = 2000) -> dict:
    """Ask Claude for strict JSON and parse it, stripping any markdown fencing."""
    text = complete_text(system, user, max_tokens=max_tokens, temperature=0)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
