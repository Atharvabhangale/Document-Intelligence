"""Windchill12DocumentProvider is a documented stub that must not guess any endpoint."""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from docintel.core.config import Settings
from docintel.core.errors import WindchillNotImplementedError
from docintel.core.models import Requester
from docintel.providers.windchill import Windchill12DocumentProvider, create_windchill_provider
from docintel.providers.windchill import windchill12 as stub_module

REQUESTER = Requester(user_id="dev.user")


def test_identity() -> None:
    provider = Windchill12DocumentProvider()
    assert provider.name == "windchill12"
    assert provider.development_only is False


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.list_documents(requester=REQUESTER),
        lambda p: p.list_documents(requester=REQUESTER, query="SOP", limit=5),
        lambda p: p.get_document("any-reference", requester=REQUESTER),
        lambda p: p.get_primary_content("any-reference", requester=REQUESTER),
    ],
)
def test_every_method_raises_not_implemented(call) -> None:
    with pytest.raises(WindchillNotImplementedError) as info:
        call(Windchill12DocumentProvider())
    assert info.value.http_status == 501
    assert info.value.code == "windchill_not_implemented"
    assert info.value.retryable is False


def test_source_contains_no_endpoint_guesses() -> None:
    source = inspect.getsource(stub_module).lower()
    for forbidden in ("servlet", "odata", "://", "/wt/", "rest/", "api/v"):
        assert forbidden not in source, forbidden


def test_docstring_lists_what_must_be_validated() -> None:
    doc = stub_module.__doc__ or ""
    for expected in (
        "12.0.2.19",
        "WRS",
        "service account",
        "Read permission",
        "Download permission",
        "requester",
        "iteration",
        "docs/windchill-integration.md",
        "WINDCHILL_AI_RESEARCH.md",
    ):
        assert expected in doc, expected


def test_factory_selects_stub() -> None:
    provider = create_windchill_provider(Settings(windchill_provider="windchill12"))
    assert isinstance(provider, Windchill12DocumentProvider)


def test_api_maps_stub_to_501(settings: Settings) -> None:
    from docintel.api.app import create_app
    from test_api_documents import make_container

    container = make_container(
        settings.model_copy(update={"windchill_provider": "windchill12"}),
        windchill=Windchill12DocumentProvider(),
    )
    client = TestClient(create_app(container=container))

    listing = client.get("/api/windchill/documents")
    assert listing.status_code == 501
    assert listing.json()["error"]["code"] == "windchill_not_implemented"

    imported = client.post("/api/documents/from-windchill", json={"reference": "wt-ref"})
    assert imported.status_code == 501
    assert imported.json()["error"] == {
        "code": "windchill_not_implemented",
        "message": WindchillNotImplementedError.default_message,
        "retryable": False,
    }

    health = client.get("/api/health").json()
    assert health["windchill"] == {"name": "windchill12", "developmentOnly": False}
