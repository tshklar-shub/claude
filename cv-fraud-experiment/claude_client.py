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


def complete_text(system: str, user: str, max_tokens: int = 2000) -> str:
    # `temperature` is intentionally omitted -- current-generation models (e.g. the
    # claude-sonnet-5 default above) reject it outright ("temperature is deprecated
    # for this model", a 400 from the API, not a transient failure). Determinism for
    # extraction/scoring now comes from the prompt being evidence-based and
    # instructed to be conservative, not from temperature=0.
    resp = client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # content[0] is not reliably the text block -- current-generation models can
    # return a ThinkingBlock (extended thinking) ahead of the TextBlock. Find the
    # actual text block by type rather than assuming position.
    for block in resp.content:
        if block.type == "text":
            return block.text
    raise RuntimeError(
        f"No text block in response (stop_reason={resp.stop_reason}, "
        f"content types={[b.type for b in resp.content]}). Most likely max_tokens "
        f"was exhausted during internal reasoning before any answer was produced -- "
        f"try calling with a larger max_tokens."
    )


def complete_json(system: str, user: str, max_tokens: int = 2000) -> dict:
    """Ask Claude for strict JSON and parse it, stripping any markdown fencing."""
    text = complete_text(system, user, max_tokens=max_tokens)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
