"""End-to-End Scenario Test for Capability Intent & Zero Model URL Exposure (ADR-0280 / INV-CAP-01 ~ INV-CAP-06).

Validates the full architectural lifecycle:
1. Tool execution (composioConnect / PreExecutionGuard) generates capability intent.
2. Observation & payload contain ZERO http/https authorization URLs (INV-CAP-01).
3. Vault manages intent lifecycle with 300s TTL & multi-tenant boundary (INV-CAP-02).
4. Gateway deterministically injects widget markup if model omits it (INV-CAP-04).
5. Out-of-band resolve endpoint exchanges intent for real URL (INV-CAP-03).
6. Multi-tenant separation and expiration return 403 / 410 (INV-CAP-02).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.infrastructure.connectors.core.intent_vault import get_default_intent_vault
from lca.infrastructure.integrations.composio.service.service import ComposioConnection
from lca.infrastructure.tools.composio import ComposioManagementExecutor
from lca.plugins.transport.webserver.routes_1.routes_composio import ROUTE_SPECS
from lca.runtime.session.run_session_writer import RunSessionWriter


@dataclass
class _StoredEvent:
    type: str
    seq: int
    data: dict[str, Any]
    time: float = 0.0
    surface_op: Any | None = None
    source_event_seqs: tuple[int, ...] | None = None


@dataclass
class _InMemorySession:
    events: list[Any] = field(default_factory=list)
    next_seq: int = 0

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> Any:
        event = _StoredEvent(
            type=event_type,
            seq=self.next_seq,
            data=dict(data),
            surface_op=surface_op,
            source_event_seqs=source_event_seqs,
        )
        self.next_seq += 1
        self.events.append(event)
        return event

    def snapshot_events(self) -> tuple[Any, ...]:
        return tuple(self.events)

    @property
    def id(self) -> str:
        return "sess_e2e_cap_intent"


@pytest.fixture
def test_client():
    routes = [
        Route(spec.path, spec.handler, methods=list(spec.methods))
        for spec in ROUTE_SPECS
    ]
    app = Starlette(routes=routes)
    return TestClient(app)


@pytest.mark.asyncio
async def test_connector_capability_intent_full_e2e_flow(monkeypatch, test_client):
    """INV-CAP-01 ~ INV-CAP-06: Full End-to-End validation of zero model exposure & async resolve."""
    vault = get_default_intent_vault()
    vault._intents.clear()

    # Step 1: Mock Composio client initiation
    real_auth_url = "https://connect.composio.dev/link/lk_prod_secure_oauth_xyz123"
    fake_conn = ComposioConnection(
        identifier="google-drive",
        app_slug="google-drive",
        label="Google Drive",
        connected_account_id="conn_account_xyz",
        auth_config_id="auth_cfg_123",
        user_id="user_alice",
        status="PENDING",
        redirect_url=real_auth_url,
    )
    mock_integration = MagicMock()
    mock_integration.get_connection.return_value = None
    mock_integration.create_connection = AsyncMock(return_value=fake_conn)
    mock_integration.user_id = "user_alice"

    executor = ComposioManagementExecutor(mock_integration)

    # 1. 执行连接工具: 产生 capability intent
    obs = await executor.composioConnect({"service": "google-drive"})
    assert obs.success is True

    payload = obs.payload
    # 验证 INV-CAP-01 (零 URL 泄漏): Observation 内容绝不含真实 URL
    assert "https://connect.composio.dev" not in payload["text"]
    assert "http://" not in payload["text"] and "https://" not in payload["text"]
    assert "redirect_url" not in payload or not payload["redirect_url"]

    # 验证工具返回 intent_id 与 widget 挂载卡片标签
    intent_id = payload["intent_id"]
    assert intent_id.startswith("cai_")
    assert f"intentId={intent_id}" in payload["text"]
    assert "[widget:connector_auth" in payload["text"]

    # Step 2: 验证 INV-CAP-02 (Vault 状态与生命周期)
    intent = vault._intents.get(intent_id)
    assert intent is not None
    assert intent.auth_url == real_auth_url
    assert intent.app_name == "Google Drive"
    assert intent.user_id == "user_alice"
    assert intent.consumed is False

    # Step 3: 模拟认知循环与网关保底挂载 (INV-CAP-04)
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)

    # 写入工具执行结果事实
    writer.append_tool_result(
        turn=1,
        step=1,
        call_id="call_connect_1",
        content=payload["text"],
        error=None,
        meta={"tool_name": "composioConnect"},
    )

    # 模拟大模型输出纯文本，完全漏写了 [widget:connector_auth]
    model_output_text = "我已经为您发起了 Google Drive 授权，请通过界面操作完成连接。"
    writer.append_assistant_message(
        turn=1,
        step=2,
        role="assistant",
        content=model_output_text,
        tool_calls=None,
        usage=None,
    )

    # 验证网关层确定性保底：Session 中的最终 assistant 消息 100% 自动补齐了 widget 标签
    asst_event = next(e for e in session.snapshot_events() if e.type == "surface/assistant_message")
    saved_msg = asst_event.data["content"]
    assert f"[widget:connector_auth?intentId={intent_id}" in saved_msg
    assert "appName=Google+Drive" in saved_msg

    # Step 4: 模拟前端带外异步兑换真实 URL (INV-CAP-03)
    # Alice 兑换其自己的 intent -> 200 OK 并获取真实授权链接
    resolve_res = test_client.post(
        f"/composio/auth-intents/{intent_id}/resolve",
        headers={"X-User-ID": "user_alice"},
    )
    assert resolve_res.status_code == 200
    res_data = resolve_res.json()
    assert res_data["authUrl"] == real_auth_url
    assert res_data["appName"] == "Google Drive"
    assert res_data["connectionId"] == "conn_account_xyz"

    # 验证消费标记已更新
    resolved_intent = vault._intents.get(intent_id)
    assert resolved_intent.consumed is True

    # Step 5: 验证跨用户多租户越权隔离 (INV-CAP-02: 返回 404 防枚举)
    # 创建一个属于 Bob 的新 intent
    bob_intent_id = vault.create_intent(
        service="gmail",
        app_name="gmail",
        auth_url="https://connect.composio.dev/link/lk_bob_only",
        connection_id="conn_bob_123",
        user_id="user_bob",
    )
    # Alice 试图访问 Bob 的 intent -> 404
    cross_res = test_client.post(
        f"/composio/auth-intents/{bob_intent_id}/resolve",
        headers={"X-User-ID": "user_alice"},
    )
    assert cross_res.status_code == 404

    # Step 6: 验证超时失效防线 (INV-CAP-02 / 404 after expiration)
    expired_intent_id = vault.create_intent(
        service="slack",
        app_name="slack",
        auth_url="https://connect.composio.dev/link/lk_expired",
        connection_id="conn_slack_123",
        user_id="user_alice",
        ttl_seconds=0.1,  # 短 TTL
    )
    await asyncio.sleep(0.15)
    expire_res = test_client.post(
        f"/composio/auth-intents/{expired_intent_id}/resolve",
        headers={"X-User-ID": "user_alice"},
    )
    assert expire_res.status_code == 404

    # Step 7: 验证不存在的 intent 返回 404
    nonexist_res = test_client.post(
        "/composio/auth-intents/cai_nonexistent/resolve",
        headers={"X-User-ID": "user_alice"},
    )
    assert nonexist_res.status_code == 404
