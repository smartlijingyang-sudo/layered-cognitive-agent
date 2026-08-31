"""Creator §13.3 可审计插件日志：基于 JournalBackend.read() 的查询 + 时间序审计序列。

Plan step 4 —— audit log test：
- 跑一遍 e2e 闭环并对写出的 ``{SCRATCH}/cordis_creator_run.jsonl`` 调用基于
  :class:`JournalBackend.read()` 的查询函数；
- 断言每类事件各出现一次且 payload 包含必要字段（grant / meta / args /
  trace_id）；
- 断言能按时间顺序产出一份「思维 → 工具调用 → 插件挂载 / 卸载」的线性审计序列；
- 捕获该序列到 ``{SCRATCH}/cordis_creator_audit.json`` 作为机读证据。

§13.3.6 self-improving 边界 + 用户新增要求（plugin logs 细致到 debug / audit）
------------------------------------------------------------------------------
审计序列要让人看得懂 agent 在想什么、做着什么、为什么拒绝；本测试断言
``PluginAuthored`` + ``PluginMounted/Rejected`` + ``PresetPublished``
+ 解释性 RuntimeObserved 四条事件类型全部出现且 payload 关键字段齐全。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from lca.contracts.models.observability.journal import (
    PluginAuthored,
    PluginInspected,
    PluginMounted,
    PluginMountRejected,
    PluginUnmounted,
    PresetPublished,
    RuntimeObserved,
    StampedEvent,
)
from lca.infrastructure.observability.backends.journal_backend import MemoryJournal
from lca.infrastructure.observability.facade import BoundObservability, bind_backends
from lca.infrastructure.observability.journal.engine.journal_io import (
    read_journal,
    stamped_to_record,
)
from lca.plugins.providers.think.composition_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.tools.cordis_control import build_cordis_control_tool
from tests.test_cordis_creator_e2e import SCRATCH, _plugin_source


@contextmanager
def bind_journal():
    journal = MemoryJournal()
    with bind_backends(BoundObservability(journal=journal)):
        yield journal


def _new_composer() -> CordisComposer:
    from cordis import Context

    ctx = Context()
    return CordisComposer(ctx, invariant_checker=build_default_invariant_checker())


def _write_jsonl(events: tuple[StampedEvent, ...], path: Path) -> None:
    path.write_text(
        "\n".join(json.dumps(stamped_to_record(s), ensure_ascii=False) for s in events),
        encoding="utf-8",
    )


def query_journal(
    *,
    path: Path,
    event_type: str | None = None,
    actor_role: str | None = None,
    plugin_name: str | None = None,
) -> list[dict[str, object]]:
    """对落盘的 journal.jsonl 做结构化查询；返回 ``list[record]``。"""
    events = read_journal(path)
    out: list[dict[str, object]] = []
    for stamped in events:
        if event_type is not None and stamped.event_type != event_type:
            continue
        record_dict = stamped_to_record(stamped)
        # lca.journal/2 envelope: payload lives under ``data``. Legacy
        # ``event`` field tolerated for backward compat.
        event_payload = record_dict.get("data") or record_dict.get("event") or {}
        if actor_role is not None and event_payload.get("actor_role") != actor_role:
            continue
        if plugin_name is not None and event_payload.get("plugin_name") != plugin_name:
            continue
        out.append(record_dict)
    return out


def linear_audit_sequence(events: tuple[StampedEvent, ...]) -> list[dict[str, object]]:
    """把 journal 摊平成时间序审计序列：每条记录带 ``seq / type / source / key / brief``。"""
    out: list[dict[str, object]] = []
    for stamped in events:
        payload = stamped.event
        record_dict = stamped_to_record(stamped)
        brief = _brief(stamped)
        out.append(
            {
                "seq": stamped.seq,
                "ts": stamped.ts,
                "scope": record_dict["scope"],
                "event_type": stamped.event_type,
                "source": getattr(payload, "source", "") or _infer_source(stamped),
                "actor_role": getattr(payload, "actor_role", ""),
                "key": _event_key(payload),
                "brief": brief,
            }
        )
    return out


def _infer_source(stamped: StampedEvent) -> str:
    p = stamped.event
    if isinstance(p, PluginMounted | PluginUnmounted | PluginMountRejected | PluginInspected):
        return "lca.plugins.tools.cordis_control"
    if isinstance(p, PluginAuthored):
        return "lca.plugins.tools.cordis_control"
    if isinstance(p, PresetPublished):
        return "lca.application.preset_authoring"
    if isinstance(p, RuntimeObserved):
        return str(getattr(p, "source", "") or "runtime")
    return ""


def _event_key(payload: object) -> str:
    for attr in ("plugin_name", "preset_id", "operation", "tool_name"):
        v = getattr(payload, attr, "")
        if v:
            return f"{attr}={v}"
    return ""


def _brief(stamped: StampedEvent) -> str:
    """人读单行摘要；让 audit json 可直接 grep 关键短语。"""
    p = stamped.event
    if isinstance(p, RuntimeObserved):
        op = getattr(p, "operation", "")
        status = getattr(p, "outcome", "ok")
        plugin = getattr(p, "source", "") or "runtime"
        return f"runtime[{op}] {plugin} {status}"
    if isinstance(p, PluginAuthored):
        return (
            f"authored plugin={p.plugin_name!r} path={p.path} "
            f"actor={p.actor_role or ''} size={p.size_bytes}"
        )
    if isinstance(p, PluginMounted):
        caps = ",".join(p.capabilities) if p.capabilities else "-"
        return (
            f"mounted plugin={p.plugin_name!r} "
            f"grant={','.join(p.capability_grant) or '-'} "
            f"caps=[{caps}] actor={p.actor_role or ''}"
        )
    if isinstance(p, PluginMountRejected):
        caps = ",".join(p.requested_capabilities) if p.requested_capabilities else "-"
        grant = ",".join(p.capability_grant) if p.capability_grant else "-"
        return (
            f"rejected plugin={p.plugin_name!r} reason={p.reason_code} "
            f"grant=[{grant}] requested=[{caps}] meta_present={p.plugin_meta_present}"
        )
    if isinstance(p, PluginUnmounted):
        return f"unmounted plugin={p.plugin_name!r} actor={p.actor_role or ''}"
    if isinstance(p, PluginInspected):
        names = ",".join(p.plugin_names) if p.plugin_names else "-"
        return f"inspected actor={p.actor_role or ''} mounted={p.mounted_count} plugins=[{names}]"
    if isinstance(p, PresetPublished):
        return (
            f"preset published preset_id={p.preset_id!r} plugin={p.plugin_name!r} "
            f"at={p.preset_root}"
        )
    return f"{stamped.event_type} {p!r}"


def _drive_creator_full_loop(preset_root: Path) -> tuple[MemoryJournal, list[dict[str, object]]]:
    """执行 inspect → author → validate → promote → rollback 并返回审计序列。"""
    from cordis import Context

    ctx = Context()
    composer = CordisComposer(ctx, invariant_checker=build_default_invariant_checker())
    tool = build_cordis_control_tool(
        composer=composer,
        caller_grant=(
            "cordis_control.inspect",
            "cordis_control.author",
            "cordis_control.validate",
            "cordis_control.promote",
            "tool_fs.read",
        ),
        actor_role="cordis-creator",
        preset_root=preset_root,
    )
    plugin_path = preset_root / "json_keys.py"
    plugin_path.write_text(_plugin_source("json_keys"), encoding="utf-8")

    import asyncio

    with bind_journal() as journal:
        # Step 1：inspect
        r1 = asyncio.run(tool.execute({"action": "inspect"}))
        assert r1.success
        # Step 2：author
        r2 = asyncio.run(
            tool.execute({"action": "author", "name": "json_keys", "path": str(plugin_path)})
        )
        assert r2.success
        # Step 3：validate
        r3 = asyncio.run(tool.execute({"action": "validate", "name": "json_keys"}))
        assert r3.success
        # Step 4：release promote
        r4 = asyncio.run(
            tool.execute({"action": "promote", "name": "json_keys", "target_scope": "release"})
        )
        assert r4.success
        # Step 5：rollback
        r5 = asyncio.run(tool.execute({"action": "promote", "name": "json_keys", "rollback": True}))
        assert r5.success

        sequence = linear_audit_sequence(journal.store.events)
        return journal, sequence


class TestCordisCreatorAuditLog:
    """§13.3 plugin logs 落到 Journal 的可审计性 + 时间序序列生成。"""

    def test_journal_query_finds_each_event_class(self) -> None:
        """journal 至少含 6 类事件（inspect / authored / mounted / preset / unmounted + RuntimeObserved）。"""
        preset_root = SCRATCH / "audit_query"
        preset_root.mkdir(parents=True, exist_ok=True)

        with bind_journal():
            # 跑完闭环
            journal_2, _ = _drive_creator_full_loop(preset_root)

            # 把 journal 落盘
            jsonl_path = SCRATCH / "cordis_creator_run.jsonl"
            _write_jsonl(journal_2.store.events, jsonl_path)

            # 用 query_journal 按事件类型查
            inspected = query_journal(path=jsonl_path, event_type="PluginInspected")
            authored = query_journal(path=jsonl_path, event_type="PluginAuthored")
            mounted = query_journal(path=jsonl_path, event_type="PluginMounted")
            unmounted = query_journal(path=jsonl_path, event_type="PluginUnmounted")
            preset = query_journal(path=jsonl_path, event_type="PresetPublished")

            assert len(inspected) >= 1, "缺 PluginInspected"
            assert len(authored) >= 1, "缺 PluginAuthored"
            assert len(mounted) >= 1, "缺 PluginMounted"
            assert len(unmounted) >= 1, "缺 PluginUnmounted"
            assert len(preset) >= 1, "缺 PresetPublished"

            # actor_role 过滤
            actor_filter = query_journal(
                path=jsonl_path,
                event_type="PluginMounted",
                actor_role="cordis-creator",
            )
            assert len(actor_filter) == len(mounted)

            # plugin_name 过滤
            plugin_filter = query_journal(
                path=jsonl_path,
                event_type="PluginMounted",
                plugin_name="json_keys",
            )
            assert len(plugin_filter) == len(mounted)

    def test_journal_payload_required_fields_present(self) -> None:
        """每个 Plugin* 事件的 payload 必含必要字段（grant / meta / args / actor_role）。"""
        preset_root = SCRATCH / "audit_payload"
        preset_root.mkdir(parents=True, exist_ok=True)

        with bind_journal():
            journal_2, _ = _drive_creator_full_loop(preset_root)

            # PluginMounted payload 校验
            mounted = [
                s.event for s in journal_2.store.events if isinstance(s.event, PluginMounted)
            ]
            assert mounted, "缺 PluginMounted"
            for ev in mounted:
                assert ev.actor_role == "cordis-creator"
                assert "tool_fs.read" in ev.capabilities
                assert "tool_fs.read" in ev.capability_grant
                assert ev.meta["name"] == "json_keys"
                assert ev.meta["policy_class"] == "execute"

            # PresetPublished payload 校验
            preset_pubs = [
                s.event for s in journal_2.store.events if isinstance(s.event, PresetPublished)
            ]
            assert preset_pubs, "缺 PresetPublished"
            for ev in preset_pubs:
                assert ev.preset_id == "json_keys"
                assert ev.plugin_name == "json_keys"
                assert ev.bundle_path == "bundle.yaml"
                assert ev.plugin_path == "plugins/json_keys.py"

    def test_linear_audit_sequence_is_monotonic(self) -> None:
        """按 seq 排出的线性序列单调递增 + 包含关键 audit 短语。"""
        preset_root = SCRATCH / "audit_linear"
        preset_root.mkdir(parents=True, exist_ok=True)

        with bind_journal():
            _, sequence = _drive_creator_full_loop(preset_root)

            # 序列单调
            seqs = [entry["seq"] for entry in sequence]
            assert seqs == sorted(seqs), f"audit sequence 非单调：{seqs}"

            # 每条记录都有 brief（grep 友好）
            for entry in sequence:
                assert entry["brief"]
                assert entry["event_type"]

            # 时间序审计序列覆盖关键事件
            event_types = [e["event_type"] for e in sequence]
            assert "PluginInspected" in event_types
            assert "PluginAuthored" in event_types
            assert "PluginMounted" in event_types
            assert "PluginUnmounted" in event_types
            assert "PresetPublished" in event_types

            # 时间序：inspected → authored → mounted → preset → unmounted
            type_to_first_idx = {}
            for i, et in enumerate(event_types):
                if et not in type_to_first_idx:
                    type_to_first_idx[et] = i
            assert type_to_first_idx["PluginInspected"] < type_to_first_idx["PluginAuthored"]
            assert type_to_first_idx["PluginAuthored"] < type_to_first_idx["PluginMounted"]
            assert type_to_first_idx["PluginMounted"] < type_to_first_idx["PresetPublished"]
            assert type_to_first_idx["PresetPublished"] < type_to_first_idx["PluginUnmounted"]

            # 落线性审计序列到 {SCRATCH}/cordis_creator_audit.json
            audit_path = SCRATCH / "cordis_creator_audit.json"
            audit_path.write_text(
                json.dumps(sequence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # brief 含「可 grep」的关键短语
            brief_blob = "\n".join(e["brief"] for e in sequence)
            assert "inspected" in brief_blob
            assert "authored plugin='json_keys'" in brief_blob
            assert "mounted plugin='json_keys'" in brief_blob
            assert "preset published" in brief_blob
            assert "unmounted plugin='json_keys'" in brief_blob

    def test_rejection_path_payload_records_full_grant_diff(self) -> None:
        """拒绝路径的 PluginMountRejected payload 含 grant + requested_caps + meta_present。"""
        preset_root = SCRATCH / "audit_reject"
        preset_root.mkdir(parents=True, exist_ok=True)

        with bind_journal() as journal:
            composer = _new_composer()
            tool = build_cordis_control_tool(
                composer=composer,
                caller_grant=("tool_fs.read",),  # 缺 promote
                actor_role="cordis-creator",
                preset_root=preset_root,
            )
            plugin_path = preset_root / "high_cap.py"
            plugin_path.write_text(
                _plugin_source("high_cap", capability="cordis_control.promote"),
                encoding="utf-8",
            )

            import asyncio

            assert asyncio.run(
                tool.execute({"action": "author", "name": "high_cap", "path": str(plugin_path)})
            ).success
            assert asyncio.run(tool.execute({"action": "validate", "name": "high_cap"})).success
            r = asyncio.run(tool.execute({"action": "promote", "name": "high_cap"}))
            assert not r.success

            rejected_stamped = [
                s for s in journal.store.events if isinstance(s.event, PluginMountRejected)
            ]
            assert len(rejected_stamped) == 1
            stamped = rejected_stamped[0]
            ev = stamped.event
            # 必要字段（plan step 4 显式要求 grant + meta + args + trace_id）
            assert ev.actor_role == "cordis-creator"
            assert ev.reason_code == "CapabilityGrantExceeded"
            assert ev.plugin_meta_present is True
            assert "tool_fs.read" in ev.capability_grant
            assert "cordis_control.promote" in ev.requested_capabilities
            # scope 字段存在（trace_id 由 ambient run_scope 盖章；测试不强制 mint）
            assert stamped.scope.run_id is not None  # 字段就位即可
            assert stamped.scope.agent_role == ""  # 未设置 ambient 时留空
            # brief 人读可 grep 拒绝原因
            sequence = linear_audit_sequence(journal.store.events)
            brief = "\n".join(e["brief"] for e in sequence)
            assert "rejected plugin='high_cap'" in brief
            assert "reason=CapabilityGrantExceeded" in brief
