"""Persistence for chatbot-built strategies.

A chat turn reads context in one short transaction, calls the model with no
transaction open, then writes the user message, the reply, and (if built) a new
immutable StrategyVersion in a second transaction.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from quantlab import strategy_builder
from quantlab.config import get_settings
from quantlab.db import transaction
from quantlab.models import CustomStrategy, StrategyMessage, StrategyVersion
from quantlab.services import NotFound


@dataclass
class ChatTurn:
    outcome: str
    reply: str
    strategy_id: int | None
    version_id: int | None


def _context(strategy_id: int) -> tuple[list[dict[str, str]], dict | None]:
    with transaction() as s:
        if s.get(CustomStrategy, strategy_id) is None:
            raise NotFound(f"Strategy {strategy_id} not found.")
        msgs = s.scalars(
            select(StrategyMessage)
            .where(StrategyMessage.strategy_id == strategy_id)
            .order_by(StrategyMessage.id.desc())
            .limit(strategy_builder.MAX_HISTORY_MESSAGES)
        ).all()
        latest = s.scalars(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version.desc())
            .limit(1)
        ).first()
        history = [{"role": m.role, "content": m.content} for m in reversed(msgs)]
        return history, (latest.spec if latest else None)


class RateLimited(RuntimeError):
    pass


def _check_daily_limit() -> None:
    limit = get_settings().strategy_chat_daily_limit
    with transaction() as s:
        used = s.scalar(
            select(func.count())
            .select_from(StrategyMessage)
            .where(
                StrategyMessage.role == "user",
                StrategyMessage.created_at > func.now() - text("interval '24 hours'"),
            )
        )
    if used >= limit:
        raise RateLimited(
            f"The strategy builder's limit of {limit} messages per 24 hours has been reached. "
            "Try again later."
        )


def chat(message: str, strategy_id: int | None = None, transport=None) -> ChatTurn:
    _check_daily_limit()
    history, previous = _context(strategy_id) if strategy_id else ([], None)
    result = strategy_builder.build(message, history, previous, transport=transport)

    if strategy_id is None and result.outcome == "invalid":
        # Nothing to save: an invalid first message does not create a strategy.
        return ChatTurn("invalid", result.reply, None, None)

    with transaction() as s:
        if strategy_id is None:
            strat = CustomStrategy(name=result.name[:120])
            s.add(strat)
            s.flush()
        else:
            strat = s.get(CustomStrategy, strategy_id, with_for_update=True)
            if strat is None:
                raise NotFound(f"Strategy {strategy_id} not found.")
            strat.updated_at = func.now()
        s.add(StrategyMessage(strategy_id=strat.id, role="user", content=message.strip()))
        version = None
        if result.outcome == "built":
            next_v = (
                s.scalar(
                    select(func.max(StrategyVersion.version)).where(
                        StrategyVersion.strategy_id == strat.id
                    )
                )
                or 0
            ) + 1
            version = StrategyVersion(
                strategy_id=strat.id,
                version=next_v,
                spec=result.spec.model_dump(mode="json", exclude_none=True),
                requirements=[r.model_dump() for r in result.requirements],
                fidelity=result.fidelity,
                summary=result.reply,
                assumptions=result.assumptions,
                model=result.model,
            )
            s.add(version)
            s.flush()
        s.add(
            StrategyMessage(
                strategy_id=strat.id,
                role="assistant",
                content=result.reply,
                outcome=result.outcome,
                version_id=version.id if version else None,
            )
        )
        return ChatTurn(result.outcome, result.reply, strat.id, version.id if version else None)


def get_version(session: Session, version_id: int) -> StrategyVersion:
    v = session.get(StrategyVersion, version_id)
    if v is None:
        raise NotFound(f"Strategy version {version_id} not found.")
    return v
