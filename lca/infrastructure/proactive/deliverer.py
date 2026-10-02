"""ProactiveDeliverer：主动消息投递层。

职责单一：把裁决通过的消息 append 进目标 session 的
``surface/assistant_message`` 事件——与前端读的是同一份 session log
（``derive_messages()``），不新开消息协议。

- SESSION_APPEND：从 SessionStore 取 session，不存在则创建（幂等），
  append 事件。事件 data 复用 run 路径的 surface taxonomy，
  ``turn=-1`` 标记非 run 上下文的主动消息，``proactive=true`` 供前端区分。
- RESPONSE_CARRIED：不经过 session，由调用方把 ``carried_message``
  塞进 HTTP 响应（见 routes_onboarding.naming_settle）。

幂等（ADR-0264 §4②）：deliverer 是唯一的 session 写路径，去重放在
写前最后一公里。``_append_to_session`` 前按 ``(session_id, proactive_id)``
查持久化去重状态（state_dir 下的 JSON，有界、可清理，风格对标
scheduler 的 state.json）；同一 key 投递两次，session 里只出现一次。
tick 重跑 / 重试 / 崩溃恢复（新实例 + 同一 state_dir）都不会重复。

顺序是 check → append → mark：append 抛错时不 mark，scheduler 的
重试/死信仍能再次尝试（mark-before-append 会把失败也记成已投递，
导致消息丢失）。

分层约束：只依赖 contracts + Session 的公开 ``append`` 方法，
不碰任何私有属性，不跨层直调。
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Protocol

from lca.contracts.models.proactive.message import (
    DeliveryTarget,
    DeliveryTargetKind,
    ProactiveMessage,
)

_log = logging.getLogger(__name__)

# 非 run 上下文主动消息的 turn 哨兵：与正常 run 的 turn>=0 区分。
PROACTIVE_TURN = -1

# surface 事件类型：复用 run 路径的 taxonomy（ADR-0226 §B）。
SURFACE_ASSISTANT_MESSAGE = "surface/assistant_message"

# 去重状态文件名（落在 state_dir 下，与 scheduler 的 state.json 同级）。
_DEDUP_FILENAME = "proactive_delivered.json"


class SessionLike(Protocol):
    """投递所需的 Session 最小公开接口（避免依赖具体实现类）。"""

    @property
    def id(self) -> str: ...
    def append(self, event_type: str, data: dict[str, Any], **kwargs: Any) -> Any: ...


class SessionStoreLike(Protocol):
    """投递所需的 SessionStore 最小公开接口。"""

    def get(self, session_id: str) -> SessionLike | None: ...
    def create(self, session_id: str | None = None) -> SessionLike: ...


class _DedupStore:
    """``(session_id, proactive_id)`` 去重状态。

    - ``state_dir`` 为 None 时只做进程内去重；传入后持久化到 JSON 文件，
      崩溃恢复（新实例 + 同一 ``state_dir``）依然有效；
    - 有界：``max_entries`` 超限时按时间戳淘汰最老；
    - 可清理：``prune(older_than_ms)`` 删过期记录；
    - 读写风格对标 scheduler：整文件 JSON + tmp 原子替换，损坏时按空处理。
    """

    def __init__(self, state_dir: str | Path | None, max_entries: int = 5000) -> None:
        self._file = (
            Path(state_dir) / _DEDUP_FILENAME if state_dir is not None else None
        )
        self._max_entries = max(1, max_entries)
        self._seen: dict[str, int] = {}

    @staticmethod
    def _key(session_id: str, proactive_id: str) -> str:
        return f"{session_id}\x1f{proactive_id}"

    def _load(self) -> None:
        if self._file is None:
            return
        try:
            with open(self._file, encoding="utf-8") as f:
                data = json.load(f)
            self._seen = (
                {str(k): int(v) for k, v in data.items()}
                if isinstance(data, dict)
                else {}
            )
        except (OSError, ValueError):
            self._seen = {}

    def _save(self) -> None:
        if self._file is None:
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._seen, f, ensure_ascii=False)
        os.replace(tmp, self._file)

    def has(self, session_id: str, proactive_id: str) -> bool:
        # 每次读都从磁盘重载：多实例 / 崩溃恢复场景下状态可见。
        self._load()
        return self._key(session_id, proactive_id) in self._seen

    def mark(
        self, session_id: str, proactive_id: str, now_ms: int | None = None
    ) -> None:
        self._load()
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        self._seen[self._key(session_id, proactive_id)] = now_ms
        overflow = len(self._seen) - self._max_entries
        if overflow > 0:
            oldest = sorted(self._seen, key=self._seen.__getitem__)[:overflow]
            for k in oldest:
                del self._seen[k]
        self._save()

    def prune(self, older_than_ms: int, now_ms: int | None = None) -> int:
        """删除早于 ``now_ms - older_than_ms`` 的记录，返回删除条数。"""
        self._load()
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        cutoff = now_ms - older_than_ms
        stale = [k for k, ts in self._seen.items() if ts < cutoff]
        for k in stale:
            del self._seen[k]
        if stale:
            self._save()
        return len(stale)


class ProactiveDeliverer:
    """主动消息投递器：session append 是唯一的写路径。"""

    def __init__(
        self,
        session_store: SessionStoreLike | None = None,
        *,
        state_dir: str | Path | None = None,
        dedup_max_entries: int = 5000,
    ) -> None:
        self._store = session_store
        self._dedup = _DedupStore(state_dir, dedup_max_entries)

    def deliver(
        self,
        message: ProactiveMessage,
        target: DeliveryTarget,
        *,
        annotate_unretrieved: bool = False,
    ) -> dict[str, Any]:
        """投递一条消息，返回投递回执（fail-loud，不静默吞错）。

        precondition：target.kind 为 SESSION_APPEND 时 session_id 非空
        （contracts 层已校验）。失败时抛错，由调用方决定重试/死信。
        同一 ``(session_id, proactive_id)`` 重复投递时不写 session，
        回执 ``duplicate=True``（幂等命中）。
        """
        if target.kind == DeliveryTargetKind.RESPONSE_CARRIED:
            return {
                "delivered": True,
                "kind": target.kind.value,
                "carried_message": {
                    "id": message.id,
                    "role": message.role,
                    "content": self._render(message, annotate_unretrieved),
                    "source": message.source.value,
                },
            }
        return self._append_to_session(message, target, annotate_unretrieved)

    def _append_to_session(
        self,
        message: ProactiveMessage,
        target: DeliveryTarget,
        annotate_unretrieved: bool,
    ) -> dict[str, Any]:
        if target.session_id is None:
            raise AssertionError("target.session_id is None")
        if self._store is None:
            raise RuntimeError("SESSION_APPEND 需要 session_store")
        # 幂等：写前最后一公里查去重状态
        if self._dedup.has(target.session_id, message.id):
            _log.info(
                "proactive.duplicate_skipped session_id=%s message_id=%s",
                target.session_id,
                message.id,
            )
            return {
                "delivered": False,
                "duplicate": True,
                "kind": target.kind.value,
                "session_id": target.session_id,
            }
        session = self._store.get(target.session_id)
        if session is None:
            session = self._store.create(target.session_id)
            _log.info(
                "proactive.session_created session_id=%s message_id=%s",
                target.session_id,
                message.id,
            )
        event = session.append(
            SURFACE_ASSISTANT_MESSAGE,
            {
                "turn": PROACTIVE_TURN,
                "step": 0,
                "role": message.role,
                "content": self._render(message, annotate_unretrieved),
                "tool_calls": None,
                "usage": None,
                "proactive": True,
                "proactive_id": message.id,
                "proactive_source": message.source.value,
            },
            surface_op="assistant_message",
            actor="proactive",
        )
        # append 成功后才 mark：失败走调用方重试，不丢失
        self._dedup.mark(target.session_id, message.id)
        _log.info(
            "proactive.delivered session_id=%s message_id=%s seq=%s",
            target.session_id,
            message.id,
            event.seq,
        )
        return {
            "delivered": True,
            "kind": target.kind.value,
            "session_id": target.session_id,
            "seq": event.seq,
        }

    @staticmethod
    def _render(message: ProactiveMessage, annotate_unretrieved: bool) -> str:
        content = message.content
        if annotate_unretrieved:
            content = f"{content}\n\n（本次内容未经持久记忆检索，仅供参考）"
        return content


__all__ = ["PROACTIVE_TURN", "SURFACE_ASSISTANT_MESSAGE", "ProactiveDeliverer"]
