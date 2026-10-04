"""ADR-0260 T1 第三腿：写盘回执是消费制，同一回执第二次使用必须拒绝。

验收原文：无回执含"已记下"→拒绝；有回执→放行；同一回执第二次使用→拒绝。
机制：`AssistantMemory.last_curated_receipt` setter 把允许宣称的回执写入 latch
文件；`take_claim_right()` 从盘上读取，取到即删，第二次取返回 None →
`guard_reply` 落到拒绝分支。latch 文件是唯一状态，一个 run 里的两个
AssistantMemory 实例因此看到同一份回执。断言直接针对这一机制。
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


def test_claim_minted_after_construction_is_visible_to_the_other_instance(
    tmp_path: Path,
) -> None:
    """一个 run 里两个实例：后写入的回执必须能被先构造的实例取到。

    tool scope 与 runtime scope 各构造一个 AssistantMemory。runtime scope 在
    run 开始时就建好，tool scope 在 run 中途写盘并铸造回执。缓存到实例字段时
    先构造的那个永远看不到，于是拒绝一次已经成功的宣称，并把对方合法写下的
    latch 删掉。
    """
    constructed_first = AssistantMemory(tmp_path / "home")
    assert constructed_first.take_claim_right() is None

    writer = AssistantMemory(tmp_path / "home")
    writer.last_curated_receipt = _receipt()

    taken = constructed_first.take_claim_right()
    assert taken is not None and taken.record_ids == ("r1",)
    assert constructed_first.take_claim_right() is None
    assert not (tmp_path / "home" / _LATCH).is_file()


def test_a_failed_take_does_not_unlink_another_instances_latch(tmp_path: Path) -> None:
    """空取一次不得删盘：先构造的实例取不到时，对方刚写的 latch 必须还在。

    这是 run_4fcfb6d83c8c 的实际时序。runtime scope 实例在 run 开始时构造，
    tool scope 实例在 run 中途写盘铸造回执，然后 runtime scope 实例去取。
    缓存字段为空时它取不到，却仍然把对方的 latch 删了，于是下一次宣称也
    没有回执可用。
    """
    constructed_first = AssistantMemory(tmp_path / "home")

    writer = AssistantMemory(tmp_path / "home")
    writer.last_curated_receipt = _receipt()
    assert (tmp_path / "home" / _LATCH).is_file()

    assert constructed_first.take_claim_right() is not None
    assert not (tmp_path / "home" / _LATCH).is_file()

    writer.last_curated_receipt = _receipt()
    stale = AssistantMemory(tmp_path / "home")
    (tmp_path / "home" / _LATCH).unlink()
    assert stale.take_claim_right() is None

    writer.last_curated_receipt = _receipt()
    assert stale.take_claim_right() is not None


def test_guard_reply_allows_a_claim_written_by_the_other_instance(
    tmp_path: Path,
) -> None:
    """端到端：写盘发生在另一个实例上，宣称仍应放行一次。"""
    guard_instance = AssistantMemory(tmp_path / "home")
    writer = AssistantMemory(tmp_path / "home")
    writer.last_curated_receipt = _receipt()

    runtime = SimpleNamespace(memory=guard_instance)
    assert guard_reply("我记下了", runtime) == "我记下了"
    assert guard_reply("我记下了", runtime) == _REFUSAL
