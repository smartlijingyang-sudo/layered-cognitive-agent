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

from typing import Any

from lca.contracts.decision import Observation
from lca.contracts.ids import new_id
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import SharedMemoryStore, Tool

_VALID_OPS = frozenset({"read", "write", "list"})


class SharedMemoryTool(Tool):
    """绑定 team_id + SharedMemoryStore 的工具实现。"""

    name: str = "shared_memory"
    is_idempotent: bool = False
    default_timeout_s: int = 5

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
        if not self._store.is_shared(layer):
            return f"层 {layer!r} 未配置为共享（team_id={self._team_id}）"
        if op == "write" and not args.get("content"):
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

        if op == "read":
            records = self._store.get_records(layer)
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload=[r.content for r in records],
                extra={"team_id": self._team_id, "layer": layer, "op": op},
            )

        if op == "list":
            records = self._store.get_records(layer)
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={"count": len(records), "contents": [r.content for r in records]},
                extra={"team_id": self._team_id, "layer": layer, "op": op},
            )

        # write
        content = str(args["content"])
        record = MemoryRecord(
            record_id=new_id("mem"),
            content=content,
            memory_type=layer,  # type: ignore[arg-type]
            importance=float(args.get("importance", 0.8)),
            source_trace_id=self._source_trace_id or self._team_id,
        )
        self._store.add_record(layer, record)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"written": content, "record_id": record.record_id},
            extra={"team_id": self._team_id, "layer": layer, "op": "write"},
        )
