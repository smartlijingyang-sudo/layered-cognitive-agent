"""ADR-0260 T1 第三腿：写盘回执是消费制，同一回执第二次使用必须拒绝。

验收原文：无回执含"已记下"→拒绝；有回执→放行；同一回执第二次使用→拒绝。
机制：`AssistantMemory.last_curated_receipt` setter 把允许宣称的回执存入
`_open_claim`（并写 latch 文件）；`take_claim_right()` 取走后置空 + 删 latch，
第二次取返回 None → `guard_reply` 落到拒绝分支。断言直接针对这一机制。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lca.cognition.memory.acknowledgement import _REFUSAL, guard_reply
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.domain.curated import CuratedProjectionReceipt

_LATCH = "memory/claim-latch.json"


def _receipt() -> CuratedProjectionReceipt:
    return CuratedProjectionReceipt(
        ok=True, path="memory/MEMORY.md", byte_count=128, record_ids=("r1",)
    )


def _memory_with_open_claim(tmp_path: Path) -> AssistantMemory:
    memory = AssistantMemory(tmp_path / "home")
    memory.last_curated_receipt = _receipt()
    return memory


def test_take_claim_right_is_single_use(tmp_path: Path) -> None:
    memory = _memory_with_open_claim(tmp_path)
    first = memory.take_claim_right()
    assert first is not None
    assert first.record_ids == ("r1",)
    # 第二次取：回执已消费，返回 None；latch 文件同步清除
    assert memory.take_claim_right() is None
    assert not (tmp_path / "home" / _LATCH).is_file()


def test_guard_reply_refuses_second_claim_with_same_receipt(tmp_path: Path) -> None:
    """端到端：同一回执只能放行一次"已记下"宣称，第二次必须拒绝。"""
    runtime = SimpleNamespace(memory=_memory_with_open_claim(tmp_path))
    assert guard_reply("我记下了", runtime) == "我记下了"
    assert guard_reply("我记下了", runtime) == _REFUSAL


def test_open_claim_survives_restart_but_stays_single_use(tmp_path: Path) -> None:
    """latch 文件让未消费的回执跨进程重启仍有效，但消费制语义不变。"""
    _memory_with_open_claim(tmp_path)
    assert (tmp_path / "home" / _LATCH).is_file()
    restarted = AssistantMemory(tmp_path / "home")
    first = restarted.take_claim_right()
    assert first is not None and first.record_ids == ("r1",)
    assert restarted.take_claim_right() is None
    assert not (tmp_path / "home" / _LATCH).is_file()
