"""Health endpoint, root/SPA serving and application wiring."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docintel import __version__
from docintel.api.app import create_app
from docintel.api.deps import build_container
from docintel.core.config import Settings
from docintel.providers.llm.fake import ScriptedLLMProvider
from docintel.providers.windchill import MockWindchillDocumentProvider
from test_api_documents import api_settings, make_client, make_container

TEST_KEY = "test-key-not-real"  # the key set by the conftest ``settings`` fixture


def test_health_with_scripted_provider(settings: Settings, tmp_path: Path) -> None:
    container = make_container(
        api_settings(settings, tmp_path, max_upload_mb=25, max_pages=300),
        llm=ScriptedLLMProvider([], model="scripted-model"),
    )
    response = make_client(container).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "ai": {
            "provider": "scripted",
            "model": "scripted-model",
            "configured": True,
            "developmentOnly": True,
        },
        "windchill": {"name": "mock-windchill", "developmentOnly": True},
        "limits": {"maxUploadMb": 25, "maxPages": 300, "maxQuestionChars": 1000},
    }


def test_health_never_exposes_credentials(settings: Settings, tmp_path: Path) -> None:
    from docintel.providers.llm.factory import create_llm_provider

    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == TEST_KEY
    container = make_container(api_settings(settings, tmp_path), llm=create_llm_provider(settings))
    response = make_client(container).get("/api/health")

    assert response.status_code == 200
    assert response.json()["ai"]["provider"] == "anthropic"
    assert response.json()["ai"]["model"] == settings.ai_model
    assert TEST_KEY not in response.text
    assert all(TEST_KEY not in value for value in response.headers.values())


def test_root_hint_without_web_build(settings: Settings, tmp_path: Path) -> None:
    client = make_client(make_container(api_settings(settings, tmp_path)))
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["health"] == "/api/health"


def test_openapi_is_served_under_api(settings: Settings, tmp_path: Path) -> None:
    client = make_client(make_container(api_settings(settings, tmp_path)))
    schema = client.get("/api/openapi.json").json()
    assert "/api/documents/{document_id}/summarize" in schema["paths"]
    assert client.get("/docs").status_code == 404  # CDN-based docs UI disabled (CSP)


def test_container_is_built_lazily_once(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[Settings] = []
    app_settings = api_settings(settings, tmp_path)

    def fake_build(s: Settings):
        built.append(s)
        return make_container(s)

    monkeypatch.setattr("docintel.api.deps.build_container", fake_build)
    app = create_app(app_settings)
    assert built == []  # creating the app builds nothing

    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/windchill/documents").status_code == 200
    assert built == [app_settings]


def test_lifespan_builds_container_on_startup(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[Settings] = []
    monkeypatch.setattr(
        "docintel.api.deps.build_container", lambda s: built.append(s) or make_container(s)
    )
    with TestClient(create_app(api_settings(settings, tmp_path))) as client:
        assert len(built) == 1
        assert client.get("/api/health").status_code == 200
    assert len(built) == 1


def test_module_level_app_imports_cleanly() -> None:
    module = importlib.import_module("docintel.api.app")
    assert module.app.title
    assert module.app.state.container_holder is not None


def test_importing_the_app_loads_no_ai_or_pdf_libraries() -> None:
    heavy = ("anthropic", "pdfplumber", "docintel.intelligence", "docintel.providers.llm")
    code = f"import sys, docintel.api.app; print(sorted(m for m in {heavy!r} if m in sys.modules))"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip() == "[]"


def test_build_container_wires_real_services(settings: Settings, tmp_path: Path) -> None:
    try:
        container = build_container(api_settings(settings, tmp_path))
    except ImportError as exc:  # parallel development: a dependency package is incomplete
        pytest.skip(f"application packages not integrated yet: {exc}")
    assert isinstance(container.windchill, MockWindchillDocumentProvider)
    assert container.llm.name == "anthropic"
    assert container.document_service is not None
    assert hasattr(container.intelligence, "summarize")


# --- static web app --------------------------------------------------------------------------


@pytest.fixture
def web_client(settings: Settings, tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the web root", encoding="utf-8")
    container = make_container(api_settings(settings, tmp_path, serve_web_dist=dist))
    return make_client(container)


def test_spa_serves_index_and_assets(web_client: TestClient) -> None:
    root = web_client.get("/")
    assert root.status_code == 200
    assert "id=root" in root.text
    assert root.headers["content-type"].startswith("text/html")
    assert "script-src 'self'" in root.headers["content-security-policy"]

    asset = web_client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text


@pytest.mark.parametrize("path", ["/documents/abc", "/deep/client/route", "/?wtRef=x&autorun=1"])
def test_spa_fallback_for_client_routes(web_client: TestClient, path: str) -> None:
    response = web_client.get(path)
    assert response.status_code == 200
    assert "id=root" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_spa_missing_asset_is_404(web_client: TestClient) -> None:
    response = web_client.get("/assets/missing.js")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("path", ["/api", "/api/unknown", "/api/documents/x/unknown/deeper"])
def test_spa_never_shadows_api(web_client: TestClient, method: str, path: str) -> None:
    response = getattr(web_client, method)(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_api_still_served_with_spa(web_client: TestClient) -> None:
    assert web_client.get("/api/health").json()["status"] == "ok"


@pytest.mark.parametrize(
    "path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt"]
)
def test_spa_path_traversal(web_client: TestClient, path: str) -> None:
    response = web_client.get(path)
    assert "outside the web root" not in response.text
