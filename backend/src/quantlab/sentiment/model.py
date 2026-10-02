"""FinBERT inference boundary.

The worker loads `ProsusAI/finbert` (pinned revision) once per process and reuses
it for every batch. Tests replace `get_classifier` with a fake; the real model is
only exercised by the explicit smoke test (`python -m quantlab.sentiment.smoke`).
"""

from __future__ import annotations

import threading
from typing import Protocol

from quantlab.config import get_settings

LABELS = ("positive", "negative", "neutral")


class ModelUnavailable(RuntimeError):
    """The model could not be loaded. Never substitute fake classifications."""


class Classifier(Protocol):
    model_name: str
    revision: str

    def classify(self, texts: list[str]) -> list[dict[str, float]]: ...


class FinBertClassifier:
    def __init__(self, model_name: str, revision: str, batch_size: int, local_only: bool):
        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                pipeline,
            )
        except ImportError as exc:
            raise ModelUnavailable(
                "transformers/torch are not installed in this image. Install the 'ml' extra "
                "(the worker image does this)."
            ) from exc
        try:
            load = {"revision": revision, "local_files_only": local_only}
            tokenizer = AutoTokenizer.from_pretrained(model_name, **load)
            model = AutoModelForSequenceClassification.from_pretrained(model_name, **load)
            model.eval()
            self._pipe = pipeline(
                "text-classification", model=model, tokenizer=tokenizer, device=-1, top_k=None
            )
        except Exception as exc:  # network, missing cache, corrupt files...
            hint = (
                " The worker runs with SENTIMENT_LOCAL_FILES_ONLY=true; download the model "
                "into HF_HOME first (see docs/learning-guide.md#transformers)."
                if local_only
                else ""
            )
            raise ModelUnavailable(
                f"Could not load {model_name}@{revision[:7]}: {exc}.{hint}"
            ) from exc
        self.model_name = model_name
        self.revision = revision
        self.batch_size = batch_size

    def classify(self, texts: list[str]) -> list[dict[str, float]]:
        outputs = self._pipe(texts, batch_size=self.batch_size, truncation=True, max_length=128)
        results = []
        for scores in outputs:
            by_label = {s["label"].lower(): float(s["score"]) for s in scores}
            if set(by_label) != set(LABELS):
                raise ModelUnavailable(f"Unexpected model labels: {sorted(by_label)}")
            results.append(by_label)
        return results


_lock = threading.Lock()
_classifier: Classifier | None = None
_status = "not_loaded"


def get_classifier() -> Classifier:
    global _classifier, _status
    with _lock:
        if _classifier is None:
            s = get_settings()
            _status = "loading"
            try:
                _classifier = FinBertClassifier(
                    s.sentiment_model_name,
                    s.sentiment_model_revision,
                    s.sentiment_batch_size,
                    s.sentiment_local_files_only,
                )
            except ModelUnavailable as exc:
                _status = f"unavailable: {str(exc)[:300]}"
                raise
            _status = "loaded"
        return _classifier


def model_status() -> str:
    return _status


def reset_for_tests(classifier: Classifier | None = None, status: str = "not_loaded") -> None:
    global _classifier, _status
    with _lock:
        _classifier = classifier
        _status = "loaded" if classifier is not None else status
