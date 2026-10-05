"""Strategy chatbot: turn a plain-English description into a validated RuleSpec.

The model fills a fixed JSON schema (OpenAI structured outputs). It never writes
code. Its output is validated by `RuleSpec`; on a validation error it gets the
error back and one more chance to fix it. The fidelity percentage is computed
here, from the model's own requirement checklist, so the arithmetic is
deterministic, but the per-requirement judgements are the model's and the UI
labels the number as an estimate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from quantlab.config import get_settings
from quantlab.engine.rules import RuleSpec

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_MESSAGES = 12
REPAIR_ATTEMPTS = 1
STATUS_SCORE = {"exact": 1.0, "approximated": 0.5, "unsupported": 0.0}
INVALID_PREFIX = "This is not a valid trading strategy."


class BuilderUnavailable(RuntimeError):
    """No API key configured, or the provider failed."""


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=300)
    status: Literal["exact", "approximated", "unsupported"]
    weight: int = Field(ge=1, le=3)
    note: str = Field(default="", max_length=400)


class _Draft(BaseModel):
    """What the model returns, before the spec is validated."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["build", "invalid"]
    reply: str = Field(min_length=1, max_length=2000)
    name: str = Field(default="", max_length=120)
    requirements: list[Requirement] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    spec: dict[str, Any] | None = None


@dataclass
class BuildResult:
    outcome: Literal["built", "invalid"]
    reply: str
    model: str
    name: str = ""
    spec: RuleSpec | None = None
    requirements: list[Requirement] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    fidelity: float = 0.0


def fidelity(requirements: list[Requirement]) -> float:
    """Weighted share of the user's requirements the spec captures, 0-100."""
    total = sum(r.weight for r in requirements)
    if not total:
        return 0.0
    got = sum(r.weight * STATUS_SCORE[r.status] for r in requirements)
    return round(100.0 * got / total, 1)


# ----------------------------------------------------------------- schema


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def _num(kind: str = "number") -> dict:
    return _nullable({"type": kind})


_OPERAND = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "indicator",
        "period",
        "source",
        "std_mult",
        "fast",
        "slow",
        "signal_period",
        "offset",
        "scale",
        "value",
    ],
    "properties": {
        "kind": {"type": "string", "enum": ["indicator", "value"]},
        "indicator": _nullable(
            {
                "type": "string",
                "enum": [
                    "close",
                    "open",
                    "high",
                    "low",
                    "volume",
                    "sma",
                    "ema",
                    "rsi",
                    "macd",
                    "macd_signal",
                    "macd_hist",
                    "bb_upper",
                    "bb_middle",
                    "bb_lower",
                    "highest_high",
                    "lowest_low",
                    "return_pct",
                    "volatility_pct",
                ],
            }
        ),
        "period": _num("integer"),
        "source": _nullable({"type": "string", "enum": ["close", "open", "high", "low", "volume"]}),
        "std_mult": _num(),
        "fast": _num("integer"),
        "slow": _num("integer"),
        "signal_period": _num("integer"),
        "offset": {"type": "integer"},
        "scale": {"type": "number"},
        "value": _num(),
    },
}
_COMPARISON = {
    "type": "object",
    "additionalProperties": False,
    "required": ["left", "op", "right"],
    "properties": {
        "left": {"$ref": "#/$defs/operand"},
        "op": {"type": "string", "enum": [">", "<", ">=", "<=", "crosses_above", "crosses_below"]},
        "right": {"$ref": "#/$defs/operand"},
    },
}
_GROUP = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "rules"],
    "properties": {
        "mode": {"type": "string", "enum": ["all", "any"]},
        "rules": {"type": "array", "items": {"$ref": "#/$defs/comparison"}},
    },
}
_CONDITION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "rules", "groups"],
    "properties": {
        "mode": {"type": "string", "enum": ["all", "any"]},
        "rules": {"type": "array", "items": {"$ref": "#/$defs/comparison"}},
        "groups": {"type": "array", "items": {"$ref": "#/$defs/group"}},
    },
}
_COND_REF = _nullable({"$ref": "#/$defs/condition"})
_SPEC = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "direction",
        "long_entry",
        "long_exit",
        "short_entry",
        "short_exit",
        "stop_loss_pct",
        "take_profit_pct",
        "max_holding_days",
    ],
    "properties": {
        "direction": {"type": "string", "enum": ["long_only", "short_only", "long_short"]},
        "long_entry": _COND_REF,
        "long_exit": _COND_REF,
        "short_entry": _COND_REF,
        "short_exit": _COND_REF,
        "stop_loss_pct": _num(),
        "take_profit_pct": _num(),
        "max_holding_days": _num("integer"),
    },
}
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "reply", "name", "requirements", "assumptions", "spec"],
    "properties": {
        "verdict": {"type": "string", "enum": ["build", "invalid"]},
        "reply": {"type": "string"},
        "name": {"type": "string"},
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "status", "weight", "note"],
                "properties": {
                    "text": {"type": "string"},
                    "status": {"type": "string", "enum": ["exact", "approximated", "unsupported"]},
                    "weight": {"type": "integer", "enum": [1, 2, 3]},
                    "note": {"type": "string"},
                },
            },
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "spec": _nullable({"$ref": "#/$defs/spec"}),
    },
    "$defs": {
        "operand": _OPERAND,
        "comparison": _COMPARISON,
        "group": _GROUP,
        "condition": _CONDITION,
        "spec": _SPEC,
    },
}

