from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from quantlab.api import schemas
from quantlab.api.deps import Limit, Offset, SessionDep
from quantlab.api.serializers import latest_job
from quantlab.models import Headline, SentimentBatch
from quantlab.sentiment.samples import SAMPLE_HEADLINES
from quantlab.sentiment.service import MAX_HEADLINES, create_batch

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])


@router.get("/samples", response_model=list[str])
def samples():
    return SAMPLE_HEADLINES


def _batch_out(session, batch: SentimentBatch) -> schemas.SentimentBatchOut:
    job = latest_job(session, sentiment_batch_id=batch.id)
    return schemas.SentimentBatchOut(
        id=batch.id,
        status=batch.status,
        error=batch.error,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        job=schemas.JobOut.model_validate(job) if job else None,
        headlines=[
            schemas.HeadlineOut(
                id=h.id,
                position=h.position,
                text=h.text,
                source=h.source,
                result=(
                    schemas.SentimentResultOut.model_validate(h.result, from_attributes=True)
                    if h.result
                    else None
                ),
            )
            for h in batch.headlines
        ],
    )


def _load(session, batch_id: int) -> SentimentBatch | None:
    return session.scalars(
        select(SentimentBatch)
        .where(SentimentBatch.id == batch_id)
        .options(selectinload(SentimentBatch.headlines).selectinload(Headline.result))
    ).first()


@router.post(
    "/batches", response_model=schemas.SentimentBatchOut, status_code=status.HTTP_201_CREATED
)
def create(body: schemas.SentimentCreate, session: SessionDep):
    items = [(h, "user") for h in body.headlines]
    if body.include_samples:
        items += [(h, "sample") for h in SAMPLE_HEADLINES]
    if len(items) > MAX_HEADLINES:
        raise HTTPException(422, f"At most {MAX_HEADLINES} headlines per batch.")
    with session.begin():
        batch = create_batch(session, items)
        batch_id = batch.id
    with session.begin():
        return _batch_out(session, _load(session, batch_id))


@router.get("/batches", response_model=schemas.Page[schemas.SentimentBatchOut])
def list_batches(session: SessionDep, limit: Limit = 10, offset: Offset = 0):
    with session.begin():
        total = session.scalar(select(func.count()).select_from(SentimentBatch))
        ids = session.scalars(
            select(SentimentBatch.id).order_by(SentimentBatch.id.desc()).limit(limit).offset(offset)
        ).all()
        items = [_batch_out(session, _load(session, i)) for i in ids]
    return schemas.Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/batches/{batch_id}", response_model=schemas.SentimentBatchOut)
def get_batch(batch_id: int, session: SessionDep):
    with session.begin():
        batch = _load(session, batch_id)
        if batch is None:
            raise HTTPException(404, f"Sentiment batch {batch_id} not found.")
        return _batch_out(session, batch)
