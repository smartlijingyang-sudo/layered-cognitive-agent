"""phase.reflect.memory.extract — primitive node: LLM distillation of memory candidates.

ADR-0246: replaces the hardcoded keyword extraction (``_SEMANTIC_DIRECTIVE_MARKERS``)
in ``phase.reflect.score`` with a schema-constrained small LLM call. The node
reads the current turn's user statement from ``AgentState.task`` and emits
structured ``memory_candidates`` (list of dicts) on ``reflection.extra``.

Fast path: ordinary replies without self-reference never invoke the LLM
(``_may_contain_self_reference`` is a cost gate, not an extraction heuristic).
Extraction failures are fail-soft: the reflection passes through unchanged and
the cognitive main flow is not blocked (ADR-0246 §0.6).
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.cognition.memory.govern import govern
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType, MemoryCategory
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.contracts.protocols.memory.filter import MemoryPreFilter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer
from lca.infrastructure.memory.pre_filter import DEFAULT_MEMORY_TOKENS, FallbackMemoryFilter

# 快速路径成本门：仅当用户陈述可能包含自我身份/偏好信号时才值得调 LLM 蒸馏。
# 这是成本门（避免普通回复产生 LLM 调用），不是提取启发式；提取本身由 LLM
# 完成（ADR-0246 §3.3 / §7）。ADR-0247 回归：无第一人称代词的偏好句
# （如「还是简洁一点好」）也必须触发，否则偏好纠正永不落盘。误报只多一次
# LLM 小调用，可接受；漏报会丢记忆，不可接受。
_SELF_REFERENCE_TOKENS: tuple[str, ...] = DEFAULT_MEMORY_TOKENS

_EXTRACT_PROMPT = """ROLE: memory_extract
你是记忆提取器。从用户陈述中提取结构化记忆候选。

规则：
- 只提取用户明确陈述的自我身份、偏好或显式要求记住的事实。
- content 必须是第三人称结构化事实（如「用户身份：系统架构师」「用户偏好：不喜欢啰嗦」），禁止输出用户原文整句。
- category 只能是 identity / preference / fact。
- confidence 0.0-1.0：用户明确陈述 = 1.0，模型推断 = 0.6 以下。
- dedupe_key 用于同维度幂等与覆盖更新（supersede），必须是稳定的抽象属性维度（格式为 category:topic，如 identity:role、identity:name、preference:tech_stack、preference:code_style、preference:database、preference:verbosity）。
  【铁律】dedupe_key 代表稳定的主题维度，严禁把具体的偏好值拼入 key（例如偏好 Python 必须是 preference:tech_stack，严禁 preference:tech_stack_python；身份是架构师必须是 identity:role，严禁 identity:architect）。
- 如果用户陈述是在变更、替换或废弃某项已有偏好/身份，必须直接复用对应已有记忆的 dedupe_key 进行覆盖替换。
- 没有候选时输出空数组 []。

当前已有活跃记忆（供参考，如修改/替换下列某项请复用对应 dedupe_key）：
{existing_memories}

输出 JSON 数组（不要 markdown 代码块），每项格式：
[{"category": "identity", "content": "用户身份：系统架构师", "confidence": 1.0, "dedupe_key": "identity:role"}]

