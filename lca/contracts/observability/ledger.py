"""RunLedger contracts —— ADR-0065 PR-4 / L1 / L2 / L3 / L7。

``RunLedger`` 是每个 run 的单一提交仲裁者。它在单一临界区内完成 descriptor
校验、scope/causation 盖章、policy 处理、``run_seq`` expected-version 比较、
durable append 和 commit-mark;之后才向 ``ProjectionRegistry`` 发布。

L1: 一次发生一次提交 —— 写入路径只有 ``RunLedger.append()``。
L2: 提交先于观察 —— durable commit 完成后才通知投影。
L3: 身份与顺序不可重铸 —— ``run_seq`` 严格连续;``event_id`` 全局唯一。
L7: 终态封存 —— terminal event 提交后,账本冻结,拒绝追加领域事实。

实现位置:``lca/layer0_infra/observability/journal/engine.py:RunLedger``。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import JournalRecord, StampedEvent


class LedgerSealedError(RuntimeError):
    """L7: terminal event 后拒绝追加领域事实。

    终态事件提交后,账本封存;任何后续 ``append()`` 抛此错。
    """


class LedgerSeqMismatchError(RuntimeError):
    """L1 / L3: 调用方声明的 ``expected_run_seq`` 与当前不一致。

    并发调用方必须显式声明期望 seq;并发竞争下不匹配抛错,防止 race 重铸
    序列。
    """


class LedgerUnregisteredError(RuntimeError):
    """L4: descriptor 未登记或 payload_schema_version 不匹配。"""


class LedgerDurabilityError(RuntimeError):
    """L2: ``required`` 事件的 durable 持久化失败。

    调用方必须收到显式错误,不得"已写入内存即视为成功"。
    """


@runtime_checkable
class RunLedger(Protocol):
    """每个 run 的提交仲裁者契约(ADR-0065 L1/L2/L3/L7)。"""

    @property
    def is_sealed(self) -> bool:
        """L7: 终态事件提交后返回 True。"""

    @property
    def run_seq(self) -> int:
        """最后一个已提交 seq;空账本为零。"""

    @property
    def run_id(self) -> str:
        """所属 run 的稳定身份。"""

    def append(
        self,
        event: StampedEvent | JournalRecord,
        *,
        expected_run_seq: int | None = None,
    ) -> StampedEvent:
        """提交一条事实;返回盖章后的 ``StampedEvent``。

        Raises:
            LedgerSealedError: 终态封存后调用(L7)
            LedgerSeqMismatchError: expected_run_seq 与当前不匹配(L1/L3)
            LedgerUnregisteredError: descriptor 未登记或 schema 版本不匹配(L4)
            LedgerDurabilityError: required 事件持久化失败(L2)
        """

    def seal(self, terminal_event: StampedEvent | JournalRecord) -> StampedEvent:
        """L7: 提交终态事件并封存账本。

        终态事件必须是已知 terminal 类型(``AgentRunFinished`` /
        ``TeamRunFinished`` 等);封存后 ``is_sealed=True``。
        """

    def events(self) -> Sequence[StampedEvent]:
        """已提交事件的稳定快照。"""

    def get(self, seq: int) -> StampedEvent | None:
        """按连续序列 O(1) 读取;越界返回 None。"""

    def read_from(self, after_seq: int) -> Sequence[StampedEvent]:
        """返回严格晚于 ``after_seq`` 的事件,供可恢复消费者拉取。"""

    def flush(self) -> None:
        """冲刷 backend + projection。"""

    def close(self) -> None:
        """关闭 backend + projection;封存后调用安全。"""


@dataclass(frozen=True)
class LedgerStats:
    """运行账本的统计快照(测试 / 诊断用)。"""

    run_id: str
    run_seq: int
    is_sealed: bool
    event_count: int
    backend_name: str


__all__ = [
    "LedgerDurabilityError",
    "LedgerSealedError",
    "LedgerSeqMismatchError",
    "LedgerStats",
    "LedgerUnregisteredError",
    "RunLedger",
]
