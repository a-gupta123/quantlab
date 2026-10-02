import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from quantlab.config import get_settings
from quantlab.db import get_session

SessionDep = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100, description="Page size (max 100)")]
Offset = Annotated[int, Query(ge=0, le=100_000)]


def require_service_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Only the Next.js server holds API_INTERNAL_TOKEN. Browsers never call the
    API directly, and CORS is deliberately not enabled: CORS is not authentication."""
    expected = get_settings().api_internal_token.get_secret_value()
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "API_INTERNAL_TOKEN is not configured on the API."
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid service token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
