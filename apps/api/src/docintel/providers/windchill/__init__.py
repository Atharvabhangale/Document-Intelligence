"""Windchill document providers: the provider interface, the DEVELOPMENT ONLY mock, the
Windchill 12 stub and the settings-based factory."""

from docintel.providers.windchill.base import (
    ContentDescriptor,
    DocumentContent,
    WindchillDocument,
    WindchillDocumentProvider,
)
from docintel.providers.windchill.factory import create_windchill_provider
from docintel.providers.windchill.mock import MockWindchillDocumentProvider
from docintel.providers.windchill.windchill12 import Windchill12DocumentProvider

__all__ = [
    "ContentDescriptor",
    "DocumentContent",
    "MockWindchillDocumentProvider",
    "Windchill12DocumentProvider",
    "WindchillDocument",
    "WindchillDocumentProvider",
    "create_windchill_provider",
]
