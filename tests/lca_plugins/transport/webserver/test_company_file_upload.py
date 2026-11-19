"""``lca-gateway-routes-company-files`` — POST /files upload seam.

Covers the wire contract with the company file service, the all-or-nothing
handler semantics, and the frozen LobeHub surface (``/files/{id}/meta``).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.files import upload as upload_module
from lca.plugins.transport.webserver.handlers.files.files import get_file_meta
from lca.plugins.transport.webserver.handlers.files.fileservice import (
    FileServiceContractViolationError,
    FileServiceError,
    FileServiceSettings,
    FileServiceUnavailableError,
    parse_upload_response,
    redact_url,
)
from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_company_files import (
    PLUGIN_ID,
    make_upload_handler,
)
from lca.plugins.transport.webserver.routes_company_files import setup as company_plugin

_SOURCE = "https://kltb-common.oss-cn-shenzhen.aliyuncs.com/test/2026/11/19/x.log"
_FAKE_CREDENTIAL = "unit-test-credential"
_FROZEN_META_KEYS = {
    "attachment_id",
    "name",
    "mime_type",
    "url",
    "size_bytes",
    "previewable",
}


class _StubClient:
    def __init__(
        self,
        sources: Sequence[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.sources = list(sources or [])
        self.error = error
        self.calls: list[list[tuple[str, bytes, str]]] = []

    async def upload_sources(self, files: Sequence[tuple[str, bytes, str]]) -> list[str]:
        self.calls.append(list(files))
        if self.error is not None:
            raise self.error
        return self.sources[: len(files)] or [f"{_SOURCE}?i={i}" for i in range(len(files))]


def _build_app(tmp_path: Path, client: Any) -> tuple[TestClient, LocalFileStore]:
    store = LocalFileStore(root=tmp_path / "uploads")
    app = Starlette()
    app.state.file_store = store
    app.add_route("/files", make_upload_handler(client), methods=["POST", "OPTIONS"])

    async def _meta(request: Request) -> JSONResponse:
        return await get_file_meta(request, store)

    app.add_route("/files/{attachment_id}/meta", _meta, methods=["GET"])
    return TestClient(app), store


def _post(client: TestClient, files: list[tuple[str, bytes, str]]) -> Any:
    return client.post(
        "/files",
        files=[("files", (name, data, mime)) for name, data, mime in files],
    )


# ── 文件服务响应契约 ──────────────────────────────────────────────


def test_parse_upload_response_accepts_string_array() -> None:
    payload = {
        "code": "200",
        "msg": "成功",
        "data": {"files": ["https://a/1.log", "https://a/2.txt"]},
    }
    assert parse_upload_response(payload, expected=2) == ["https://a/1.log", "https://a/2.txt"]


def test_parse_upload_response_rejects_object_items() -> None:
    """needView=1 shape (objects) is a contract violation, never a fallback."""
    payload = {"code": "200", "data": {"files": [{"valid": "v", "source": "s"}]}}
    with pytest.raises(FileServiceContractViolationError):
        parse_upload_response(payload, expected=1)


def test_parse_upload_response_rejects_count_mismatch() -> None:
    payload = {"code": "200", "data": {"files": ["https://a/1.log"]}}
    with pytest.raises(FileServiceContractViolationError):
        parse_upload_response(payload, expected=2)


def test_parse_upload_response_surfaces_upstream_error() -> None:
    with pytest.raises(FileServiceError) as excinfo:
        parse_upload_response({"code": "500", "msg": "boom"}, expected=1)
    assert "500" in str(excinfo.value)


def test_redact_url_drops_query() -> None:
    assert redact_url("http://h:9094/upload?pwd=secret") == "http://h:9094/upload"


def test_settings_not_configured_without_credentials() -> None:
    assert not FileServiceSettings(base_url="", app_id="a", pwd=_FAKE_CREDENTIAL).configured
    assert FileServiceSettings(base_url="http://h", app_id="a", pwd=_FAKE_CREDENTIAL).configured


# ── 路由处理器 ──────────────────────────────────────────────────


def test_upload_single_file_stores_attachment(tmp_path: Path) -> None:
    stub = _StubClient(sources=[_SOURCE])
    client, store = _build_app(tmp_path, stub)

    response = _post(client, [("x.log", b"hello world", "text/plain")])

    assert response.status_code == 200
    body = response.json()["files"]
    assert len(body) == 1
    item = body[0]
    assert item["source"] == _SOURCE
    assert item["name"] == "x.log"
    assert item["url"] == f"/files/{item['attachment_id']}"
    assert len(stub.calls) == 1
    assert stub.calls[0][0][0] == "x.log"
    stored = store.get(item["attachment_id"])
    assert stored is not None
    assert stored.source_url == _SOURCE


def test_upload_multiple_files_keeps_order(tmp_path: Path) -> None:
    stub = _StubClient(sources=["https://a/1.log", "https://a/2.txt"])
    client, _ = _build_app(tmp_path, stub)

    response = _post(
        client,
        [("1.log", b"one", "text/plain"), ("2.txt", b"two", "text/plain")],
    )

    assert response.status_code == 200
    body = response.json()["files"]
    assert [item["name"] for item in body] == ["1.log", "2.txt"]
    assert [item["source"] for item in body] == ["https://a/1.log", "https://a/2.txt"]
    assert len(stub.calls) == 1
    assert [entry[0] for entry in stub.calls[0]] == ["1.log", "2.txt"]


def test_upload_requires_files_field(tmp_path: Path) -> None:
    client, _ = _build_app(tmp_path, _StubClient())
    response = client.post("/files", data={"other": "x"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_files"


def test_upload_rejects_too_many_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_module, "MAX_INGEST_FILES", 2)
    client, _ = _build_app(tmp_path, _StubClient())
    response = _post(
        client,
        [
            ("a.log", b"a", "text/plain"),
            ("b.log", b"b", "text/plain"),
            ("c.log", b"c", "text/plain"),
        ],
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "too_many_files"


def test_upload_rejects_oversized_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_module, "MAX_INGEST_FILE_BYTES", 4)
    stub = _StubClient()
    client, _ = _build_app(tmp_path, stub)
    response = _post(client, [("big.log", b"123456", "text/plain")])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "file_too_large"
    assert stub.calls == []


def test_upload_rejects_mime_mismatch(tmp_path: Path) -> None:
    stub = _StubClient()
    client, _ = _build_app(tmp_path, stub)
    response = _post(client, [("fake.pdf", b"not a pdf", "application/pdf")])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_file"
    assert stub.calls == []


def test_upload_maps_unavailable_to_502(tmp_path: Path) -> None:
    stub = _StubClient(error=FileServiceUnavailableError("down"))
    client, store = _build_app(tmp_path, stub)

    response = _post(client, [("x.log", b"data", "text/plain")])

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "fileservice_unavailable"
    assert store.list() == []


def test_upload_maps_contract_violation_to_502(tmp_path: Path) -> None:
    stub = _StubClient(error=FileServiceContractViolationError("shape"))
    client, store = _build_app(tmp_path, stub)

    response = _post(client, [("x.log", b"data", "text/plain")])

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "fileservice_contract_violation"
    assert store.list() == []


def test_upload_without_credentials_returns_503(tmp_path: Path) -> None:
    client, _ = _build_app(tmp_path, None)
    response = _post(client, [("x.log", b"data", "text/plain")])
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "fileservice_unconfigured"


# ── 冻结面：LobeHub 的 /files/{id}/meta ─────────────────────────


def test_file_meta_response_keys_unchanged(tmp_path: Path) -> None:
    stub = _StubClient(sources=[_SOURCE])
    client, _ = _build_app(tmp_path, stub)
    attachment_id = _post(client, [("x.log", b"hello", "text/plain")]).json()["files"][0][
        "attachment_id"
    ]

    response = client.get(f"/files/{attachment_id}/meta")

    assert response.status_code == 200
    assert set(response.json()) == _FROZEN_META_KEYS
    assert "source_url" not in response.json()


def test_stored_file_meta_sidecar_records_source(tmp_path: Path) -> None:
    stub = _StubClient(sources=[_SOURCE])
    client, store = _build_app(tmp_path, stub)
    attachment_id = _post(client, [("x.log", b"hello", "text/plain")]).json()["files"][0][
        "attachment_id"
    ]

    meta_path = store.root / attachment_id / "meta.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))

    assert payload["source_url"] == _SOURCE
    assert store.get(attachment_id).source_url == _SOURCE  # type: ignore[union-attr]


# ── plugin 形状 ────────────────────────────────────────────────


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        if key == "route_registry":
            return self._router
        raise AssertionError(f"unexpected required capability {key!r}")

    def inject(self, key: str, *, default: Any = None) -> Any:
        return default

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


def _effects_of(plugin_obj: Any) -> tuple[str, ...]:
    from lca.harness.plugin.declaration import definition_from_plugin

    definition = definition_from_plugin(plugin_obj, module=__name__)
    effects = definition.spec.effects
    if isinstance(effects, (list, tuple)):
        return tuple(
            effect.value if hasattr(effect, "value") else str(effect) for effect in effects
        )
    return (effects.value if hasattr(effects, "value") else str(effects),)


@pytest.mark.asyncio
async def test_plugin_registers_single_route_with_network_effect() -> None:
    from lca.harness.plugin.declaration import definition_from_plugin

    definition = definition_from_plugin(company_plugin, module=__name__)
    assert "network" in _effects_of(company_plugin)
    assert "route_registry" in definition.required_capability_keys
    assert definition.id == PLUGIN_ID
    router = RouteRegistry()
    ctx = _FakeCtx(router)

    await company_plugin.setup(ctx, {"base_url": "http://h", "app_id": "a", "pwd": "p"})

    assert list(router._exact) == ["/files"]
    assert set(router._exact["/files"].methods or ()) == {"POST", "OPTIONS"}
    assert len(ctx._fake_runtime.effects) == 1
    assert ctx._fake_runtime.effects[0][1] == "route:/files"


@pytest.mark.asyncio
async def test_plugin_without_credentials_still_registers_route() -> None:
    router = RouteRegistry()
    ctx = _FakeCtx(router)

    await company_plugin.setup(ctx, {})

    assert list(router._exact) == ["/files"]


def test_plugin_identity_is_stable() -> None:
    assert PLUGIN_ID == "lca-gateway-routes-company-files"
