"""Optional LLM explanation of a finished workflow (disabled by default).

The model only receives already-computed facts and is asked to explain them.
Its output is rejected if it contains any number that does not appear in those
facts, so it cannot introduce metrics. It never chooses parameters, never sees
raw prices, and never generates code.
"""

from __future__ import annotations

import json
import re

import httpx

from quantlab.config import get_settings

_NUM = re.compile(r"-?\d+(?:\.\d+)?")

SYSTEM_PROMPT = (
    "You explain backtest research results to a student. Use only the JSON facts "
    "provided. Do not introduce any number that is not in the facts. Do not recommend "
    "trading, do not predict future returns, and do not suggest new parameters. "
    "Mention that the held-out result is a single out-of-sample check. Under 150 words."
)


class LLMUnavailable(RuntimeError):
    pass


def _allowed_numbers(facts: dict) -> set[str]:
    allowed: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, bool):
            return
        elif isinstance(v, (int, float)):
            for scale in (1, 100):
                for digits in (0, 1, 2, 3, 4):
                    allowed.add(f"{v * scale:.{digits}f}")
        elif isinstance(v, str):
            allowed.update(_NUM.findall(v))

    walk(facts)
    return allowed


def unsupported_numbers(text: str, facts: dict) -> list[str]:
    allowed = _allowed_numbers(facts)
    return [n for n in _NUM.findall(text) if n not in allowed and n.lstrip("-") not in allowed]


def explain(facts: dict) -> tuple[str, str]:
    s = get_settings()
    key = s.openai_api_key.get_secret_value()
    if not (s.llm_explanations_enabled and key):
        raise LLMUnavailable("LLM explanations are disabled.")
    try:
        resp = httpx.post(
            f"{s.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": s.openai_model,
                "temperature": 0,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(facts)},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise LLMUnavailable(f"LLM request failed: {exc}") from exc
    bad = unsupported_numbers(text, facts)
    if bad:
        raise LLMUnavailable(f"Rejected LLM text containing numbers not in the facts: {bad[:5]}")
    return text, s.openai_model
