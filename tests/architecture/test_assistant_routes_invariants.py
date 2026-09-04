"""Assistant / AssistantRoutes architecture invariants —— ADR-0187 §5。

不变量（ADR-0187 §5 PR-5 子集）:

- I-A1 web-standard 回归: ``web-standard`` profile 不挂 ``assistant-runtime``;
  ``lca.plugins.transport.webserver.routes_assistants`` 仅在引入
  ``assistant-runtime`` bundle 的 profile 才被装配。
- I-A9 不新增顶层 loop 类: ``lca`` 树内不允许出现
  ``AssistantRuntime`` / ``AssistantLoop`` / 平行 ``compile_assistant_plan()``
  命名（ADR-0187 §6 删除条件，§8 拒收信号）。
- I-A10 默认 profile 不污染: ``web-standard`` 解析结果不得包含
  ``lca.plugins.transport.webserver.routes_assistants``。
- I-A11 EP 描述符白名单: 助理域 EP 词表 = 12 项闭集；本 PR-5 路由
  模块自身不直接发 EP（catalog 才发，PR-3），但路由可消费的 catalog 调用
  须走 ``assistant.catalog`` capability（路由 ``requires`` 不含 catalog，
  仅运行时探查 —— 契约层不在 PR-5 强制 EP 描述符消费）。
- I-A12 jobs 必经 0093 WorkQueue（PR-8 范畴；本测试仅占位声明）。
- I-A13 记忆面写入不参与 digest、不触发 ``revision_seq``（PR-3+ 范畴；
  本测试仅占位声明，不在本 PR 强制）。

长期回归锁；delete-when:N/A。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    """Run ripgrep; empty list = no matches."""
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                pattern,
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    out: list[str] = []
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                rel = path.relative_to(_REPO_ROOT)
                out.append(f"{rel}:{lineno}:{line}")
    return out


# ── I-A1 / I-A10: web-standard 不引入 assistant routes ─────────────────────


class TestIAssistantRoutesProfileIsolation:
    """``web-standard`` profile 解析结果不得包含 assistant routes plugin。

    路由仅在显式 include ``assistant-runtime`` bundle 的 profile 才装载
    （PR-4 范畴）。任何把 ``lca.plugins.transport.webserver.routes_assistants``
    注入 ``web-standard`` 的改动都会破坏 I-A10 与 P6 存量零打扰。
    """

    def test_web_standard_does_not_resolve_routes_assistants(self) -> None:
        from lca.harness.profile.resolve import resolve_profile

        resolved = resolve_profile("profiles/web-standard.yaml")
        ids = {plugin.id for plugin in resolved.plugins}
        assert "lca.plugins.transport.webserver.routes_assistants" not in ids, (
            "I-A10 violated: routes_assistants must not appear in web-standard"
        )

    def test_web_standard_does_not_resolve_assistant_catalog(self) -> None:
        """Catalog plugin 来自 ``assistant-runtime`` bundle（PR-3）；
        ``web-standard`` 不装载，避免 I-A1 / P6 存量零打扰破坏。"""
        from lca.harness.profile.resolve import resolve_profile

        resolved = resolve_profile("profiles/web-standard.yaml")
        ids = {plugin.id for plugin in resolved.plugins}
        assert "lca.plugins.assistant.catalog" not in ids
        assert "lca.plugins.assistant.bootstrap" not in ids
        assert "lca.plugins.assistant.workspace" not in ids
        assert "lca.plugins.assistant.skill_overlay" not in ids
        assert "lca.plugins.assistant.jobs" not in ids
        assert "lca.plugins.assistant.evolve" not in ids


# ── I-A9: 不新增顶层 loop 类（PR-5 delete-when 守门）─────────────────────────


class TestINoAssistantLoopClass:
    """I-A9（ADR-0187 §5）:不新增顶层 loop 类。

    本类守住 §6 删除条件 + §8 拒收信号 1：
    ``AssistantRuntime`` / ``AssistantLoop`` / ``AssistantCognitiveLoop``
    / 平行 ``compile_assistant_plan()`` 在 ``lca`` 树内不得出现。
    """

    @pytest.mark.parametrize(
        "forbidden",
        (
            "AssistantRuntime",
            "AssistantLoop",
            "AssistantCognitiveLoop",
            "compile_assistant_plan",
        ),
    )
    def test_forbidden_identifier_absent(self, forbidden: str) -> None:
        """``lca/`` + ``lca_kernel/`` 内不得出现禁止命名。

        实测 0 命中；任何新增都会被本测试拒绝（CI 守护 §8 拒收信号 1）。
        """
        lca_root = _REPO_ROOT / "lca"
        kernel_root = _REPO_ROOT / "lca_kernel"
        hits_lca = _rg(forbidden, lca_root)
        hits_kernel = _rg(forbidden, kernel_root)
        # ``lca_kernel/`` 不在本 ADR 范围内，但保留扫描以发现跨包外溢。
        all_hits = hits_lca + hits_kernel
        assert all_hits == [], (
            f"I-A9 violated: forbidden identifier {forbidden!r} found:\n" + "\n".join(all_hits)
        )


# ── I-A11: routes_assistants 模块不直接发 EP ──────────────────────────────────


class TestIAssistantRoutesEpSurface:
    """routes_assistants 自身不直接发射 assistant.* EP。

    EP 发射是 catalog 插件的责任（PR-3）；PR-5 的路由只消费 catalog
    调用结果（fail-closed 4xx）。本测试锁定 routes_assistants 模块内
    不出现 cordis publish / EventBus publish / 直接 EP 发射 helper 调用。
    """

    def test_routes_assistants_does_not_emit_cordis_events(self) -> None:
        """``routes_assistants.py`` 不得调 cordis EventBus.publish /
        publish_event 等直接发射面（EP 发射是 catalog 责任，PR-3）。
        """
        target = _REPO_ROOT / "lca" / "plugins" / "transport" / "webserver" / "routes_assistants.py"
        text = target.read_text(encoding="utf-8")
        # 显式禁词（按需追加；EP 发射面 ≠ cordis 事件总线）
        forbidden = (
            "EventBus.publish",
            ".publish_event(",
            "publish_assistant_",
            "emit_assistant_",
        )
        for token in forbidden:
            assert token not in text, (
                f"I-A11 violated: routes_assistants contains {token!r}; "
                "EP emission belongs to the catalog plugin (PR-3)."
            )

    def test_routes_assistants_does_not_strip_event_descriptor_layer(self) -> None:
        """路由模块不得修改 EP 描述符 registry / cordis 事件表 —— 注册
        面只由 ``event_descriptors_data.build_default_registry`` 在 boot
        一次性导入（PR-2 已落）。"""
        target = _REPO_ROOT / "lca" / "plugins" / "transport" / "webserver" / "routes_assistants.py"
        text = target.read_text(encoding="utf-8")
        forbidden = (
            "register_event_descriptor",
            "register_assistant",
            "ASSISTANT_EVENT_DESCRIPTORS",
            "ASSISTANT_EVENT_POINTS",
        )
        for token in forbidden:
            assert token not in text, (
                f"I-A11 violated: routes_assistants touches EP registration "
                f"surface via {token!r}; this belongs to PR-3 catalog."
            )


# ── I-A12 / I-A13 占位声明（PR-8 / PR-3+ 范畴）───────────────────────────────


class TestIAssistantInvariantsPlaceholder:
    """占位声明：I-A12 / I-A13 由后续 PR 的测试守护（jobs 注册走 0093；
    记忆面写入不参与 manifest digest）。本测试仅声明占位，避免后人
    误以为 PR-5 已经落 I-A12 / I-A13 守护。

    PR-5 delete-when: PR-3 (catalog + memory seam test) 与 PR-8 (jobs
    arch test) 合入后由对应测试守护；本类保留为契约溯源锚点。
    """

    def test_i_a12_placeholder(self) -> None:
        pytest.skip(
            "I-A12 owned by PR-8 (jobs registry arch test); PR-5 routes_assistants 不创建 jobs 插件"
        )

    def test_i_a13_placeholder(self) -> None:
        pytest.skip(
            "I-A13 owned by PR-3+ (memory seam agent-scope test); "
            "PR-5 路由不写记忆面（catalog 写 SOUL 等配置面，PR-3）"
        )


# ── routes_assistants 装配契约 ──────────────────────────────────────────────


class TestIAssistantRoutesBootContract:
    """routes_assistants 必须满足 PR-5 boot 契约。

    - 插件 module id 对齐仓内模板 ``lca.plugins.<dir>.<name>``（§3 D6）；
    - 唯一 requires = ``route_registry``（catalog 在运行时探查，I-A10 兼容）；
    - 不声明 filesystem / network 等 effect class（REST 路由不写文件）。
    """

    def test_module_id_matches_convention(self) -> None:
        from lca.plugins.transport.webserver.routes_assistants import setup as plugin

        defn = plugin._lca_definition
        assert defn.id == "lca.plugins.transport.webserver.routes_assistants"

    def test_requires_is_only_route_registry(self) -> None:
        from lca.plugins.transport.webserver.routes_assistants import setup as plugin

        defn = plugin._lca_definition
        assert set(defn.required_capability_keys) == {"route_registry"}

    def test_plugin_does_not_declare_filesystem_or_network_effects(self) -> None:
        from lca.plugins.transport.webserver.routes_assistants import setup as plugin

        defn = plugin._lca_definition
        effect_values = set(getattr(defn, "effects", set()) or set())
        # REST 路由不写文件、不发网络（catalog 才发网络 + 写 FS，PR-3）。
        # effects 字段是 frozenset[str]（enum 值集合）。
        assert "filesystem" not in effect_values
        assert "network" not in effect_values
