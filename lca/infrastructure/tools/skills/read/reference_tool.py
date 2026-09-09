"""read_skill_reference_once — load bundled skill resource files (ADR-0214 §7).

改名 + 节流(同一 ``(skill_id, path)`` 在最近 5 步内失败 ≥ 2 → fail-loud),
防止 run_c218d952c6f2 类回归(模型反复 read_skill_reference 不存在的路径)。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.contracts.protocols.memory.operational_skills import (
    SkillContractError,
    SkillNotFoundError,
    SkillPackageStore,
)
from lca.infrastructure.tools.contract.render.render import RenderContract, contract
from lca.infrastructure.tools.contract.schema.schema import COMMON

READ_SKILL_REFERENCE_ONCE_TOOL = "read_skill_reference_once"

# ADR-0214 §7.3 — 节流默认参数(可被测试 fixture 覆盖)。
_THROTTLE_WINDOW = 5
_THROTTLE_THRESHOLD = 2


class ReadSkillReferenceThrottle:
    """同一 ``(skill_id, path)`` 在 ``window`` 步内失败 ≥ ``threshold`` → fail-loud.

    滑动窗口使用 ``collections.deque(maxlen=window)``,O(1) append。
    线程安全 — SkillReadReferenceOnceTool 可能在并发工具调用中触发。
    """

    def __init__(
        self,
        *,
        window: int = _THROTTLE_WINDOW,
        threshold: int = _THROTTLE_THRESHOLD,
    ) -> None:
        self._window = window
        self._threshold = threshold
        self._fail_history: dict[tuple[str, str], deque[bool]] = {}
        self._lock = threading.Lock()

    def check_and_record(self, skill_id: str, path: str, *, success: bool) -> None:
        """记录本次调用结果;若达到阈值则抛 :class:`SkillContractError`。

        顺序: 先追加本次结果 → 再统计窗口内失败数 → 触发阈值。
        这保证触发是「包含本次」的窗口统计,而不是「上一次触发后」。
        """
        key = (skill_id, path)
        with self._lock:
            history = self._fail_history.get(key)
            if history is None:
                history = deque(maxlen=self._window)
                self._fail_history[key] = history
            history.append(not success)  # True 表示失败
            recent_fails = sum(1 for x in history if x)
        if recent_fails >= self._threshold:
            raise SkillContractError(
                f"read_skill_reference_once({skill_id!r}, {path!r}) "
                f"在最近 {self._window} 步内失败 ≥ {self._threshold}, 节流熔断"
            )

    def reset(self, skill_id: str | None = None, path: str | None = None) -> None:
        """重置窗口;测试与 recovery 用。None 视作通配。"""
        with self._lock:
            if skill_id is None and path is None:
                self._fail_history.clear()
                return
            if skill_id is not None and path is not None:
                self._fail_history.pop((skill_id, path), None)
                return
            # 单边键: 只删能匹配的项
            to_drop = [
                k
                for k in self._fail_history
                if (skill_id is not None and k[0] == skill_id)
                or (path is not None and k[1] == path)
            ]
            for k in to_drop:
                del self._fail_history[k]


# 进程级单例节流器 — 全 run 共享同一窗口。
_default_throttle: ReadSkillReferenceThrottle = ReadSkillReferenceThrottle()


def get_default_throttle() -> ReadSkillReferenceThrottle:
    return _default_throttle


@contract(
    RenderContract(
        tool_name="read_skill_reference_once",
        identifier="lobe-skills",
        api_name="readReference",
        args=(
            COMMON["skill_id"],
            COMMON["path"],
        ),
        state=(
            COMMON["path"],
            COMMON["content"],
            COMMON["size"].optional(),
            COMMON["file_type"].optional(),
            COMMON["encoding"].optional(),
        ),
    )
)
class SkillReadReferenceOnceTool(Tool):
    name = READ_SKILL_REFERENCE_ONCE_TOOL
    description = (
        "读取已安装 skill 的附属资源文件(模板/参考文档/脚本说明等)。"
        "需先 activate_skill,SKILL.md 正文已注入上下文;"
        "仅当正文未涵盖某个子文档时调用本工具,不要重复读同一路径。"
        "同一 (skill_id, path) 在最近 5 步内失败 ≥ 2 → fail-loud。"
        "参数: skill_id、path(skill 包内相对路径,必须在 SKILL.md frontmatter "
        "references 列表里声明)。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string"},
            "path": {"type": "string", "description": "skill 包内相对路径"},
        },
        "required": ["skill_id", "path"],
    }
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(
        self,
        store: SkillPackageStore,
        *,
        throttle: ReadSkillReferenceThrottle | None = None,
    ) -> None:
        self._store = store
        self._throttle = throttle if throttle is not None else _default_throttle

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        skill_id = str(args.get("skill_id") or "").strip()
        path = str(args.get("path") or "").strip()
        try:
            content = self._store.read_resource(skill_id, path)
        except SkillNotFoundError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            self._throttle.check_and_record(skill_id, path, success=False)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(exc),
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        except SkillContractError:
            # 节流熔断本身 — 直接 raise,不让 Observation 吞掉。
            latency_ms = int((time.monotonic() - start) * 1000)
            raise
        latency_ms = int((time.monotonic() - start) * 1000)
        self._throttle.check_and_record(skill_id, path, success=True)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"content": content, "path": path, "skill_id": skill_id},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )
