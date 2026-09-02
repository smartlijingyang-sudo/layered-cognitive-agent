"""ADR-0169 PR-30:cordis 双词表收口 — 业务 / plugin 必须经 EventDescriptor。

cordis 双词表收口(评审 §S4 + §D9 + I-CURSOR-4):

1. 业务代码(cognition / runtime / agent)禁止直字面
   ``ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')`` —— 必须经
   ``EventDescriptor.derive(execution_point)`` + ``descriptor.cordis_name``
   走单派生表。

2. ``EventDescriptor`` dataclass 必含 ``cordis_name`` 字段(I-CURSOR-4
   结构门禁); 缺字段视为违规,防止 EventDescriptor 失掉 cordis 派生职责。

3. ``CORDIS_EVENT_TABLE`` 必含全部已登记 EP 的 ``cordis_name``;新加 EP
   必须同时填表,防止表与 descriptor 失同步。

4. ``CordisEventBus`` 业务包装不可再 import;参见
   ``test_event_bus_removed.py`` 的更细化断言。

门禁脚本: ``scripts/check_cordis_event_derivation.py`` 在 PR-30 升级为
ERROR 级别 fail-fast(PR-13 是 WARNING 级别)。本测试与该脚本互为强化。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_business_code_uses_event_descriptor_only() -> None:
    """业务代码(cognition / runtime / agent)无 ``ctx.emit`` 直字面调用。

    运行 ``scripts/check_cordis_event_derivation.py``;期望返回 0 且无任何
    L12 / I-CURSOR-4 / I-CURSOR-4-removal 违规。
    """
    script = REPO_ROOT / "scripts" / "check_cordis_event_derivation.py"
    assert script.exists(), f"missing static guard script: {script}"

    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, (
        f"PR-30 cordis double-vocabulary gate FAILED:\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    # 输出应为 PR-30 OK 而非 WARNING/PR-13。
    assert "PR-30 OK" in result.stdout, (
        f"check_cordis_event_derivation.py 应输出 PR-30 OK;实得: {result.stdout!r}"
    )


def test_event_descriptor_has_cordis_name() -> None:
    """I-CURSOR-4 结构门禁:``EventDescriptor`` 必含 ``cordis_name`` 字段。

    用 dataclass fields 直接断言,避免仅依赖 AST 脚本而失锁字段 rename。
    """
    from dataclasses import fields

    from lca.contracts.observability.event_descriptor import EventDescriptor

    field_names = {f.name for f in fields(EventDescriptor)}
    assert "cordis_name" in field_names, (
        f"EventDescriptor 缺 cordis_name 字段(ADR-0169 I-CURSOR-4);"
        f"present fields = {sorted(field_names)}"
    )
    # 同时确保字段类型与 ADR-0169 §D6 一致:``str | None``。
    cordis_field = next(f for f in fields(EventDescriptor) if f.name == "cordis_name")
    type_str = str(cordis_field.type)
    assert "str" in type_str and "None" in type_str, (
        f"EventDescriptor.cordis_name 类型应为 str | None;实得: {type_str!r}"
    )


def test_cordis_event_table_covers_descriptor_cordis_names() -> None:
    """``CORDIS_EVENT_TABLE`` 与 ``EventDescriptor`` 必须保持单字面一致。

    所有 ``lookup_cordis_name(ep).cordis_name`` 必须等于
    ``EventDescriptor.derive(ep).cordis_name``,防止派生表与 descriptor
    失同步后某一方独自演化。
    """
    from lca.contracts.observability.cordis_event_table import (
        all_execution_points,
        lookup_cordis_name,
    )
    from lca.contracts.observability.event_descriptor import EventDescriptor

    for ep in all_execution_points():
        entry = lookup_cordis_name(ep)
        descriptor = EventDescriptor.derive(ep)
        assert entry.cordis_name == descriptor.cordis_name, (
            f"EP={ep!r}: 表 entry.cordis_name={entry.cordis_name!r} != "
            f"descriptor.cordis_name={descriptor.cordis_name!r}"
        )


def test_event_descriptor_derive_unknown_ep_fails_loud() -> None:
    """未登记 EP 的 ``derive()`` 必须抛 ``UnknownCordisEventError``。

    I-CURSOR-4 + L15 ``UnknownEventType`` 子型:静默 fallback 被禁止;
    调用方必须拿到明确错误码。
    """
    from lca.contracts.observability.cordis_event_table import UnknownCordisEventError
    from lca.contracts.observability.event_descriptor import EventDescriptor

    with pytest.raises(UnknownCordisEventError):
        EventDescriptor.derive("agent.bogus.event.never_registered")


def test_business_dirs_have_no_event_bus_module() -> None:
    """业务 + 横切层不再承载 ``event_bus.py``;保护 PR-30 收口不可回填。

    扫描 ``lca/cognition/``,``lca/runtime/``,``lca/agent/`` 三个
    SCAN_DIRS,任何 ``event_bus.py`` 出现都视为违规。
    """
    forbidden_dirs = ("cognition", "runtime", "agent")
    for sub in forbidden_dirs:
        candidate = REPO_ROOT / "lca" / sub / "event_bus.py"
        assert not candidate.exists(), (
            f"PR-30 收口目标不应再承载 CordisEventBus 业务包装: {candidate}"
        )


def test_runtime_event_publisher_unchanged() -> None:
    """``lca/runtime/runtime_event_publisher.py``(lifecycle 而非 cordis)不应被本 PR 误删。

    PR-30 目标仅是 cordis 双词表收口;runtime lifecycle publisher 是独立
    插件子系统,职责清晰,本 PR 不应触及。本测试防止误删蔓延。
    """
    target = REPO_ROOT / "lca" / "runtime" / "runtime_event_publisher.py"
    assert target.exists(), (
        f"unexpected: lifecycle publisher missing (PR-30 should not touch it): {target}"
    )
    text = target.read_text(encoding="utf-8")
    # lifecycle publisher 不应承载 cordis 事件派生 / emit 入口。
    assert "ctx.emit" not in text, (
        f"{target.name} 不得新增 cordis emit 入口(ADR-0169 §D9 / 评审 §S4)"
    )