用户陈述：
{task}
"""

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _may_contain_self_reference(task: str) -> bool:
    """快速路径门：判断用户陈述是否可能包含自我身份/偏好信号。"""
    lowered = task.lower()
    return any(token in task or token in lowered for token in _SELF_REFERENCE_TOKENS)


def _parse_candidates(text: str) -> list[dict[str, Any]]:
    """从 LLM 回复中解析候选数组；解析失败返回空列表（fail-soft）。"""
    if not text:
        return []
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return []
    try:
        raw = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        content = str(item.get("content") or "").strip()
        if category not in {c.value for c in MemoryCategory} or not content:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        candidates.append(
            {
                "category": category,
                "content": content,
                "confidence": max(0.0, min(1.0, confidence)),
                "source": str(item.get("source") or "model"),
                "dedupe_key": str(item.get("dedupe_key") or "").strip() or None,
            }
        )
    return candidates


def _format_existing_memories(runtime: Any) -> str:
    """提取当前活跃的身份与偏好记忆，供提取器做上下文感知的覆盖与演化。"""
    memory = getattr(runtime, "memory", None)
    if memory is None and hasattr(runtime, "get"):
        memory = runtime.get("memory")
    if memory is None or not hasattr(memory, "query"):
        return "（无）"
    try:
        from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer

        records = [
            r
            for r in memory.query(MemoryLayer.SEMANTIC)
            if getattr(r, "category", None) in {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE}
            and not getattr(r, "deleted", False)
        ]
        if not records:
            return "（无）"
        lines = []
        for r in records:
            key_str = f" [dedupe_key: {r.dedupe_key}]" if getattr(r, "dedupe_key", None) else ""
            lines.append(f"-{key_str} {r.content}")
        return "\n".join(lines)
    except Exception:
        return "（无）"


@dataclass(frozen=True, slots=True)
class ReflectMemoryExtractExecutor:
    """Primitive: distill the current user statement into memory candidates."""

    semantic_name: str = "phase.reflect.memory.extract"
    region: str = "reflect"
    declared_inputs: tuple[PortName, ...] = ("reflection",)
    declared_outputs: tuple[PortName, ...] = ("reflection", "routing")
    pre_filter: MemoryPreFilter | None = None
    governor_enabled: bool = False
    now_ms: Callable[[], int] | None = None

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        reflection = input.port_values.get("reflection")
        if reflection is None:
            return self._passthrough(reflection)
        extra = getattr(reflection, "extra", None)
        if not isinstance(extra, dict):
            extra = {}
        if extra.get("fast_path") is True or extra.get("memory_candidates"):
            return self._passthrough(reflection)

        if self.governor_enabled:
            try:
                governed = self._apply_governor(context, reflection)
            except Exception:
                # Buffer or template failure must not fail the turn.
                governed = None
            if governed is not None:
                return governed

        runtime = context.runtime or {}
        state = getattr(runtime, "agent_state", None)
        if state is None and hasattr(runtime, "get"):
            state = runtime.get("agent_state")
        task = str(getattr(state, "task", "") or "").strip()
        if not task:
            return self._passthrough(reflection)

        filter_ = self.pre_filter if self.pre_filter is not None else FallbackMemoryFilter()
        decision = await filter_.evaluate(task)
        if not decision.should_extract:
            return self._passthrough(reflection)

        adapter = getattr(runtime, "adapter", None)
        if adapter is None and hasattr(runtime, "get"):
            adapter = runtime.get("adapter")
        if adapter is None or not hasattr(adapter, "complete"):
            return self._passthrough(reflection)

        existing_memories = _format_existing_memories(runtime)
        prompt = _EXTRACT_PROMPT.replace("{existing_memories}", existing_memories).replace(
            "{task}", task
        )
        try:
            response = await adapter.complete(prompt)
            candidates = _parse_candidates(getattr(response, "text", "") or "")
        except Exception:
            # 提取失败不阻塞主流程（ADR-0246 §0.6 fail-soft）。
            return self._passthrough(reflection)

        if candidates:
            extra["memory_candidates"] = candidates
            extra["pre_filter"] = {
                "source": decision.source,
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
        return self._passthrough(reflection)

    def _apply_governor(self, context: NodeContext, reflection: object) -> NodeOutput | None:
        runtime = context.runtime or {}
        home = _episode_home(runtime)
        state = getattr(runtime, "agent_state", None)
        if state is None and hasattr(runtime, "get"):
            state = runtime.get("agent_state")
        turns = getattr(state, "control_turns", None) if state is not None else None
        observation = None
        if isinstance(turns, list) and turns:
            observation = getattr(turns[-1], "observation", None)
        observation_success = (
            getattr(observation, "success", None) if observation is not None else None
        )
        if observation_success is not None and not isinstance(observation_success, bool):
            observation_success = None
        observation_error = getattr(observation, "error", None) if observation is not None else None
        if observation_error is not None and not isinstance(observation_error, str):
            observation_error = str(observation_error)
        last_error = getattr(state, "last_error", None) if state is not None else None
        if last_error is not None and not isinstance(last_error, str):
            last_error = str(last_error)
        lesson = getattr(reflection, "lesson", None)
        if lesson is not None and not isinstance(lesson, str):
            lesson = str(lesson)
        fact = govern(
            task=str(getattr(state, "task", "") or ""),
            trace_id=str(getattr(state, "trace_id", "") or ""),
            lesson=lesson,
            observation_success=observation_success,
            observation_error=observation_error,
            last_error=last_error,
            now_ms=self.now_ms() if self.now_ms is not None else int(time.time() * 1000),
        )
        if fact is None:
            return self._passthrough(reflection)
        if home is None:
            return None
        EpisodeBuffer(home).append(fact)
        return self._passthrough(reflection)

    @staticmethod
    def _passthrough(reflection: object) -> NodeOutput:
        return NodeOutput(
            port_values={
                "reflection": reflection,
                "routing": RoutingDecision(action_type=ActionType.RESPOND),
            }
        )


def _runtime_get(runtime: object, key: str) -> object:
    getter = getattr(runtime, "get", None)
    if callable(getter):
        return getter(key)
    return None


def _episode_home(runtime: object) -> Path | None:
    raw_home = _runtime_get(runtime, "assistant_home_path")
    if isinstance(raw_home, Path):
        return raw_home if str(raw_home).strip() else None
    if isinstance(raw_home, str) and raw_home.strip():
        return Path(raw_home)
    memory = _runtime_get(runtime, "memory")
    bound = getattr(memory, "home_path", None)
    if isinstance(bound, Path):
        return bound
    if isinstance(bound, str) and bound.strip():
        return Path(bound)
    return None


class Config(BaseModel):
    """Optional daytime episode governor. Default off leaves today's extractor."""

    model_config = ConfigDict(extra="forbid")

    governor_enabled: bool = False


def _config_from(config: object) -> Config:
    if isinstance(config, Config):
        return config
    if isinstance(config, dict):
        return Config.model_validate(config)
    return Config()


@plugin(
    id="phase.reflect.memory.extract",
    Config=Config,
    provides=("reflect::phase.reflect.memory.extract",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/reflect/test_memory_extract_distills_identity.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_reflect_memory_extract.checked",
                "phase_reflect_memory_extract.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    parsed = _config_from(config)
    ctx.provide(
        "reflect::phase.reflect.memory.extract",
        ReflectMemoryExtractExecutor(governor_enabled=parsed.governor_enabled),
    )


__all__ = ["Config", "ReflectMemoryExtractExecutor", "setup"]
