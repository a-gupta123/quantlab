"""Real FinBERT inference. Skipped unless RUN_MODEL_TESTS=1 because it needs the
'ml' extra and ~440 MB of model weights:

    RUN_MODEL_TESTS=1 uv run --extra ml pytest -m model
"""

import os

import pytest

pytestmark = [
    pytest.mark.model,
    pytest.mark.skipif(os.environ.get("RUN_MODEL_TESTS") != "1", reason="set RUN_MODEL_TESTS=1"),
]


def test_finbert_classifies_clear_headlines():
    from quantlab.sentiment import model

    model.reset_for_tests(None)
    clf = model.get_classifier()
    pos, neg = clf.classify(
        [
            "Operating profit rose sharply and the company raised guidance",
            "Company profits fell sharply amid falling sales",
        ]
    )
    assert max(pos, key=pos.get) == "positive"
    assert max(neg, key=neg.get) == "negative"
    for scores in (pos, neg):
        assert set(scores) == {"positive", "negative", "neutral"}
        assert abs(sum(scores.values()) - 1) < 1e-3
    assert clf.revision == "4556d13015211d73dccd3fdd39d39232506f3e43"
