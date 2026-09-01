"""``POST /runs`` command decoding (ADR-0100 mode vs model alias).

ADR-0163 决策 2:``llm_status(ctx)`` 调用从 handler 中删除,readiness
由 routes plugin ``RouteSpec.requires=("llm_resolver",)`` 在 boot
期强制。本测试用 scripted ``RunPort`` 注入,默认视为 capability 已
挂载;只验证 payload-shape 与 mode/model 别名解析。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import create_run
from lca.plugins.transport.webserver.handlers.runs.ingest.ingress import LobeHubRunInput
from lca.plugins.transport.webserver.handlers.runs.terminal.port import RunReceipt


def _identity_mode(_ctx: object, key: str) -> str:
    return key


def _app(spy: AsyncMock) -> Starlette:
    application = Starlette(routes=[Route("/runs", create_run, methods=["POST"])])
    application.state.ctx = object()
    application.state.file_store = object()
    application.state.run_port = type("Port", (), {"create_and_dispatch": spy})()
    return application


_INPUT = LobeHubRunInput(user_text="hello", question="hello")


def _post_runs(spy: AsyncMock, payload: dict[str, object]) -> object:
    with (
        patch(
            "lca.plugins.transport.webserver.handlers.runs.api.command_endpoints.resolve_profile_mode",
            side_effect=_identity_mode,
        ),
        patch(
            "lca.plugins.transport.webserver.handlers.runs.api.command_endpoints.prepare_run_from_messages",
            new=AsyncMock(return_value=_INPUT),
        ),
    ):
        return TestClient(_app(spy)).post("/runs", json=payload)


def test_post_runs_mode_without_model_resolves_team() -> None:
    spy = AsyncMock(return_value=RunReceipt(run_id="r1", trace_id="t1", accepted=True))
    response = _post_runs(
        spy,
        {"mode": "team", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 202
    request = spy.await_args.args[0]
    assert request.mode == "team"


def test_post_runs_model_alias_still_resolves() -> None:
    spy = AsyncMock(return_value=RunReceipt(run_id="r1", trace_id="t1", accepted=True))
    response = _post_runs(
        spy,
        {"model": "team", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 202
    request = spy.await_args.args[0]
    assert request.mode == "team"


def test_post_runs_mode_wins_over_model() -> None:
    spy = AsyncMock(return_value=RunReceipt(run_id="r1", trace_id="t1", accepted=True))
    response = _post_runs(
        spy,
        {
            "mode": "team",
            "model": "solo",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 202
    request = spy.await_args.args[0]
    assert request.mode == "team"
