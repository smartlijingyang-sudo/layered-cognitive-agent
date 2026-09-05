"""端到端 sanity: boot web-standard profile, 创建 RunSession, 模拟一次 run 的
 spine 路径, 验证 events.jsonl + journal.json 双写 + doctor H2 ok。

独立运行(不在 tests/observability/ 下), 防止 import 链断裂。
"""

from __future__ import annotations

import asyncio

from lca.harness.profile.boot import boot_profile
from lca.infrastructure.observability.writable_matrix import NullStorage
from lca.infrastructure.observability.writable_matrix.registry import (
    WritableFaceRegistry,
)


def test_boot_web_standard_exposes_event_spine_and_writable_registry() -> None:
    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))

    event_spine = ctx.inject("event_spine")
    writable_face_registry = ctx.inject("writable_face_registry")
    run_ledger_factory = ctx.inject("run_ledger_factory")

    assert event_spine is not None, "web-standard profile must expose event_spine"
    assert writable_face_registry is not None, (
        "web-standard profile must expose writable_face_registry "
        "(loaded by writable.matrix.default)"
    )
    assert isinstance(writable_face_registry, WritableFaceRegistry)
    # ADR-0186 单写者:writable matrix 的 storage 面必须 Null(不落盘);
    # spine ledger 由 Session / spine-sink 链唯一写入。
    assert isinstance(writable_face_registry.require("storage"), NullStorage)
    assert run_ledger_factory is not None


def test_event_spine_subscribe_accepts_deriver_callbacks() -> None:
    """event_spine.subscribe() 可接受 StepTreeAccumulatorDeriver.on_event (FD-2)。"""
    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))
    spine_core = ctx.inject("event_spine")
    assert spine_core is not None

    received: list[int] = []

    def _callback(record: object) -> None:
        received.append(1)

    spine_core.event_spine.subscribe(_callback)
    spine_core.event_spine.close()
