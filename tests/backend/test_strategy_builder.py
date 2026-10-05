"""Strategy chatbot builder, with the OpenAI API replaced by httpx.MockTransport."""

import json

import httpx
import pytest

from quantlab import strategy_builder as sb
from quantlab.config import get_settings


def operand(**kw):
    base = dict(
        kind="indicator",
        indicator=None,
        period=None,
        source=None,
        std_mult=None,
        fast=None,
        slow=None,
        signal_period=None,
        offset=0,
        scale=1.0,
        value=None,
    )
    base.update(kw)
    return base


RSI_SPEC = {
    "direction": "long_only",
    "long_entry": {
        "mode": "all",
        "groups": [],
        "rules": [
            {
                "left": operand(indicator="rsi", period=14),
                "op": "<",
                "right": operand(kind="value", value=30),
            }
        ],
    },
    "long_exit": {
        "mode": "all",
        "groups": [],
        "rules": [
            {
                "left": operand(indicator="rsi", period=14),
                "op": ">",
                "right": operand(kind="value", value=70),
            }
        ],
    },
    "short_entry": None,
    "short_exit": None,
    "stop_loss_pct": None,
    "take_profit_pct": None,
    "max_holding_days": None,
}


def answer(verdict="build", spec=RSI_SPEC, reqs=None, reply="Built an RSI strategy."):
    return {
        "verdict": verdict,
        "reply": reply,
        "name": "RSI mean reversion" if verdict == "build" else "",
        "requirements": reqs
        if reqs is not None
        else [
            {"text": "Buy when RSI below 30", "status": "exact", "weight": 3, "note": ""},
            {"text": "Sell when RSI above 70", "status": "exact", "weight": 3, "note": ""},
            {
                "text": "Only on Mondays",
                "status": "approximated",
                "weight": 2,
                "note": "No calendar data; ignored day-of-week.",
            },
            {"text": "Use earnings news", "status": "unsupported", "weight": 1, "note": ""},
        ],
        "assumptions": ["RSI period 14"],
        "spec": spec if verdict == "build" else None,
    }


class FakeOpenAI:
    def __init__(self, *responses, status=200):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "boom"})
        body = self.responses.pop(0)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(body), "refusal": None}}]}
        )

    @property
    def transport(self):
        return httpx.MockTransport(self)


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_builds_validated_spec_and_computes_fidelity_in_code():
    fake = FakeOpenAI(answer())
    r = sb.build(
        "buy RSI<30, sell RSI>70, mondays only, use earnings news", transport=fake.transport
    )
    assert r.outcome == "built" and r.name == "RSI mean reversion"
    assert r.spec.long_entry.rules[0].left.indicator == "rsi"
    # (3*1 + 3*1 + 2*0.5 + 1*0) / 9 = 77.8%
    assert r.fidelity == 77.8
    req = fake.requests[0]
    assert req["response_format"]["json_schema"]["strict"] is True
    assert req["messages"][0]["role"] == "system"


def test_invalid_verdict_says_not_valid():
    fake = FakeOpenAI(answer("invalid", reply="That is a recipe for pancakes."))
    r = sb.build("flour, eggs, milk", transport=fake.transport)
    assert r.outcome == "invalid" and r.spec is None
    assert r.reply.startswith("This is not a valid trading strategy.")


def test_repairs_once_after_validation_error():
    broken = json.loads(json.dumps(RSI_SPEC))
    broken["long_entry"]["rules"][0]["left"]["period"] = None  # rsi without a period
    fake = FakeOpenAI(answer(spec=broken), answer())
    r = sb.build("rsi strategy", transport=fake.transport)
    assert r.outcome == "built" and len(fake.requests) == 2
    assert "failed validation" in fake.requests[1]["messages"][-1]["content"]
    assert "period" in fake.requests[1]["messages"][-1]["content"]


def test_gives_up_after_repeated_invalid_output():
    fake = FakeOpenAI(answer(reqs=[]), answer(reqs=[]))
    with pytest.raises(sb.BuilderUnavailable, match="after a retry"):
        sb.build("rsi", transport=fake.transport)


def test_iteration_sends_history_and_previous_spec():
    fake = FakeOpenAI(answer())
    history = [{"role": "user", "content": "rsi 30/70"}, {"role": "assistant", "content": "ok"}]
    sb.build("add a 5% stop", history, RSI_SPEC, transport=fake.transport)
    msgs = fake.requests[0]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "system", "user"]
    assert msgs[3]["content"].startswith("PREVIOUS_SPEC:")
    assert msgs[-1]["content"] == "add a 5% stop"


def test_provider_errors_and_missing_key(monkeypatch):
    with pytest.raises(sb.BuilderUnavailable, match="HTTP 500"):
        sb.build("rsi", transport=FakeOpenAI(status=500).transport)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    assert not sb.is_available()
    with pytest.raises(sb.BuilderUnavailable, match="not configured"):
        sb.build("rsi", transport=FakeOpenAI().transport)


def test_fidelity_weights():
    R = sb.Requirement
    assert sb.fidelity([]) == 0.0
    assert sb.fidelity([R(text="a", status="exact", weight=1)]) == 100.0
    assert (
        sb.fidelity(
            [
                R(text="a", status="approximated", weight=2),
                R(text="b", status="unsupported", weight=2),
            ]
        )
        == 25.0
    )


def test_schema_is_valid_for_strict_structured_outputs():
    """OpenAI strict mode: every object lists all its properties as required and
    forbids additional properties."""

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(sb.RESPONSE_SCHEMA)