SYSTEM_PROMPT = """\
You turn a user's plain-English trading strategy into a rule specification for a
daily-bar backtester. You never write code; you only fill the JSON schema.

WHAT THE BACKTESTER CAN DO
- One instrument, daily bars: open, high, low, close, volume (volume may be missing,
  in which case volume rules never trigger). No intraday data, news, fundamentals,
  options, order book, other symbols, or calendar/seasonality data.
- Positions: long, short, or flat (cash), always 100% of equity, no leverage,
  no pyramiding or partial sizing. Shorts have no borrow fees.
- Decisions are made at each day's close and filled at the next day's open.
- Indicators (all trailing, no look-ahead):
  close/open/high/low/volume (raw); sma, ema (period, optional source);
  rsi (period>=2, Wilder); macd, macd_signal, macd_hist (fast, slow, signal_period;
  defaults 12/26/9); bb_upper, bb_middle, bb_lower (period, std_mult default 2);
  highest_high, lowest_low (highest high / lowest low of the `period` bars BEFORE
  today, for breakouts); return_pct (percent change over `period` bars, e.g. 5 = 5%);
  volatility_pct (std dev of daily % returns over `period` bars).
- Operand extras: offset = value N bars ago; scale = multiplier (1.02 * sma = 2% above).
  A constant uses kind "value" and `value`. Unused operand fields are null; offset 0
  and scale 1 by default.
- Comparisons: > < >= <= crosses_above crosses_below.
- A condition combines its `rules` and its `groups` with mode "all" (AND) or "any"
  (OR); groups nest one level. Max 8 rules per list, 4 groups.
- Exits: long_exit / short_exit conditions (optional), stop_loss_pct and
  take_profit_pct (percent from entry, checked at close), max_holding_days.
  Without any exit, a position is held until an opposite entry (long_short) or forever.
- direction long_only needs long_entry and no short rules; short_only the reverse;
  long_short needs both entries. Max period 400 bars, max offset 50.

DECIDING
- verdict "invalid" ONLY if the message is gibberish, not about trading at all, or
  describes something with no possible approximation using price/volume data
  (e.g. "buy when my horoscope says so"). If ANY part can be expressed, verdict is
  "build": approximate what you can and mark the rest unsupported. When unsure, build.
- If the user is iterating, start from PREVIOUS_SPEC and change only what they ask.
  The requirements must then cover the whole strategy as now requested (carry over
  earlier requirements that still apply).
- Fill unspecified details with common defaults (e.g. RSI 14, MACD 12/26/9) and list
  each as an assumption. Do not count defaults as requirements.

REQUIREMENTS CHECKLIST (used to compute a match percentage)
- Split the user's request into atomic requirements in their words (entry trigger,
  exit trigger, direction, each parameter, each risk rule).
- Only list things the user actually asked for. Never add a requirement for something
  they did NOT ask for (e.g. "no stop loss specified"), and never list a default you
  chose; those go in assumptions. Suggestions belong in `reply`, not in requirements.
- status: exact = implemented precisely; approximated = implemented with a stated
  substitution or simplification; unsupported = not implemented. Be honest; do not
  mark something exact if you changed it. weight: 3 core logic, 2 important detail,
  1 minor detail. Explain approximations/unsupported items in `note`.

REPLY
- `reply`: 1-4 friendly sentences to the user summarizing what you built, what you
  approximated, and one suggestion for refining it. For invalid, explain why briefly.
  Write for a day trader, not a programmer: say "50-day average", not "sma(50)", and
  never mention JSON, specs, schemas, or field names.
- `name`: a short title (max 6 words). spec must be null when verdict is invalid.
"""


