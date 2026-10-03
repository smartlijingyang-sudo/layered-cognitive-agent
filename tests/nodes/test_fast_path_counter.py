"""FastPathCounter 契约测试（todo-28 C1；ADR-0246 zero-LLM 快捷分支计数）。

覆盖：初始 0 / note_fast_path 累加 / reset 开新窗口 / 实例隔离 /
frozen+slots 宿主可用（post_init 初始化；domain 字段仍不可写）/
四节点 executor 的 mixin 接线 + 快捷分支打点在场。

覆盖率口径：fast_path_count() / NodeLatencyTracker 同节点 count
（tracker 侧在 tests/framework/graph/test_node_latency.py 覆盖）。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from lca.nodes.fast_path import FastPathCounter
from lca.nodes.reflect.memory_extract.memory_extract import (
    ReflectMemoryExtractExecutor,
)
from lca.nodes.reflect.score.score import ReflectScoreExecutor
from lca.nodes.remember.admit.admit import RememberAdmitExecutor
from lca.nodes.remember.write.write import RememberWriteExecutor


@dataclasses.dataclass(frozen=True, slots=True)
class _FakeExecutor(FastPathCounter):
    name: str = "fake"


def test_initial_count_is_zero():
    assert _FakeExecutor().fast_path_count() == 0


def test_note_fast_path_accumulates():
    ex = _FakeExecutor()
    ex.note_fast_path()
    ex.note_fast_path()
    assert ex.fast_path_count() == 2


def test_reset_starts_fresh_window():
    ex = _FakeExecutor()
    ex.note_fast_path()
    ex.reset_fast_path_count()
    assert ex.fast_path_count() == 0
    ex.note_fast_path()
    assert ex.fast_path_count() == 1


def test_instances_are_isolated():
    a, b = _FakeExecutor(), _FakeExecutor()
    a.note_fast_path()
    assert a.fast_path_count() == 1
    assert b.fast_path_count() == 0


def test_frozen_host_domain_fields_stay_frozen():
    ex = _FakeExecutor(name="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ex.name = "y"  # type: ignore[misc]
    # 计数器 slot 仍可写（可观测性唯一写入点），domain 字段无变化。
    ex.note_fast_path()
    assert ex.name == "x"
    assert ex.fast_path_count() == 1


@pytest.mark.parametrize(
    "executor_cls",
    [
        ReflectScoreExecutor,
        ReflectMemoryExtractExecutor,
        RememberAdmitExecutor,
        RememberWriteExecutor,
    ],
)
def test_real_executors_mix_in_counter(executor_cls):
    assert issubclass(executor_cls, FastPathCounter)


@pytest.mark.parametrize(
    "relpath",
    [
        "lca/nodes/reflect/score/score.py",
        "lca/nodes/reflect/memory_extract/memory_extract.py",
        "lca/nodes/remember/admit/admit.py",
        "lca/nodes/remember/write/write.py",
    ],
)
def test_note_fast_path_call_site_present_in_shortcut_branch(relpath):
    # 接线钉：四个节点的快捷分支必须调用 self.note_fast_path()。
    # admit_recovery/fold 无快捷分支，quality 10:09 轮已实证，故不在此列。
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / relpath).read_text(encoding="utf-8")
    assert "self.note_fast_path()" in src
