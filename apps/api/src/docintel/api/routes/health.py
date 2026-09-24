"""Service health and non-secret configuration facts."""

from __future__ import annotations

from fastapi import APIRouter

from docintel import __version__
from docintel.api.deps import ContainerDep, describe_ai
from docintel.schemas.api import HealthResponse, Limits, SourceProviderInfo

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(container: ContainerDep) -> HealthResponse:
    """Liveness plus the active AI and document providers and the request limits.

    Never includes credentials, endpoints or other configuration secrets.
    """
    settings = container.settings
    return HealthResponse(
        version=__version__,
        ai=describe_ai(container.llm),
        windchill=SourceProviderInfo(
            name=container.windchill.name,
            development_only=container.windchill.development_only,
        ),
        limits=Limits(
            max_upload_mb=settings.max_upload_mb,
            max_pages=settings.max_pages,
            max_question_chars=settings.max_question_chars,
        ),
    )
