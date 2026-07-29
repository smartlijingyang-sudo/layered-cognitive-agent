"""SharedMemoryTool —— 把 SharedMemoryStore 包装成普通 Tool。

设计意图（ADR-0016）：
团队成员在单体循环内通过 Body → use_tool → ToolRegistry 访问共享存储，
与调用 calculator 等工具无区别。不改 Body / Runtime / AgentEntrypoint 协议。

ops:
  - read:  读取 layer 全部记录（payload=list[str content]）
  - write: 向 layer 追加一条 MemoryRecord
  - list:  返回 layer 记录条数与内容摘要
"""

from __future__ import annotations

from typing import Any, Literal

from lca.contracts.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.decision import Observation
from lca.contracts.enums import SharedMemoryOp
from lca.contracts.ids import new_id
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import SharedMemoryStore, Tool

_VALID_OPS = frozenset(SharedMemoryOp)
_VALID_MEMORY_TYPES: frozenset[str] = frozenset({"working", "semantic", "episodic", "procedural"})
_DEFAULT_IMPORTANCE = 0.8


class SharedMemoryTool(Tool):
    """绑定 team_id + SharedMemoryStore 的工具实现。

    支持三种操作（SharedMemoryOp）：
    - read:  读取 layer 全部记录
    - write: 向 layer 追加一条 MemoryRecord
    - list:  返回 layer 记录条数与内容摘要
    """

    name: str = "shared_memory"
    is_idempotent: bool = False
    default_timeout_s: int = DEFAULT_TOOL_TIMEOUT_S

    def __init__(
        self,
        store: SharedMemoryStore,
        team_id: str,
        *,
        default_layer: str = "semantic",
        source_trace_id: str = "",
    ) -> None:
        self._store = store
        self._team_id = team_id
        self._default_layer = default_layer
        self._source_trace_id = source_trace_id

    def validate(self, args: dict[str, Any]) -> str | None:
        op = args.get("op")
        if op not in _VALID_OPS:
            return f"shared_memory.op 必须是 {sorted(_VALID_OPS)} 之一，收到: {op!r}"
        layer = str(args.get("layer", self._default_layer))
        if layer not in _VALID_MEMORY_TYPES:
            return f"layer 必须是 {_VALID_MEMORY_TYPES} 之一，收到: {layer!r}"
        if not self._store.is_shared(layer):
            return f"层 {layer!r} 未配置为共享（team_id={self._team_id}）"
        if op == SharedMemoryOp.WRITE and not args.get("content"):
            return "write 操作需要 content 字段"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=err,
            )

        op = str(args["op"])
        layer = str(args.get("layer", self._default_layer))

        if op == SharedMemoryOp.READ:
            records = self._store.get_records(layer)
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload=[r.content for r in records],
                extra={"team_id": self._team_id, "layer": layer, "op": op},
            )

        if op == SharedMemoryOp.LIST:
            records = self._store.get_records(layer)
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={"count": len(records), "contents": [r.content for r in records]},
                extra={"team_id": self._team_id, "layer": layer, "op": op},
            )

        # write — layer 已在 validate 中校验属于 _VALID_MEMORY_TYPES
        content = str(args["content"])
        # layer was validated against _VALID_MEMORY_TYPES above, so this cast is safe
        memory_type: Literal["working", "semantic", "episodic", "procedural"] = layer  # type: ignore[assignment]
        record = MemoryRecord(
            record_id=new_id("mem"),
            content=content,
            memory_type=memory_type,
            importance=float(args.get("importance", _DEFAULT_IMPORTANCE)),
            source_trace_id=self._source_trace_id or self._team_id,
        )
        self._store.add_record(layer, record)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"written": content, "record_id": record.record_id},
            extra={"team_id": self._team_id, "layer": layer, "op": SharedMemoryOp.WRITE.value},
        )
