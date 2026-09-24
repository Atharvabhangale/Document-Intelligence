"""Browse documents of the configured Windchill provider (development browsing)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from docintel.api.deps import ContainerDep, RequesterDep
from docintel.schemas.api import SourceProviderInfo, WindchillDocumentList

router = APIRouter(prefix="/api/windchill", tags=["windchill"])


@router.get("/documents", response_model=WindchillDocumentList)
def list_windchill_documents(
    container: ContainerDep,
    requester: RequesterDep,
    q: Annotated[str | None, Query(max_length=200, description="Search text")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> WindchillDocumentList:
    """Documents visible to the requester whose number, name or location matches ``q``."""
    provider = container.windchill
    return WindchillDocumentList(
        provider=SourceProviderInfo(name=provider.name, development_only=provider.development_only),
        items=provider.list_documents(requester=requester, query=q, limit=limit),
    )
