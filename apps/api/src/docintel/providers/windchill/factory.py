"""Construct the configured Windchill document provider from settings."""

from __future__ import annotations

from docintel.core.config import Settings
from docintel.providers.windchill.base import WindchillDocumentProvider
from docintel.providers.windchill.mock import MockWindchillDocumentProvider
from docintel.providers.windchill.windchill12 import Windchill12DocumentProvider


def create_windchill_provider(settings: Settings) -> WindchillDocumentProvider:
    """Return the provider selected by ``settings.windchill_provider``.

    ``mock`` is DEVELOPMENT ONLY (local sample documents). ``windchill12`` is a stub that
    answers every call with ``windchill_not_implemented``.
    """
    if settings.windchill_provider == "mock":
        return MockWindchillDocumentProvider(settings.samples_dir)
    if settings.windchill_provider == "windchill12":
        return Windchill12DocumentProvider()
    raise ValueError(f"Unknown Windchill provider: {settings.windchill_provider!r}")
