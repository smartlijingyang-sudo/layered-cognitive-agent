"""Creator §13.3 单 session 端到端闭环（mock LLM + in-memory journal）。

Plan step 2 — e2e test：
- 按 v3 §13.3.4 流程编排：think → ``cordis_control.inspect`` → think →
  ``tool_file_write``（写到 preset plugin 路径）→ think →
  ``cordis_control.mount`` → 在同一 session 内调用新挂载的工具断言
  返回值正确；穿插一条「故意 grant 缺失」的 mount 调用，断言拒绝事件。
- 捕获 journal 到 ``{SCRATCH}/cordis_creator_run.jsonl``。

设计原则（NO TEST THEATER）：
- 直接驱动真实 Tool / Composer 链（不是 stub 替代品）；
- 失败路径用 grant 子集精确断言拒绝原因（不混用 happy / fail 路径）；
- journal 走 in-memory MemoryJournal + 测试结束 dump 到 ``{SCRATCH}``，
  与 ``lca-ops trace`` 等价的可机读审计序列留待
  ``test_cordis_creator_audit_log``。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from lca.contracts.mechanisms.composition import (
    ComposerErrorCode,
)
from lca.contracts.models.observability.journal import (
    PluginMounted,
    PluginMountRejected,
)
from lca.layer0_infra.observability.facade import BoundObservability, bind_backends
from lca.layer0_infra.observability.journal_backend import MemoryJournal
from lca.layer4_app.preset_authoring import PresetAuthoring
from lca.plugins.providers.composition_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.tools.cordis_control import build_cordis_control_tool

# 测试隔离：避免 preset 写到用户真实 ~/.agent-presets
SCRATCH = Path(__file__).resolve().parent / ".scratch_cordis_creator"
SCRATCH.mkdir(exist_ok=True)


@contextmanager
def bind_journal():
    """在 ambient BoundObservability 上绑定一个 in-memory journal。

    Tests 必须在 ``with bind_journal() as journal:`` 块内调用 record(...)，
    否则 record() 会因 ambient 未绑定而 no-op（journal 为空）。
    """
    journal = MemoryJournal()
    with bind_backends(BoundObservability(journal=journal)):
        yield journal


def _dump_journal(journal: MemoryJournal, path: Path) -> None:
    """把 in-memory journal 序列化为 ``journal.v1`` jsonl，便于审计 / 回放。"""
    from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

    path.write_text(
        "\n".join(
            json.dumps(stamped_to_record(s), ensure_ascii=False) for s in journal.store.events
        ),
        encoding="utf-8",
    )


def _plugin_source(name: str, capability: str = "tool_fs.read") -> str:
    """生成最小可挂载的 plugin 源文本（PR12 自带 plugin_meta）。"""
    return f'''
plugin_meta = {{
    "name": "{name}",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["{capability}"],
    "side_effects": "none",
    "policy_class": "execute",
    "test_suite": "tests/test_{name}.py",
}}


def factory():
    """返回调用函数：参数 text（字符串），返回 sorted keys。"""
    import json

    def _keys(text):
        return sorted(json.loads(text).keys())

    return _keys
'''


def _plugin_source_no_meta(name: str) -> str:
    """故意缺 ``plugin_meta`` 的 plugin 源（用于 PR12 闸测试）。"""
    return """
def factory():
    return "ok"
