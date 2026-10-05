from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from quantlab.api import schemas
from quantlab.api.deps import Limit, Offset, SessionDep
from quantlab.datasets import (
    ADJUSTMENTS,
    DatasetImportError,
    DatasetMeta,
    DuplicateDatasetError,
    earliest_valid_start,
    import_dataset,
)
from quantlab.engine.backtest import MAX_WINDOW
from quantlab.engine.rules import RuleSpec
from quantlab.models import Dataset, StrategyVersion
from quantlab.storage import StorageError, get_storage

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.get("", response_model=schemas.Page[schemas.DatasetOut])
def list_datasets(session: SessionDep, limit: Limit = 50, offset: Offset = 0):
    with session.begin():
        total = session.scalar(select(func.count()).select_from(Dataset))
        rows = session.scalars(
            select(Dataset)
            .order_by(Dataset.name, Dataset.version.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        items = [schemas.DatasetOut.model_validate(r) for r in rows]
    return schemas.Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{dataset_id}", response_model=schemas.DatasetOut)
def get_dataset(dataset_id: int, session: SessionDep):
    with session.begin():
        ds = session.get(Dataset, dataset_id)
        if ds is None:
            raise HTTPException(404, f"Dataset {dataset_id} not found.")
        return schemas.DatasetOut.model_validate(ds)


@router.get("/{dataset_id}/warmup", response_model=schemas.WarmupOut)
def warmup(
    dataset_id: int,
    session: SessionDep,
    long_window: Annotated[int | None, Query(ge=2, le=MAX_WINDOW)] = None,
    strategy_version_id: Annotated[int | None, Query(gt=0)] = None,
):
    if (long_window is None) == (strategy_version_id is None):
        raise HTTPException(422, "Give exactly one of long_window or strategy_version_id.")
    with session.begin():
        if session.get(Dataset, dataset_id) is None:
            raise HTTPException(404, f"Dataset {dataset_id} not found.")
        if strategy_version_id is not None:
            version = session.get(StrategyVersion, strategy_version_id)
            if version is None:
                raise HTTPException(404, f"Strategy version {strategy_version_id} not found.")
            bars = RuleSpec.model_validate(version.spec).warmup_bars()
        else:
            bars = long_window
        first = earliest_valid_start(session, dataset_id, bars)
    return schemas.WarmupOut(
        dataset_id=dataset_id,
        long_window=long_window,
        strategy_version_id=strategy_version_id,
        warmup_bars=bars,
        earliest_start=first,
    )


@router.post(
    "",
    response_model=schemas.DatasetImportOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {}, 413: {}, 422: {}},
)
def upload_dataset(
    session: SessionDep,
    file: Annotated[UploadFile, File(description="OHLC CSV")],
    name: Annotated[str, Form(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9 ._-]+$")],
    symbol: Annotated[str, Form(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.^-]+$")],
    source: Annotated[str, Form(min_length=3, max_length=300)],
    adjustment: Annotated[str, Form()],
    is_synthetic: Annotated[bool, Form()] = False,
):
    if adjustment not in ADJUSTMENTS:
        raise HTTPException(422, f"adjustment must be one of: {', '.join(ADJUSTMENTS)}.")
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 5 MB.")
    meta = DatasetMeta(
        name=name.strip(),
        symbol=symbol.upper(),
        source=source.strip(),
        adjustment=adjustment,
        is_synthetic=is_synthetic,
    )
    try:
        with session.begin():
            ds, report = import_dataset(
                session,
                get_storage(),
                raw,
                meta,
                manifest={"imported_via": "api-upload", "original_filename": file.filename},
            )
            out = schemas.DatasetOut.model_validate(ds)
    except DuplicateDatasetError as exc:
        return JSONResponse(
            status_code=409, content={"detail": str(exc), "existing_dataset_id": exc.existing_id}
        )
    except DatasetImportError as exc:
        report = exc.report
        return JSONResponse(
            status_code=422,
            content={
                "detail": str(exc),
                "errors": [e.as_dict() for e in report.errors] if report else [],
                "warnings": [w.as_dict() for w in report.warnings] if report else [],
            },
        )
    except StorageError as exc:
        raise HTTPException(502, f"Could not store the dataset file: {exc}") from exc
    return schemas.DatasetImportOut(dataset=out, warnings=[w.as_dict() for w in report.warnings])