# ------------------------------------------------------------------- call


def is_available() -> bool:
    return bool(get_settings().openai_api_key.get_secret_value())


def _post(messages: list[dict], transport: httpx.BaseTransport | None) -> dict:
    s = get_settings()
    key = s.openai_api_key.get_secret_value()
    if not key:
        raise BuilderUnavailable(
            "The strategy chatbot is not configured. Set OPENAI_API_KEY on the API service."
        )
    try:
        with httpx.Client(transport=transport, timeout=60) as client:
            resp = client.post(
                f"{s.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": s.openai_model,
                    "temperature": 0.2,
                    "max_tokens": 4000,
                    "messages": messages,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "strategy_build",
                            "strict": True,
                            "schema": RESPONSE_SCHEMA,
                        },
                    },
                },
            )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
    except httpx.HTTPStatusError as exc:
        raise BuilderUnavailable(
            f"The language model request failed (HTTP {exc.response.status_code})."
        ) from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise BuilderUnavailable(f"The language model request failed: {exc}") from exc
    if msg.get("refusal"):
        raise BuilderUnavailable(f"The model declined: {msg['refusal']}")
    try:
        return json.loads(msg["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BuilderUnavailable("The model returned malformed JSON.") from exc


def _strip_nulls(v: Any) -> Any:
    """The strict schema forces every key; drop nulls so RuleSpec defaults apply."""
    if isinstance(v, dict):
        return {k: _strip_nulls(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_strip_nulls(x) for x in v]
    return v


def _validate(raw: dict) -> tuple[_Draft, RuleSpec | None]:
    draft = _Draft.model_validate(raw)
    if draft.verdict == "invalid":
        return draft, None
    if draft.spec is None:
        raise ValueError("verdict is 'build' but spec is null.")
    if not draft.requirements:
        raise ValueError("verdict is 'build' but the requirements checklist is empty.")
    return draft, RuleSpec.model_validate(_strip_nulls(draft.spec))


def build(
    message: str,
    history: list[dict[str, str]] | None = None,
    previous_spec: dict | None = None,
    transport: httpx.BaseTransport | None = None,
) -> BuildResult:
    """One chatbot turn. Raises BuilderUnavailable if the provider cannot answer."""
    message = message.strip()[:MAX_MESSAGE_CHARS]
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or [])[-MAX_HISTORY_MESSAGES:]:
        messages.append({"role": h["role"], "content": h["content"][:MAX_MESSAGE_CHARS]})
    if previous_spec is not None:
        messages.append(
            {"role": "system", "content": "PREVIOUS_SPEC:\n" + json.dumps(previous_spec)}
        )
    messages.append({"role": "user", "content": message})

    last_error = ""
    for _ in range(1 + REPAIR_ATTEMPTS):
        raw = _post(messages, transport)
        try:
            draft, spec = _validate(raw)
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)[:1500]
            messages.append({"role": "assistant", "content": json.dumps(raw)})
            messages.append(
                {
                    "role": "user",
                    "content": "Your spec failed validation. Fix it and answer again with the "
                    f"full JSON. Errors:\n{last_error}",
                }
            )
            continue
        model = get_settings().openai_model
        if spec is None:
            reply = draft.reply.strip()
            if not reply.startswith(INVALID_PREFIX):
                reply = f"{INVALID_PREFIX} {reply}"
            return BuildResult(outcome="invalid", reply=reply, model=model)
        return BuildResult(
            outcome="built",
            reply=draft.reply.strip(),
            model=model,
            name=(draft.name.strip() or message[:60]).strip(),
            spec=spec,
            requirements=draft.requirements,
            assumptions=[a.strip() for a in draft.assumptions if a.strip()],
            fidelity=fidelity(draft.requirements),
        )
    raise BuilderUnavailable(
        f"The model could not produce a valid strategy after a retry: {last_error[:300]}"
    )
