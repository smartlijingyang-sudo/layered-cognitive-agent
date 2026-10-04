"""Connector 授权卡片端到端（Zero Model URL Exposure / INV-CAP-05 / ADR-0280）。

链路：
  composioConnect tool → ConnectorAuthIntentVault.create_intent()（auth_url 入库，
  只返回 cai_xxx 票据）→ format_connector_auth_widget(intent_id=...)
  → ``[widget:connector_auth?appName=..&intentId=cai_xxx]``
  → 模型原样输出标签（严禁裸 URL）→ 前端 patch 解析标签
  → <ConnectorAuthCard intentId/> → 点击时 POST
  ``/lca-api/composio/auth-intents/{intentId}/resolve`` 兑换真实 URL。

断言：
- tag 含 intentId，不含裸 http URL（URL 永不经过模型/前端文本）
- vault 往返：create → resolve 拿回原 URL；跨 user 拒绝；消费标记；过期语义
- 前端 ConnectorAuthCard.tsx 静态断言：intentId prop、resolve 端点、三态机
- 收敛（缺口一）：gmail CLI _handle_status 已迁到 vault intent 路径；
  test_no_bare_auth_url_callers_in_production 用 AST 断言 lca/ 生产代码
  不再向 format_connector_auth_widget 传 auth_url（formatter 形参仅为
  旧持久化标签保留）。
- 前端 fail-closed 静态断言：resolvedUrl 不再从 http authUrl 预填；
  handleStartAuth 无 http 回退；按钮禁用态只看 intentId/resolvedUrl。

不动：不调真实 Composio/OAuth；不启动浏览器/前端 dev server。
前端渲染断言为静态源码分析（252 无 node/jsdom 渲染链），诚实降级。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qsl

from lca.infrastructure.connectors.core.intent_vault import (
    ConnectorAuthIntentVault,
    set_default_intent_vault,
)
from lca.infrastructure.connectors.core.state import format_connector_auth_widget
from lca.infrastructure.connectors.core.vault import ConnectorVault
from lca.infrastructure.connectors.gmail.cli import GmailConnectorCLI

REPO_ROOT = Path(__file__).resolve().parents[2]
TSX = REPO_ROOT / "deploy/lobehub/patches/ui/ConnectorAuthCard.tsx"
PATCH_PY = REPO_ROOT / "deploy/lobehub/patches/ui/connector_auth_card.py"

# 前端 patch 用的标签正则（与 connector_auth_card.py 内嵌 pattern 同构）
_WIDGET_RE = re.compile(r"\[widget:connector_auth\?([^\]]+)\]")

FAKE_AUTH_URL = "https://oauth.example.com/authorize?token=TOKEN123&sig=abc"


def _make_vault() -> ConnectorAuthIntentVault:
    return ConnectorAuthIntentVault()


def test_widget_tag_carries_intent_id_not_raw_url() -> None:
    tag = format_connector_auth_widget(
        app_name="Gmail", intent_id="cai_test123", connection_id="conn_1"
    )
    assert tag.startswith("[widget:connector_auth?")
    assert "intentId=cai_test123" in tag
    assert "http" not in tag
    assert "authUrl" not in tag


def test_vault_create_returns_opaque_ticket() -> None:
    vault = _make_vault()
    intent_id = vault.create_intent(
        service="gmail",
        app_name="Gmail",
        auth_url=FAKE_AUTH_URL,
        connection_id="conn_1",
        user_id="u1",
    )
    assert intent_id.startswith("cai_")
    assert FAKE_AUTH_URL not in intent_id


def test_vault_resolve_roundtrip() -> None:
    vault = _make_vault()
    intent_id = vault.create_intent(
        service="gmail",
        app_name="Gmail",
        auth_url=FAKE_AUTH_URL,
        connection_id="conn_1",
        user_id="u1",
    )
    intent = vault.resolve_intent(intent_id, user_id="u1")
    assert intent is not None
    assert intent.auth_url == FAKE_AUTH_URL
    assert intent.consumed is True


def test_vault_rejects_wrong_user() -> None:
    vault = _make_vault()
    intent_id = vault.create_intent(
        service="gmail",
        app_name="Gmail",
        auth_url=FAKE_AUTH_URL,
        connection_id="conn_1",
        user_id="u1",
    )
    assert vault.resolve_intent(intent_id, user_id="intruder") is None
    # 原用户仍可解析（隔离检查不污染票据）
    assert vault.resolve_intent(intent_id, user_id="u1") is not None


def test_vault_expiry_semantics() -> None:
    vault = _make_vault()
    intent_id = vault.create_intent(
        service="gmail",
        app_name="Gmail",
        auth_url=FAKE_AUTH_URL,
        connection_id="conn_1",
        user_id="u1",
        ttl_seconds=3600,
    )
    intent = vault.resolve_intent(intent_id, user_id="u1")
    assert intent is not None
    assert intent.is_expired(intent.expires_at - 1) is False
    assert intent.is_expired(intent.expires_at + 1) is True


def test_end_to_end_no_url_leak_from_vault_to_tag() -> None:
    """核心契约：真实 URL 进 vault，tag 里只有票据，密钥零泄漏。"""
    vault = _make_vault()
    intent_id = vault.create_intent(
        service="gmail",
        app_name="Gmail",
        auth_url=FAKE_AUTH_URL,
        connection_id="conn_1",
        user_id="u1",
    )
    tag = format_connector_auth_widget(
        app_name="Gmail", intent_id=intent_id, auth_url="", connection_id="conn_1"
    )
    # 密钥不出 vault
    assert FAKE_AUTH_URL not in tag
    assert "TOKEN123" not in tag
    # 前端能解析出 intentId（用 patch 同构正则）
    match = _WIDGET_RE.search(tag)
    assert match is not None
    params = dict(parse_qsl(match.group(1)))
    assert params.get("intentId") == intent_id
    assert "authUrl" not in params


def test_frontend_card_resolves_intent_id_async() -> None:
    """静态断言（降级）：组件走 intentId → 异步 resolve → 三态机。"""
    src = TSX.read_text(encoding="utf-8")
    assert "intentId" in src
    assert "/lca-api/composio/auth-intents/" in src
    assert "/resolve" in src
    for state in ("pending", "authorizing", "connected"):
        assert state in src


def test_frontend_patch_mounts_widget_parser() -> None:
    """静态断言（降级）：patch 把 [widget:connector_auth?...] 解析挂进 Assistant。"""
    src = PATCH_PY.read_text(encoding="utf-8")
    assert "[widget:connector_auth" in src
    assert "ConnectorAuthCard" in src


def test_legacy_formatter_branch_retained_for_old_persisted_tags() -> None:
    """formatter 的 auth_url 分支仅为旧持久化标签保留。

    缺口一已收敛：生产调用方不再传 auth_url（见
    test_no_bare_auth_url_callers_in_production）。此测试锁定 formatter
    对历史标签的兼容能力，而非生产行为；前端对这类标签渲染禁用态。
    """
    tag = format_connector_auth_widget(
        app_name="Gmail", auth_url=FAKE_AUTH_URL, connection_id="conn_1"
    )
    assert "authUrl=" in tag
    assert "TOKEN123" in tag


def test_gmail_status_path_emits_intent_not_url(tmp_path) -> None:
    """缺口一收敛：gmail status 全链路走 vault，widget/返回体无裸 URL。"""
    set_default_intent_vault(ConnectorAuthIntentVault())
    cli = GmailConnectorCLI(vault=ConnectorVault(user_id="e2e_user", lca_home=tmp_path))
    res = cli.execute(["status"])
    assert res["status"] == "not_connected"
    assert "authUrl" not in res
    intent_id = res["intentId"]
    assert intent_id.startswith("cai_")
    tag = res["widget"]
    assert f"intentId={intent_id}" in tag
    assert "authUrl" not in tag
    assert "http" not in tag
    # 前端 patch 正则能解析出 intentId
    match = _WIDGET_RE.search(tag)
    assert match is not None
    params = dict(parse_qsl(match.group(1)))
    assert params.get("intentId") == intent_id


def test_no_bare_auth_url_callers_in_production() -> None:
    """契约：lca/ 生产代码不得再向 format_connector_auth_widget 传 auth_url。

    用 AST 精确匹配调用点（非文本 grep，避免误报）；formatter 自身的
    形参定义是 FunctionDef 而非 Call，不会被计入。
    """
    import ast

    lca_root = REPO_ROOT / "lca"
    violations: list[str] = []
    for py_file in sorted(lca_root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        # utf-8-sig：个别文件带 BOM，直接 ast.parse 会报 U+FEFF
        tree = ast.parse(py_file.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "format_connector_auth_widget":
                continue
            for kw in node.keywords:
                if kw.arg == "auth_url":
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}:{node.lineno}")
    assert not violations, f"bare auth_url callers remain: {violations}"


def test_frontend_fail_closed_no_http_prefill() -> None:
    """静态断言：resolvedUrl 不再从 http authUrl 预填。"""
    src = TSX.read_text(encoding="utf-8")
    assert "authUrl && authUrl.startsWith('http') ? authUrl : undefined" not in src


def test_frontend_fail_closed_no_http_fallback() -> None:
    """静态断言：handleStartAuth 内无 http 回退直接打开。"""
    src = TSX.read_text(encoding="utf-8")
    assert "targetUrl = authUrl" not in src


def test_frontend_fail_closed_intent_only_credential() -> None:
    """静态断言：唯一凭据是 effectiveIntentId；按钮禁用态 fail-closed。"""
    src = TSX.read_text(encoding="utf-8")
    assert "effectiveIntentId" in src
    assert "disabled={!effectiveIntentId && !resolvedUrl}" in src
    assert "@deprecated" in src
