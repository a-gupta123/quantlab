"""Strategy chatbot end to end through the API, with the model call stubbed."""

import pytest
from conftest import TEST_TOKEN
from factories import dataset_dates, make_dataset
from fastapi.testclient import TestClient
from test_strategy_builder import RSI_SPEC, answer, operand

from quantlab import strategy_builder
from quantlab.config import get_settings
from quantlab.worker import Worker

pytestmark = pytest.mark.db
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}

LONG_SHORT = {
    **RSI_SPEC,
    "direction": "long_short",
    "short_entry": {
        "mode": "all",
        "groups": [],
        "rules": [
            {
                "left": operand(indicator="rsi", period=14),
                "op": ">",
                "right": operand(kind="value", value=65),
            }
        ],
    },
    "stop_loss_pct": 5,
}


@pytest.fixture
def client(db_env, monkeypatch):
    from quantlab.api.main import create_app
    from quantlab.storage import get_storage

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    get_storage.cache_clear()
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def model(monkeypatch):
    """Queue canned model answers; records the messages each call received."""
    queue, calls = [], []

    def fake_post(messages, transport):
        calls.append(messages)
        return queue.pop(0)

    monkeypatch.setattr(strategy_builder, "_post", fake_post)
    return queue, calls


def test_chat_build_iterate_and_backtest(client, model):
    queue, calls = model

    queue.append(answer("invalid", reply="Not about markets."))
    r = client.post("/api/strategies", headers=AUTH, json={"message": "asdf qwer"})
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "invalid" and r.json()["strategy"] is None
    assert client.get("/api/strategies", headers=AUTH).json()["total"] == 0

    queue.append(answer())
    r = client.post("/api/strategies", headers=AUTH, json={"message": "RSI 30/70"}).json()
    strat = r["strategy"]
    assert r["outcome"] == "built" and strat["name"] == "RSI mean reversion"
    v1 = strat["versions"][0]
    assert v1["version"] == 1 and v1["fidelity"] == 77.8 and v1["warmup_bars"] == 15
    assert v1["rules_text"][1] == "Enter long when: rsi(14) < 30"
    assert [m["role"] for m in strat["messages"]] == ["user", "assistant"]

    queue.append(answer(spec=LONG_SHORT, reply="Added shorts above 65 and a 5% stop."))
    r = client.post(
        f"/api/strategies/{strat['id']}/messages",
        headers=AUTH,
        json={"message": "also short when RSI > 65, 5% stop"},
    ).json()
    sent = calls[-1]
    assert any(m["content"].startswith("PREVIOUS_SPEC:") for m in sent)
    assert any(m["content"] == "RSI 30/70" for m in sent)
    assert [v["version"] for v in r["strategy"]["versions"]] == [1, 2]
    v2 = r["strategy"]["versions"][1]

    listing = client.get("/api/strategies", headers=AUTH).json()
    assert listing["items"][0]["latest_version"] == 2
    assert listing["items"][0]["direction"] == "long_short"

    ds = make_dataset()
    dates = dataset_dates(ds)
    warm = client.get(
        f"/api/datasets/{ds}/warmup?strategy_version_id={v2['id']}", headers=AUTH
    ).json()
    assert warm["warmup_bars"] == 15 and warm["earliest_start"] == str(dates[15])

    body = dict(
        name="chatbot run",
        dataset_id=ds,
        start_date=str(dates[20]),
        end_date=str(dates[-1]),
        initial_capital=10000,
        fee_bps=5,
        slippage_bps=5,
        strategy_version_id=v2["id"],
    )
    exp = client.post("/api/experiments", headers=AUTH, json=body)
    assert exp.status_code == 201, exp.text
    assert exp.json()["strategy_config"]["rules"]["version"] == 2

    Worker("strategy-test").run_once()
    detail = client.get(f"/api/experiments/{exp.json()['id']}", headers=AUTH).json()
    assert detail["status"] == "completed", detail["error"]
    sides = {t["side"] for t in detail["trades"]}
    assert sides <= {"buy", "sell", "short", "cover"} and "short" in sides
    page = client.get("/api/experiments", headers=AUTH).json()
    assert page["items"][0]["strategy_label"] == "RSI mean reversion (v2)"

    # Same version + costs reuses the config row.
    again = client.post("/api/experiments", headers=AUTH, json={**body, "name": "again"}).json()
    assert again["strategy_config"]["id"] == exp.json()["strategy_config"]["id"]


@pytest.mark.parametrize(
    "extra, fragment",
    [
        (dict(short_window=10, long_window=50, strategy_version_id=1), "not both"),
        (dict(short_window=10), "required for the MA crossover"),
        (dict(strategy_version_id=99999), "not found"),
    ],
)
def test_experiment_strategy_validation(client, extra, fragment):
    ds = make_dataset()
    dates = dataset_dates(ds)
    body = dict(
        name="x",
        dataset_id=ds,
        start_date=str(dates[200]),
        end_date=str(dates[-1]),
        initial_capital=10000,
        fee_bps=5,
        slippage_bps=5,
        **extra,
    )
    r = client.post("/api/experiments", headers=AUTH, json=body)
    assert r.status_code in (404, 422) and fragment in r.text


def test_chat_without_key_is_503_and_saves_nothing(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    assert client.get("/api/strategies/status", headers=AUTH).json()["available"] is False
    r = client.post("/api/strategies", headers=AUTH, json={"message": "RSI 30/70"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.text
    assert client.get("/api/strategies", headers=AUTH).json()["total"] == 0
    assert client.post("/api/strategies", headers=AUTH, json={"message": "  "}).status_code == 422
    assert client.get("/api/strategies/12345", headers=AUTH).status_code == 404