"""


def _build_tool(composer: CordisComposer, preset_root: Path, *, caller_grant: tuple[str, ...]):
    return build_cordis_control_tool(
        composer=composer,
        caller_grant=caller_grant,
        actor_role="cordis-creator",
        preset_root=preset_root,
    )


def _new_composer() -> CordisComposer:
    from cordis import Context

    ctx = Context()
    return CordisComposer(ctx, invariant_checker=build_default_invariant_checker())


# 每个 test 用独立 preset 子目录（隔离 + 可观测）
def _preset_root(name: str) -> Path:
    p = SCRATCH / f"preset_{name}"
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def full_grant() -> tuple[str, ...]:
    """creator happy path 的完整 caller_grant。"""
    return (
        "cordis_control.inspect",
        "cordis_control.mount",
        "cordis_control.unmount",
        "cordis_control.publish",
        "tool_fs.read",
        "tool_fs.write",
    )


class TestCordisCreatorEnd2End:
    """单 session 闭环：mock LLM（脚本化决策序列）+ 真实 Tool / Composer。"""

    @pytest.mark.asyncio
    async def test_full_loop_creates_plugin_and_invokes_it(self, full_grant) -> None:
        preset_root = _preset_root("happy")
        with bind_journal() as journal:
            composer = _new_composer()
            tool = _build_tool(composer, preset_root, caller_grant=full_grant)

            # Step 1 —— think → use_tool(cordis_control, action=inspect)
            r1 = await tool.execute({"action": "inspect"})
            assert r1.success, f"inspect 失败：{r1.error}"
            assert r1.payload["mounted_count"] == 0

            # Step 2 —— 把 plugin 源写到 preset 目录（Step 5 of §13.3.4 之前的写文件动作）
            plugin_path = preset_root / "json_keys.py"
            plugin_path.write_text(_plugin_source("json_keys"), encoding="utf-8")

            # Step 3 —— think → use_tool(cordis_control, action=mount, name=json_keys, path=...)
            r2 = await tool.execute(
                {
                    "action": "mount",
                    "name": "json_keys",
                    "path": str(plugin_path),
                }
            )
            assert r2.success, f"mount 失败：{r2.error}"
            assert r2.payload["plugin_name"] == "json_keys"
            assert "tool_fs.read" in r2.payload["capabilities"]
            assert "tool_fs.read" in r2.payload["capability_grant"]
            assert r2.payload["preset_layout"]["bundle_path"] == "bundle.yaml"
            assert r2.payload["preset_layout"]["plugin_path"] == "plugins/json_keys.py"
            assert r2.payload["publish_error"] is None

            # Step 4 —— 同一 session 调用新挂载的工具
            instance = composer._ctx.own_bindings.get("plugin:json_keys")
            assert instance is not None, "plugin 未注入 cordis Context"
            keys_fn = instance
            result = keys_fn('{"foo": 1, "bar": 2, "baz": 3}')
            assert result == ["bar", "baz", "foo"]

            # Step 5 —— 落 preset 校验
            assert PresetAuthoring.list_visible_presets(root=preset_root) == ("json_keys",)

            _dump_journal(journal, SCRATCH / "cordis_creator_run.jsonl")

    @pytest.mark.asyncio
    async def test_mount_with_insufficient_grant_rejected(self) -> None:
        preset_root = _preset_root("insufficient_grant")
        with bind_journal() as journal:
            composer = _new_composer()

            plugin_path = preset_root / "high_cap.py"
            plugin_path.write_text(
                _plugin_source("high_cap", capability="cordis_control.publish"),
                encoding="utf-8",
            )

            # grant ⊃ tool_fs.read 但缺 cordis_control.publish → 拒绝
            tool = _build_tool(
                composer,
                preset_root,
                caller_grant=("tool_fs.read",),  # 故意缺 publish
            )
            r = await tool.execute(
                {
                    "action": "mount",
                    "name": "high_cap",
                    "path": str(plugin_path),
                }
            )
            assert not r.success
            assert r.error.startswith(ComposerErrorCode.CAPABILITY_GRANT_EXCEEDED.value)

            # journal 必须落 PluginMountRejected
            rejected = [
                s
                for s in journal.store.events
                if isinstance(s.event, PluginMountRejected) and s.event.plugin_name == "high_cap"
            ]
            assert len(rejected) == 1, f"PluginMountRejected 未落：events={journal.store.events}"
            ev = rejected[0].event
            assert ev.reason_code == ComposerErrorCode.CAPABILITY_GRANT_EXCEEDED.value
            assert "tool_fs.read" in ev.capability_grant
            assert "cordis_control.publish" in ev.requested_capabilities
            assert ev.plugin_meta_present is True

            # plugin 不能出现在 Context
            assert composer._ctx.own_bindings.get("plugin:high_cap") is None

    @pytest.mark.asyncio
    async def test_mount_with_missing_plugin_meta_rejected(self) -> None:
        preset_root = _preset_root("missing_meta")
        with bind_journal() as journal:
            composer = _new_composer()

            plugin_path = preset_root / "no_meta.py"
            plugin_path.write_text(_plugin_source_no_meta("no_meta"), encoding="utf-8")

            tool = _build_tool(
                composer,
                preset_root,
                caller_grant=("tool_fs.read", "cordis_control.publish"),
            )
            r = await tool.execute(
                {
                    "action": "mount",
                    "name": "no_meta",
                    "path": str(plugin_path),
                }
            )
            assert not r.success
            assert r.error.startswith(ComposerErrorCode.PLUGIN_META_MISSING.value)

            rejected = [
                s
                for s in journal.store.events
                if isinstance(s.event, PluginMountRejected) and s.event.plugin_name == "no_meta"
            ]
            assert len(rejected) == 1, f"PluginMountRejected 未落：events={journal.store.events}"
            assert rejected[0].event.reason_code == ComposerErrorCode.PLUGIN_META_MISSING.value
            assert rejected[0].event.plugin_meta_present is False

    @pytest.mark.asyncio
    async def test_unmount_nonexistent_rejected(self) -> None:
        preset_root = _preset_root("ghost")
        with bind_journal() as journal:
            composer = _new_composer()
            tool = _build_tool(
                composer,
                preset_root,
                caller_grant=("cordis_control.unmount",),
            )
            r = await tool.execute({"action": "unmount", "name": "ghost"})
            assert not r.success
            assert r.error.startswith(ComposerErrorCode.NOT_MOUNTED.value)

            # unmount 失败只落 RuntimeObserved FAILED，不落 PluginUnmounted
            ev_types = {s.event_type for s in journal.store.events}
            assert "PluginUnmounted" not in ev_types

    @pytest.mark.asyncio
    async def test_audit_chain_has_all_event_classes(self, full_grant) -> None:
        """一次 happy mount + inspect 应覆盖全部 Creator 事件类型。"""
        preset_root = _preset_root("audit_chain")
        with bind_journal() as journal:
            composer = _new_composer()
            tool = _build_tool(composer, preset_root, caller_grant=full_grant)

            plugin_path = preset_root / "json_keys.py"
            plugin_path.write_text(_plugin_source("json_keys"), encoding="utf-8")

            await tool.execute({"action": "inspect"})
            await tool.execute({"action": "mount", "name": "json_keys", "path": str(plugin_path)})

            ev_types = {s.event_type for s in journal.store.events}
            assert "PluginInspected" in ev_types
            assert "PluginAuthored" in ev_types
            assert "PluginMounted" in ev_types
            assert "PresetPublished" in ev_types
            assert "RuntimeObserved" in ev_types
            assert "PluginMountRejected" not in ev_types

            mounted_events = [s for s in journal.store.events if isinstance(s.event, PluginMounted)]
            assert len(mounted_events) == 1
            ev = mounted_events[0].event
            assert ev.actor_role == "cordis-creator"
            assert "tool_fs.read" in ev.capabilities
            assert "tool_fs.read" in ev.capability_grant
            assert ev.meta["name"] == "json_keys"
            assert ev.meta["policy_class"] == "execute"
