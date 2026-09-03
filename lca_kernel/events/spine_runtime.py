"""spine 运行时 helpers（ADR-0181 提取层）。

机制本体（``mechanism.py``）只负责 send/subscribe + 鉴权 + 失败语义；
壳类（``payloads_spine.py``）只负责 typed payload + EP 闭集；
本模块负责"所有 spine sink/subscriber 都要做的事"——统一 helpers。

提取动机（PR-2 复审）：
- chain_sink 自己维护 ``_last_hash`` 类状态 + 散落的 hash 计算 →
  ``SpineChain`` 显式无状态计算，prev_hash 显式传入
- chain_sink / step_tree / console_projector 各自 ``hasattr(payload, "x")``
  类型守卫 → ``is_spine_event()`` TypeGuard
- chain_sink 自己 ``datetime.now(timezone.utc)`` 落盘时间戳 →
  ``SpineClock.now_iso()`` 统一
- 未来 N 个 sink/subscriber 各自要"结构化记录事件" →
  ``SpineEventRecord.build()`` 统一序列化

不属于本模块的：
- 机制本体（mechanism.py）
- 壳类 payload（payloads_spine.py）
- 任何 sink/subscriber plugin 业务逻辑

设计原则：
- **无状态**：除 ``SpineChain`` 提供无状态纯函数外，不持类级可变状态
- **不 import plugin**：helpers 不依赖任何 sink/subscriber
- **kernel 元层**：与 mechanism 同一层，固定不可替换
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO, TypeGuard

if TYPE_CHECKING:
    from lca.contracts.event import EventPayload
    from lca_kernel.events import EventRef
    from lca_kernel.events.payloads_spine import SpineEventPayload

log = logging.getLogger(__name__)


# ── 类型守卫 ──────────────────────────────────────────────────────────────


def is_spine_event(payload: Any) -> TypeGuard[SpineEventPayload]:
    """类型守卫：payload 是 SpineEventPayload？

    替代散落的 ``hasattr(payload, "execution_point")`` 模式。pydantic
    v2 BaseModel 必有 ``execution_point`` 字段，鸭子类型判定足够。
    """
    return hasattr(payload, "execution_point") and hasattr(payload, "channel")


# ── 时钟 ────────────────────────────────────────────────────────────────


class SpineClock:
    """统一时钟 helper。

    替代散落的 ``datetime.now(timezone.utc).isoformat()`` 模式。
    全局可注入（测试可换 FrozenClock）；生产用 wall-clock UTC。
    """

    _override: datetime | None = None

    @classmethod
    def now(cls) -> datetime:
        if cls._override is not None:
            return cls._override
        return datetime.now(timezone.utc)

    @classmethod
    def now_iso(cls) -> str:
        return cls.now().isoformat()

    @classmethod
    def freeze(cls, at: datetime | None) -> None:
        """测试用：固定时钟；at=None 解除。"""
        cls._override = at


# ── Hash chain（无状态显式） ──────────────────────────────────────────────


class SpineChain:
    """无状态 chain 计算 helper。

    替代 chain_sink 自维护 ``_last_hash`` 类级可变状态。所有 chain 操作显式
    传 prev_hash，避免类级共享状态在并发 / 重入下不可预期。

    用法：
        prev = None
        for record in records:
            new_hash = SpineChain.next_hash(prev, record)
            record["prev_event_hash"] = prev
            record["event_hash"] = new_hash
            prev = new_hash

    caller 自行持久化 prev（每 sink 自己一个 chain 上下文）。
    """

    @staticmethod
    def causality_id(record: dict[str, Any]) -> str:
        """算 record 的 causality_id（sha256:hex）。"""
        payload = json.dumps(
            {
                "execution_point": record.get("execution_point"),
                "channel": record.get("channel"),
                "payload": record.get("payload"),
                "event_id": record.get("event_id"),
            },
            sort_keys=True,
            default=str,
        )
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def next_hash(prev_hash: str | None, causality_id: str) -> str:
        """算 chain next event_hash（sha256:hex）。"""
        return (
            "sha256:"
            + hashlib.sha256(((prev_hash or "") + causality_id).encode("utf-8")).hexdigest()
        )


# ── 记录序列化 ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SpineChainContext:
    """chain 计算上下文（显式传 None = chain 起点）。

    sink 自维护 prev_hash；构造 record 时把 prev_hash 装进 SpineChainContext
    传入 build()。next_hash 返回后 sink 用它更新自己的 SpineChainContext.prev_hash。
    """

    prev_hash: str | None = None


@dataclass(frozen=True, slots=True)
class SpineEventRecord:
    """spine 事件标准化记录（不可变 dataclass）。

    sink 落盘前 build() 一次，dict 落 jsonl 即可。所有 sink 走同一序列化
    路径，避免 EP/channel/payload 字段名漂移。
    """

    event_id: str
    category: str
    execution_point: str
    channel: str
    payload: dict[str, Any]
    ts: str
    causation_id: str | None = None
    prev_event_hash: str | None = None
    event_hash: str | None = None

    @classmethod
    def build(
        cls,
        payload: SpineEventPayload,
        ref: EventRef,
        *,
        chain: SpineChainContext | None = None,
    ) -> SpineEventRecord:
        """从 SpineEventPayload + EventRef 构造标准化记录。

        chain 显式传才算 chain（causation_id + prev_event_hash + event_hash）。
        传 chain 时 prev_event_hash 可 None（chain 起点）。
        不传 chain = 不算 chain（causation_id/prev_event_hash/event_hash 均为 None）。
        """
        record = cls(
            event_id=ref.event_id,
            category=ref.category,
            execution_point=payload.execution_point,
            channel=payload.channel,
            payload=dict(payload.payload),
            ts=SpineClock.now_iso(),
        )
        if chain is None:
            return record
        base = {
            "execution_point": record.execution_point,
            "channel": record.channel,
            "payload": record.payload,
            "event_id": record.event_id,
        }
        causation = SpineChain.causality_id(base)
        event_hash = SpineChain.next_hash(chain.prev_hash, causation)
        return cls(
            event_id=record.event_id,
            category=record.category,
            execution_point=record.execution_point,
            channel=record.channel,
            payload=record.payload,
            ts=record.ts,
            causation_id=causation,
            prev_event_hash=chain.prev_hash,
            event_hash=event_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        """转可 jsonl 序列化 dict。

        字段一律输出（值可 None），保证下游消费者 dict.get() / d["k"] 行为一致。
        chain 字段（causation_id / prev_event_hash / event_hash）未启用时为 None。
        """
        return {
            "event_id": self.event_id,
            "category": self.category,
            "execution_point": self.execution_point,
            "channel": self.channel,
            "payload": self.payload,
            "ts": self.ts,
            "causation_id": self.causation_id,
            "prev_event_hash": self.prev_event_hash,
            "event_hash": self.event_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpineEventRecord:
        """从 dict 反序列化（to_dict 的逆操作）。

        ADR-0183 PR-5：SpineReader 的唯一构造入口；字段名 / 字段顺序与
        ``to_dict()`` 严格对齐。缺字段 / 类型不匹配由调用方（reader）吞错，
        本方法直接 raise 触发 caller 跳过。
        """
        return cls(
            event_id=str(data["event_id"]),
            category=str(data["category"]),
            execution_point=str(data["execution_point"]),
            channel=str(data["channel"]),
            payload=dict(data.get("payload") or {}),
            ts=str(data["ts"]),
            causation_id=data.get("causation_id"),
            prev_event_hash=data.get("prev_event_hash"),
            event_hash=data.get("event_hash"),
        )


# ── 日志输出 ──────────────────────────────────────────────────────────────


class SpineStream:
    """统一流输出 helper。

    替代 console_projector 自己 ``print(... file=sys.stdout)`` 模式。
    支持注入 stream（测试用 io.StringIO），env 覆盖默认 stream。
    """

    def __init__(self, *, default: TextIO | None = None) -> None:
        env_path = os.environ.get("LCA_SPINE_STREAM")
        if env_path and env_path != "-":
            # 写到文件而不是 stdout（生产 SSE / 容器友好）；
            # 持有文件句柄到对象生命周期,不能用 with
            self._default = Path(env_path).open("a", encoding="utf-8")  # noqa: SIM115
        else:
            self._default = default or sys.stdout

    def write(self, line: str) -> None:
        print(line, file=self._default, flush=True)


# ── 落盘路径 helper ──────────────────────────────────────────────────────


def default_chain_path() -> Path:
    """spine chain 落盘默认路径。

    env ``LCA_SPINE_CHAIN_PATH`` 覆盖；默认 ``$TMPDIR/lca_spine_chain.jsonl``。
    """
    env = os.environ.get("LCA_SPINE_CHAIN_PATH")
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / "lca_spine_chain.jsonl"


__all__ = [
    "SpineChain",
    "SpineChainContext",
    "SpineClock",
    "SpineEventRecord",
    "SpineStream",
    "build_record",
    "default_chain_path",
    "is_spine_event",
]


# ── 统一 record 构造入口（ADR-0183 PR-5）─────────────────────────────────


def build_record(
    payload: EventPayload,
    ref: EventRef,
    *,
    chain: SpineChainContext | None = None,
) -> SpineEventRecord:
    """统一 record 构造入口 —— ADR-0183 §3.5 + PR-5。

    旧 ``_build_event_record(sp, ref)`` 反推 14 字段 ``EventRecord`` 的逻辑
    被吸收；``SpineEventRecord``（9 字段）是新的字节布局 SSOT，plugin 不可改
    ``to_dict()``。

    payload 形态兼容：
    - ``SpineEventPayload``：直接读 ``execution_point`` / ``channel`` /
      ``prev_event_hash`` 字段
    - 其它 ``EventPayload``（非 spine）：``getattr(payload, "execution_point",
      "unknown")`` 容错走位；channel 默认 ``"fact"``；prev_event_hash 默认 None
    """
    execution_point = getattr(payload, "execution_point", "unknown")
    channel = getattr(payload, "channel", "fact")
    inner_payload: dict[str, Any] = getattr(payload, "payload", {}) or {}
    prev_event_hash_attr: str | None = getattr(payload, "prev_event_hash", None)

    record = SpineEventRecord(
        event_id=ref.event_id,
        category=ref.category,
        execution_point=execution_point,
        channel=channel,
        payload=inner_payload,
        ts=SpineClock.now_iso(),
        causation_id=None,
        prev_event_hash=prev_event_hash_attr,
        event_hash=None,
    )

    if chain is None:
        return record

    base = {
        "execution_point": record.execution_point,
        "channel": record.channel,
        "payload": record.payload,
        "event_id": record.event_id,
    }
    causation_id = SpineChain.causality_id(base)
    event_hash = SpineChain.next_hash(chain.prev_hash, causation_id)
    return SpineEventRecord(
        event_id=record.event_id,
        category=record.category,
        execution_point=record.execution_point,
        channel=record.channel,
        payload=record.payload,
        ts=record.ts,
        causation_id=causation_id,
        prev_event_hash=chain.prev_hash,
        event_hash=event_hash,
    )
