"""API routers, in the order they are mounted by ``create_app``."""

from fastapi import APIRouter

from docintel.api.routes import analysis, documents, health, windchill

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    windchill.router,
    documents.router,
    analysis.router,
)

__all__ = ["ROUTERS"]
