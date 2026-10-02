"""Sentiment batches: headlines are classified by the worker and stored with the
model name and revision. Sentiment is an annotation only; it never feeds the
backtest or the research workflow."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantlab import jobs
from quantlab.config import get_settings
from quantlab.db import transaction
from quantlab.models import Headline, SentimentBatch, SentimentResult
from quantlab.sentiment import model as sentiment_model

MAX_HEADLINES = 32


def create_batch(session: Session, items: list[tuple[str, str]]) -> SentimentBatch:
    """items: (text, source) where source is 'sample' or 'user'."""
    batch = SentimentBatch(status="queued")
    session.add(batch)
    session.flush()
    for i, (txt, source) in enumerate(items):
        session.add(Headline(batch_id=batch.id, position=i, text=txt, source=source))
    session.flush()
    jobs.enqueue(session, "sentiment", batch.id, get_settings().job_max_attempts)
    return batch


def execute_sentiment_job(job: jobs.ClaimedJob) -> None:
    from quantlab.worker import NonRetryableError

    with transaction() as s:
        rows = s.execute(
            select(Headline.id, Headline.text)
            .where(Headline.batch_id == job.target_id)
            .order_by(Headline.position)
        ).all()
    if not rows:
        raise NonRetryableError("Batch has no headlines.")
    try:
        clf = sentiment_model.get_classifier()
        scores = clf.classify([r.text for r in rows])
    except sentiment_model.ModelUnavailable as exc:
        raise NonRetryableError(f"Sentiment model unavailable: {exc}") from exc
    if len(scores) != len(rows):
        raise NonRetryableError("Model returned a different number of results than inputs.")

    with transaction() as s:
        jobs.lock_owned(s, job)
        for row, sc in zip(rows, scores, strict=True):
            label = max(sc, key=sc.get)
            s.execute(
                pg_insert(SentimentResult)
                .values(
                    headline_id=row.id,
                    label=label,
                    score_positive=sc["positive"],
                    score_negative=sc["negative"],
                    score_neutral=sc["neutral"],
                    model_name=clf.model_name,
                    model_revision=clf.revision,
                )
                .on_conflict_do_nothing(index_elements=["headline_id"])
            )
        jobs.mark_completed(s, job)
