"""run 链路 assistant_id 解析与 fail-closed 校验（ADR-0187 §3 D7）。

覆盖：

- ``decode_create_run`` 解析 ``assistant_id``（缺省 / 合法 / 非字符串 400）；
- ``_to_run_request`` 透传 ``assistant_id``；
- ``_validate_assistant_binding``：无绑定 ⇒ None（I-A1）；有绑定但无
  catalog ⇒ 400；未知 id ⇒ 404；digest 不匹配 ⇒ 409；合法 ⇒ None；
- ``RunAmbit.assistant_id`` + ``current_assistant_id``；
- ``RunSessionRequest`` / ``RunSession`` 携带 ``assistant_id``。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.observability.facade.run_ambit import (
    RunAmbit,
    bind_run_ambit,
    current_assistant_id,
)
from lca.plugins.assistant.catalog import AssistantCatalogImpl
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    CreateRunRequest,
    _to_run_request,
    _validate_assistant_binding,
    decode_create_run,
)
from lca.plugins.transport.webserver.handlers.runs.session.setup_types import (
    RunSessionRequest,
)


def _messages(text: str = "你好") -> list[dict[str, Any]]:
    return [{"role": "user", "content": text}]


def _resolve_mode(ctx: Any, mode: str) -> str:
    return mode or "solo"


@pytest.fixture
def file_store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(tmp_path / "files")


@pytest.fixture
def catalog(tmp_path: Path) -> AssistantCatalogImpl:
    return AssistantCatalogImpl(root=tmp_path / "assistants")


def _request_with_catalog(catalog: Any | None) -> Request:
    app = Starlette()
    if catalog is not None:
        app.state.assistant_catalog = catalog
    scope = {"type": "http", "method": "POST", "path": "/runs", "headers": [], "app": app}
    return Request(scope)


class TestDecodeCreateRunAssistantId:
    @pytest.mark.asyncio
    async def test_absent_defaults_empty(self, file_store: LocalFileStore) -> None:
        decoded = await decode_create_run(
            {"messages": _messages()}, ctx=None, file_store=file_store, resolve_mode=_resolve_mode
        )
        assert isinstance(decoded, CreateRunRequest)
        assert decoded.assistant_id == ""

    @pytest.mark.asyncio
    async def test_blank_normalizes_empty(self, file_store: LocalFileStore) -> None:
        decoded = await decode_create_run(
            {"messages": _messages(), "assistant_id": "  "},
            ctx=None,
            file_store=file_store,
            resolve_mode=_resolve_mode,
        )
        assert isinstance(decoded, CreateRunRequest)
        assert decoded.assistant_id == ""

    @pytest.mark.asyncio
    async def test_valid_assistant_id_parsed(self, file_store: LocalFileStore) -> None:
        decoded = await decode_create_run(
            {"messages": _messages(), "assistant_id": "asst_abc"},
            ctx=None,
            file_store=file_store,
            resolve_mode=_resolve_mode,
        )
        assert isinstance(decoded, CreateRunRequest)
        assert decoded.assistant_id == "asst_abc"

    @pytest.mark.asyncio
    async def test_non_string_rejected_400(self, file_store: LocalFileStore) -> None:
        decoded = await decode_create_run(
            {"messages": _messages(), "assistant_id": 123},
            ctx=None,
            file_store=file_store,
            resolve_mode=_resolve_mode,
        )
        assert decoded.status_code == 400

    def test_to_run_request_carries_assistant_id(self, file_store: LocalFileStore) -> None:
        carrier = CreateRunRequest(
            profile="web-standard",
            question="q",
            user_text="q",
            mode="solo",
            attachment_ids=(),
            prior_turns=(),
            agent=None,  # type: ignore[arg-type]
            device_id="",
            plane="",
            extra_plane="",
            execution_target="",
            options={},
            ctx=None,
            assistant_id="asst_xyz",
        )
        request = _to_run_request(carrier)
        assert request.assistant_id == "asst_xyz"


class TestValidateAssistantBinding:
    def test_no_binding_returns_none(self) -> None:
        request = _request_with_catalog(None)
        assert _validate_assistant_binding(request, "") is None

    def test_binding_without_catalog_returns_400(self) -> None:
        request = _request_with_catalog(None)
        response = _validate_assistant_binding(request, "asst_x")
        assert response is not None and response.status_code == 400

    def test_unknown_id_returns_404(self, catalog: AssistantCatalogImpl) -> None:
        request = _request_with_catalog(catalog)
        response = _validate_assistant_binding(request, "asst_missing")
        assert response is not None and response.status_code == 404

    def test_valid_id_returns_none(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(CreateAssistantRequest(name="合法助理"))
        request = _request_with_catalog(catalog)
        assert _validate_assistant_binding(request, handle.assistant_id) is None

    def test_digest_mismatch_returns_409(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(CreateAssistantRequest(name="篡改目标"))
        soul = Path(handle.home_path) / "SOUL.md"
        soul.write_text(soul.read_text(encoding="utf-8") + "\n# tampered", encoding="utf-8")
        request = _request_with_catalog(catalog)
        response = _validate_assistant_binding(request, handle.assistant_id)
        assert response is not None and response.status_code == 409


class TestRunAmbitAssistantId:
    def test_default_empty(self) -> None:
        assert current_assistant_id() == ""

    def test_bound_ambit_exposes_assistant_id(self) -> None:
        ambit = RunAmbit(assistant_id="asst_bound")
        with bind_run_ambit(ambit):
            assert current_assistant_id() == "asst_bound"
        assert current_assistant_id() == ""


class TestRunSessionRequest:
    def test_carries_assistant_id(self) -> None:
        request = RunSessionRequest(question="q", user_text="q", assistant_id="asst_s")
        assert request.assistant_id == "asst_s"

    def test_default_empty(self) -> None:
        request = RunSessionRequest(question="q", user_text="q")
        assert request.assistant_id == ""
