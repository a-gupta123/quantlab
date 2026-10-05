from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from quantlab import strategies, strategy_builder
from quantlab.api import schemas
from quantlab.api.deps import Limit, Offset, SessionDep
from quantlab.api.serializers import strategy_detail
from quantlab.config import get_settings
from quantlab.models import CustomStrategy, StrategyVersion
from quantlab.services import NotFound

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("/status", response_model=schemas.StrategyStatusOut)
def chatbot_status():
    return schemas.StrategyStatusOut(
        available=strategy_builder.is_available(), model=get_settings().openai_model
    )


@router.get("", response_model=schemas.Page[schemas.StrategySummary])
def list_strategies(session: SessionDep, limit: Limit = 50, offset: Offset = 0):
    latest = (
        select(
            StrategyVersion.strategy_id,
            func.max(StrategyVersion.version).label("v"),
        )
        .group_by(StrategyVersion.strategy_id)
        .subquery()
    )
    q = (
        select(CustomStrategy, StrategyVersion)
        .join(latest, latest.c.strategy_id == CustomStrategy.id)
        .join(
            StrategyVersion,
            (StrategyVersion.strategy_id == latest.c.strategy_id)
            & (StrategyVersion.version == latest.c.v),
        )
    )
    with session.begin():
        total = session.scalar(select(func.count()).select_from(q.subquery()))
        rows = session.execute(
            q.order_by(CustomStrategy.updated_at.desc(), CustomStrategy.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    items = [
        schemas.StrategySummary(
            id=s.id,
            name=s.name,
            updated_at=s.updated_at,
            latest_version_id=v.id,
            latest_version=v.version,
            fidelity=v.fidelity,
            direction=v.spec.get("direction", ""),
        )
        for s, v in rows
    ]
    return schemas.Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{strategy_id}", response_model=schemas.StrategyDetail)
def get_strategy(strategy_id: int, session: SessionDep):
    with session.begin():
        detail = strategy_detail(session, strategy_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Strategy {strategy_id} not found.")
    return detail


def _turn(session, message: str, strategy_id: int | None) -> schemas.StrategyChatOut:
    try:
        turn = strategies.chat(message, strategy_id)
    except NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except strategy_builder.BuilderUnavailable as exc:
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if not strategy_builder.is_available()
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, str(exc)) from exc
    detail = None
    if turn.strategy_id is not None:
        with session.begin():
            detail = strategy_detail(session, turn.strategy_id)
    return schemas.StrategyChatOut(outcome=turn.outcome, reply=turn.reply, strategy=detail)


@router.post("", response_model=schemas.StrategyChatOut)
def start_chat(body: schemas.StrategyChatIn, session: SessionDep):
    """Describe a strategy in words. Creates a strategy only if something was built."""
    return _turn(session, body.message, None)


@router.post("/{strategy_id}/messages", response_model=schemas.StrategyChatOut)
def continue_chat(strategy_id: int, body: schemas.StrategyChatIn, session: SessionDep):
    """Iterate: the model sees the conversation and the latest version's spec."""
    return _turn(session, body.message, strategy_id)
