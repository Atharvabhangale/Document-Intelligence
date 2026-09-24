"""FastAPI application factory.

Run with ``uvicorn docintel.api.app:app``. Importing this module is cheap: it reads settings
and declares routes, but the services (LLM client, repositories, providers) are built on
startup or on the first request.

* The JSON API lives under ``/api``; the OpenAPI document is ``/api/openapi.json``. The
  interactive Swagger/ReDoc pages are disabled because they load scripts from a third-party
  CDN, which the Content-Security-Policy forbids.
* When ``SERVE_WEB_DIST`` points at a built web app (a directory with ``index.html``), it is
  served at ``/`` with single-page-app fallback to ``index.html``; ``/api`` is never shadowed.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from docintel import __version__
from docintel.api.deps import Container, ContainerHolder
from docintel.api.errors import register_exception_handlers
from docintel.api.middleware import (
    REQUEST_ID_HEADER,
    BodySizeLimitMiddleware,
    ErrorBoundaryMiddleware,
    RequestContextMiddleware,
)
from docintel.api.routes import ROUTERS
from docintel.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

API_TITLE = "AI Document Intelligence for PTC Windchill"
# Allowance for multipart framing and the small metadata field on top of the file size limit.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def create_app(settings: Settings | None = None, *, container: Container | None = None) -> FastAPI:
    """Create the application.

    Args:
        settings: configuration; defaults to ``container.settings`` or ``get_settings()``.
        container: pre-built services (tests); built lazily from ``settings`` when omitted.
    """
    if settings is None:
        settings = container.settings if container is not None else get_settings()
    holder = ContainerHolder(settings, container)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _configure_logging(settings.log_level)
        services = holder.get()
        logger.info(
            "Document intelligence API %s started: ai=%s model=%s windchill=%s",
            __version__,
            services.llm.name,
            services.llm.model,
            services.windchill.name,
        )
        yield

    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.state.container_holder = holder
    register_exception_handlers(app)

    # add_middleware wraps the current stack, so the last one added is the outermost.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES,
    )
    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        allow_credentials=False,
    )
    app.add_middleware(RequestContextMiddleware)

    for router in ROUTERS:
        app.include_router(router)

    web_dist = _web_dist(settings.serve_web_dist)
    if web_dist is not None:
        app.mount("/", SinglePageAppFiles(directory=web_dist), name="web")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> dict[str, str]:
            return {
                "service": API_TITLE,
                "message": (
                    "The web UI is not built. Build apps/web (its dist directory is served "
                    "here) or use the web dev server. The API is under /api."
                ),
                "health": "/api/health",
                "openapi": "/api/openapi.json",
            }

    return app


class SinglePageAppFiles(StaticFiles):
    """Static files of the built web app with SPA fallback.

    Unknown paths that look like client-side routes (no file extension in the last segment)
    are answered with ``index.html``; missing assets stay 404. ``api`` paths are never served
    from here, so an unknown API route is a JSON 404. Path traversal is prevented by
    ``StaticFiles`` (paths are resolved and must stay inside ``directory``).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        if _is_api_path(path):
            raise StarletteHTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or "." in PurePosixPath(path).name:
                raise
        response = await super().get_response("index.html", scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _is_api_path(path: str) -> bool:
    return path == "api" or path.startswith("api/")


def _web_dist(path: Path | None) -> Path | None:
    if path is None or not (path / "index.html").is_file():
        return None
    return path


def _configure_logging(level_name: str) -> None:
    """Make application logs visible when the host (e.g. uvicorn) did not configure them."""
    level = logging.getLevelNamesMapping().get(level_name.upper(), logging.INFO)
    logging.getLogger("docintel").setLevel(level)
    if not logging.getLogger().handlers:
        logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")


app = create_app()
