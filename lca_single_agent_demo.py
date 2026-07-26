"""
LCA Framework —— 单 Agent 回答单一问题：L0 → L4 端到端参考实现
================================================================

本文件是架构文档"核心数据结构与协议"一节（第5节）与"Runtime Loop"一节
（第6节）的可运行落地版本。为保证在任意环境下无需额外依赖即可直接运行，
本参考实现用标准库 dataclasses 替代文档中 Pydantic 风格的契约定义；
生产环境请按第5节把每个 dataclass 替换为对应的 pydantic.BaseModel，
接口方法签名保持不变。

运行方式：
    python3 lca_single_agent_demo.py

层级对照（自下而上，与文档第2节总览图一一对应）：
    L0  基础设施层   —— LLMAdapter / ToolProtocol / StateStore / Observability
    L1  认知组件层   —— Brain(MAP+Reasoner+Critic+DecisionParser) / Body / MemorySystem / EventBus / PromptManager / HookRegistry
    L2  认知运行时层 —— CognitiveRuntime（核心循环）
    L3  Agent抽象层  —— BaseAgent
    L4  应用/编排层  —— Agent(...) 极简入口
"""

from __future__ import annotations

import ast
import asyncio
import json
import operator
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ============================================================================
# 第5节：核心数据结构（dataclass 版契约；生产环境替换为 pydantic.BaseModel）
# ============================================================================

@dataclass
class Budget:
    max_tokens: Optional[int] = None
    max_cost_usd: Optional[float] = None
    max_steps: Optional[int] = None
    max_wall_clock_seconds: Optional[int] = None
    used_tokens: int = 0
    used_cost_usd: float = 0.0
    used_steps: int = 0
    started_at: datetime = field(default_factory=now)
    extra: dict[str, Any] = field(default_factory=dict)

    def exceeded(self) -> bool:
        if self.max_steps is not None and self.used_steps > self.max_steps:
            return True
        if self.max_wall_clock_seconds is not None:
            elapsed = (now() - self.started_at).total_seconds()
            if elapsed > self.max_wall_clock_seconds:
                return True
        return False


@dataclass
class StateSnapshot:
    snapshot_id: str
    step: int
    state_ref: str
    reason: Literal["periodic", "pre_approval", "manual", "on_error"]
    created_at: datetime = field(default_factory=now)


@dataclass
class MemoryRecord:
    record_id: str
    content: str
    memory_type: Literal["working", "semantic", "episodic", "procedural"]
    importance: float
    recency_score: Optional[float] = None
    source_trace_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TypedState:
    trace_id: str
    task: str
    budget: Budget
    schema_version: str = "1.0"
    working_memory: dict[str, Any] = field(default_factory=dict)
    retrieved_context: list[MemoryRecord] = field(default_factory=list)
    step: int = 0
    checkpoints: list[StateSnapshot] = field(default_factory=list)
    status: Literal["running", "paused", "waiting_human", "completed", "failed"] = "running"
    extra: dict[str, Any] = field(default_factory=dict)

    def snapshot(self, reason: str = "periodic") -> StateSnapshot:
        snap = StateSnapshot(
            snapshot_id=new_id("snap"),
            step=self.step,
            state_ref=f"mem://{self.trace_id}/{self.step}",
            reason=reason,  # type: ignore[arg-type]
        )
        self.checkpoints.append(snap)
        return snap


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base_s: float = 0.05
    backoff_multiplier: float = 2.0
    retryable_errors: list[str] = field(default_factory=list)


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl_s: int = 300
    key_fields: list[str] = field(default_factory=list)


@dataclass
class ToolPermissionManifest:
    allowed_tools: list[str]
    max_calls_per_task: dict[str, int] = field(default_factory=dict)
    requires_approval: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    idempotency_key: Optional[str] = None
    timeout_s: Optional[int] = None


@dataclass
class DelegationSpec:
    subtask: str
    target_role: Optional[str] = None
    target_agent_id: Optional[str] = None
    context_refs: list[str] = field(default_factory=list)
    protocol: Literal["internal", "a2a", "mcp"] = "internal"


@dataclass
class StructuredDecision:
    decision_id: str
    action_type: Literal["use_tool", "delegate", "respond", "ask_human", "stop"]
    rationale: str
    confidence: float
    tool_call: Optional[ToolCall] = None
    delegate_to: Optional[DelegationSpec] = None
    response_text: Optional[str] = None
    schema_version: str = "1.0"
    created_at: datetime = field(default_factory=now)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    observation_id: str
    success: bool
    payload: Any
    tool_call_id: Optional[str] = None
    error: Optional[str] = None
    retries_used: int = 0
    latency_ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Reflection:
    reflection_id: str
    verdict: Literal["on_track", "needs_correction", "blocked"]
    lesson: Optional[str] = None
    correction: Optional[StructuredDecision] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleProfile:
    role: str
    goal: str
    backstory: str
    tool_permission_manifest: ToolPermissionManifest
    tone: Optional[str] = None
    values: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceSpan:
    span_id: str
    trace_id: str
    name: str
    started_at: datetime
    parent_span_id: Optional[str] = None
    ended_at: Optional[datetime] = None
    status: Literal["ok", "error"] = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    trace_id: str
    status: Literal["completed", "failed", "paused", "waiting_human"]
    final_state_ref: str
    total_steps: int
    budget_used: Budget
    schema_version: str = "1.0"
    output: Optional[str] = None
    lessons: list[str] = field(default_factory=list)
    trace_url: Optional[str] = None
    error: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


class ApprovalPendingError(Exception):
    def __init__(self, approval_request: Any):
        self.approval_request = approval_request
        super().__init__("waiting for human approval")


class BudgetExceededError(Exception):
    pass


class ToolExecutionError(Exception):
    def __init__(self, message: str, last_observation: Optional[Observation] = None):
        self.last_observation = last_observation
        super().__init__(message)


# ============================================================================
# 第5.11节：关键协议接口（Protocol）—— dataclass 版契约对应的行为契约
# ============================================================================

class LLMAdapter(Protocol):
    async def complete(self, prompt: str, **kwargs: Any) -> str: ...


class ToolProtocol(Protocol):
    name: str
    is_idempotent: bool
    default_timeout_s: int

    async def execute(self, args: dict[str, Any]) -> Observation: ...


class Reasoner(Protocol):
    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]: ...


class DecisionParser(Protocol):
    def parse(self, raw_output: str, state: TypedState) -> StructuredDecision: ...


class Critic(Protocol):
    async def critique(self, state: TypedState, observation: Observation) -> Reflection: ...


class TaskDecomposer(Protocol):
    async def decompose(self, state: TypedState) -> list[str]: ...


class StatePredictor(Protocol):
    async def predict(self, state: TypedState, candidate_action: str) -> dict[str, Any]: ...


class StateEvaluator(Protocol):
    async def score(self, state: TypedState, predicted_state: dict[str, Any]) -> float: ...


class ConflictMonitor(Protocol):
    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]: ...


class TaskCoordinator(Protocol):
    async def arbitrate(
        self, state: TypedState, candidates: list[StructuredDecision], scores: list[float]
    ) -> StructuredDecision: ...


class BrainStrategy(Protocol):
    async def think(self, state: TypedState) -> StructuredDecision: ...
    async def reflect(self, state: TypedState, observation: Observation) -> Reflection: ...


class Body(Protocol):
    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation: ...


class MemorySystem(Protocol):
    async def perceive_and_retrieve(self, state: TypedState) -> TypedState: ...
    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None: ...


class EventBus(Protocol):
    def emit(self, event_name: str, payload: Any, trace_id: str) -> None: ...
    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None: ...


class PromptManager(Protocol):
    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...
    def register_template(self, name: str, template: str, version: str = "1.0") -> None: ...


class ToolRegistryP(Protocol):
    def register(self, tool: ToolProtocol) -> None: ...
    def get(self, name: str) -> Optional[ToolProtocol]: ...


class SafeExecutorProtocol(Protocol):
    async def execute(
        self, tool: ToolProtocol, args: dict[str, Any], retry_policy: RetryPolicy, cache_config: CacheConfig
    ) -> Observation: ...


class StateStore(Protocol):
    async def save(self, state: TypedState) -> str: ...
    async def load(self, state_ref: str) -> TypedState: ...


class Hook(Protocol):
    async def __call__(self, event_name: str, state: TypedState, **kwargs: Any) -> None: ...


class HookRegistryP(Protocol):
    def register(self, event_name: str, hook: Hook) -> None: ...
    async def trigger(self, event_name: str, state: TypedState, **kwargs: Any) -> Any: ...


class Observability(Protocol):
    def emit_span(self, span: TraceSpan) -> None: ...


class Runtime(Protocol):
    async def run(self, task: str, max_steps: int) -> Result: ...


# ============================================================================
# L0 · 基础设施层
# ============================================================================

class MockLLMAdapter:
    """离线可跑的确定性 Mock 实现，用于本示例；接口与真实厂商适配器完全一致。"""

    name = "mock-llm"

    _WEATHER_CITIES = {
        "东京": "Tokyo", "tokyo": "Tokyo",
        "北京": "Beijing", "beijing": "Beijing",
        "旧金山": "San Francisco", "san francisco": "San Francisco",
        "纽约": "New York", "new york": "New York",
        "伦敦": "London", "london": "London",
    }

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        await asyncio.sleep(0)  # 模拟异步I/O让出事件循环
        if "TOOL_RESULT:" in prompt:
            m = re.search(r"TOOL_RESULT:\s*([^\n]+)", prompt)
            tool_result = m.group(1).strip() if m else "未知"
            question = re.search(r"USER_TASK:\s*([^\n]+)", prompt)
            q = question.group(1).strip() if question else ""
            return json.dumps({
                "action_type": "respond",
                "response_text": f"「{q}」的答案是 {tool_result}。",
                "rationale": "已从工具获得结果，直接向用户作答，无需进一步调用工具。",
                "confidence": 0.98,
            }, ensure_ascii=False)

        city = self._extract_weather_city(prompt)
        if city:
            return json.dumps({
                "action_type": "use_tool",
                "tool_name": "get_weather",
                "arguments": {"city": city, "unit": "celsius"},
                "rationale": f"用户询问天气，应调用 get_weather 工具查询 {city}。",
                "confidence": 0.95,
            }, ensure_ascii=False)

        expr = self._extract_arithmetic_expression(prompt)
        if expr:
            return json.dumps({
                "action_type": "use_tool",
                "tool_name": "calculator",
                "arguments": {"expression": expr},
                "rationale": f"用户问题是纯算术计算（{expr}），应调用 calculator 工具求精确值而非直接臆测。",
                "confidence": 0.95,
            }, ensure_ascii=False)

        return json.dumps({
            "action_type": "respond",
            "response_text": "这是一个通用问题，暂无可用工具，基于已有知识直接作答。",
            "rationale": "未检测到需要调用工具的模式，直接生成回答。",
            "confidence": 0.6,
        }, ensure_ascii=False)

    @classmethod
    def _extract_weather_city(cls, prompt: str) -> Optional[str]:
        m = re.search(r"USER_TASK:\s*([^\n]+)", prompt)
        if not m:
            return None
        text = m.group(1)
        if not re.search(r"天气|气温|温度|weather|temp", text, re.IGNORECASE):
            return None
        for keyword, city in cls._WEATHER_CITIES.items():
            if keyword in text.lower():
                return city
        return None

    @staticmethod
    def _extract_arithmetic_expression(prompt: str) -> Optional[str]:
        m = re.search(r"USER_TASK:\s*([^\n]+)", prompt)
        if not m:
            return None
        text = m.group(1)
        text = text.replace("乘以", "*").replace("加上", "+").replace("减去", "-").replace("除以", "/")
        text = text.replace("×", "*").replace("÷", "/")
        nums_ops = re.findall(r"[\d.]+|[+\-*/]", text)
        if len(nums_ops) >= 3:
            return "".join(nums_ops)
        return None


class OpenAICompatAdapter:
    """通用 OpenAI 兼容 LLM 适配器。

    支持 OpenAI / DashScope / Ollama / vLLM 等所有 chat.completions 兼容 API。
    只需配置环境变量即可切换，代码无需改动：
        LLM_API_KEY   API Key
        LLM_BASE_URL  基地址（默认 https://api.openai.com/v1）
        LLM_MODEL     模型名（默认 gpt-4.1）
    """

    def __init__(
        self,
        model: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        from openai import AsyncOpenAI
        self._model = model or os.getenv("LLM_MODEL", "gpt-4.1")
        self._client = AsyncOpenAI(
            api_key=api_key or os.getenv("LLM_API_KEY", ""),
            base_url=base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        )

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        response = await self._client.chat.completions.create(
            model=kwargs.pop("model", self._model),
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.pop("temperature", 0.7),
            max_tokens=kwargs.pop("max_tokens", 2048),
            **kwargs,
        )
        return response.choices[0].message.content or ""


class CalculatorTool:
    """实现 ToolProtocol 的示例工具：安全求值四则运算表达式（不使用 eval，杜绝任意代码执行）。"""

    name = "calculator"
    is_idempotent = True
    default_timeout_s = 5

    _OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg,
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        expr = args.get("expression", "")
        try:
            value = self._safe_eval(expr)
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"), success=True, payload=value, latency_ms=latency_ms
            )
        except Exception as e:  # noqa: BLE001
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"), success=False, payload=None,
                error=str(e), latency_ms=latency_ms,
            )

    def _safe_eval(self, expr: str) -> float:
        node = ast.parse(expr, mode="eval").body
        return self._eval_node(node)

    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._OPS:
            return self._OPS[type(node.op)](self._eval_node(node.left), self._eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._OPS:
            return self._OPS[type(node.op)](self._eval_node(node.operand))
        raise ValueError(f"不支持的表达式片段: {ast.dump(node)}")


class GetWeatherTool:
    """实现 ToolProtocol 的天气查询工具（内置假数据，无需外部网络）。"""

    name = "get_weather"
    is_idempotent = True
    default_timeout_s = 5

    _FAKE_DB: dict[str, dict[str, Any]] = {
        "tokyo": {"temp_c": 27, "condition": "cloudy"},
        "beijing": {"temp_c": 31, "condition": "sunny"},
        "san francisco": {"temp_c": 18, "condition": "foggy"},
        "new york": {"temp_c": 24, "condition": "clear"},
        "london": {"temp_c": 19, "condition": "rainy"},
    }
    _CITY_ALIASES: dict[str, str] = {
        "东京": "tokyo", "東京": "tokyo",
        "北京": "beijing",
        "旧金山": "san francisco",
        "纽约": "new york",
        "伦敦": "london",
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        raw_city = str(
            args.get("city") or args.get("location") or args.get("name") or ""
        ).strip().lower()
        city = self._CITY_ALIASES.get(raw_city, raw_city)

        if not city:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"), success=False, payload=None,
                error="missing required arg: city", latency_ms=latency_ms,
            )

        await asyncio.sleep(0.05)  # 模拟网络 IO

        data = self._FAKE_DB.get(city)
        if data is None:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"), success=False, payload=None,
                error=f"unknown city: {city}", latency_ms=latency_ms,
            )

        unit = str(args.get("unit", "celsius")).lower()
        temp_c = data["temp_c"]
        temp = temp_c if unit == "celsius" else temp_c * 9 / 5 + 32

        result = {
            "city": city,
            "temperature": round(temp, 1),
            "unit": unit,
            "condition": data["condition"],
        }
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"), success=True, payload=result,
            latency_ms=latency_ms,
        )



class InMemoryStateStore:
    def __init__(self) -> None:
        self._store: dict[str, TypedState] = {}

    async def save(self, state: TypedState) -> str:
        ref = f"mem://{state.trace_id}/{state.step}"
        self._store[ref] = state
        return ref

    async def load(self, state_ref: str) -> TypedState:
        return self._store[state_ref]


class ConsoleObservability:
    """默认可观测实现：把每个跨层调用输出为结构化 TraceSpan（第5.9节契约）。"""

    def emit_span(self, span: TraceSpan) -> None:
        dur = None
        if span.ended_at:
            dur = int((span.ended_at - span.started_at).total_seconds() * 1000)
        print(f"  [TraceSpan] {span.name:<28} status={span.status:<5} dur_ms={dur} attrs={span.attributes}")


# ============================================================================
# L1 · 认知组件层
# ============================================================================

class SimplePromptManager:
    def __init__(self) -> None:
        self._templates: dict[str, str] = {}

    def register_template(self, name: str, template: str, version: str = "1.0") -> None:
        self._templates[name] = template

    def render(self, template_name: str, variables: dict[str, Any]) -> str:
        return self._templates[template_name].format(**variables)


DEFAULT_REACT_TEMPLATE = """\
ROLE: {role}
GOAL: {goal}
BACKSTORY: {backstory}
AVAILABLE_TOOLS: {tools}
USER_TASK: {task}
CONTEXT:
{context}

请以 JSON 输出下一步 StructuredDecision（字段：action_type/tool_name/arguments/response_text/rationale/confidence）。
"""


class SimpleEventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Any], Awaitable[None]]]] = {}

    def emit(self, event_name: str, payload: Any, trace_id: str) -> None:
        for handler in self._subs.get(event_name, []):
            asyncio.create_task(handler({"event_name": event_name, "payload": payload, "trace_id": trace_id}))

    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        self._subs.setdefault(event_name, []).append(handler)


class SimpleHookRegistry:
    def __init__(self, observability: Observability) -> None:
        self._hooks: dict[str, list[Hook]] = {}
        self.observability = observability

    def register(self, event_name: str, hook: Hook) -> None:
        self._hooks.setdefault(event_name, []).append(hook)

    async def trigger(self, event_name: str, state: TypedState, **kwargs: Any) -> Any:
        span = TraceSpan(span_id=new_id("span"), trace_id=state.trace_id, name=f"hook.{event_name}", started_at=now())
        for hook in self._hooks.get(event_name, []):
            await hook(event_name, state, **kwargs)
        span.ended_at = now()
        self.observability.emit_span(span)
        return None


async def default_logging_hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
    extra = {k: v for k, v in kwargs.items() if k != "state"}
    print(f"  [Hook] {event_name} @step={state.step} {extra if extra else ''}")


class SimpleToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolProtocol] = {}

    def register(self, tool: ToolProtocol) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolProtocol]:
        return self._tools.get(name)


class SimpleSafeExecutor:
    """权限校验 -> 缓存命中 -> 重试装饰 -> 沙箱执行（第4.1/9节内部链路）。"""

    def __init__(self, permission_manifest: ToolPermissionManifest, observability: Observability):
        self.permission_manifest = permission_manifest
        self.observability = observability
        self._cache: dict[str, Observation] = {}

    async def execute(
        self, tool: ToolProtocol, args: dict[str, Any], retry_policy: RetryPolicy, cache_config: CacheConfig
    ) -> Observation:
        if tool.name not in self.permission_manifest.allowed_tools:
            raise ToolExecutionError(f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权")

        cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if cache_config.enabled and cache_key in self._cache:
            return self._cache[cache_key]

        last_obs: Optional[Observation] = None
        delay = retry_policy.backoff_base_s
        for attempt in range(retry_policy.max_retries + 1):
            span = TraceSpan(span_id=new_id("span"), trace_id="", name=f"tool.{tool.name}", started_at=now())
            obs = await tool.execute(args)
            span.ended_at = now()
            span.status = "ok" if obs.success else "error"
            self.observability.emit_span(span)
            if obs.success:
                if cache_config.enabled:
                    self._cache[cache_key] = obs
                return obs
            last_obs = obs
            if attempt < retry_policy.max_retries:
                await asyncio.sleep(delay)
                delay *= retry_policy.backoff_multiplier

        raise ToolExecutionError(f"工具 {tool.name} 重试 {retry_policy.max_retries} 次后仍失败", last_obs)


class SimpleBody:
    """L1 Body：ToolRegistry + SafeExecutor，对外只暴露 act()。"""

    def __init__(self, tool_registry: ToolRegistryP, safe_executor: SafeExecutorProtocol):
        self.tool_registry = tool_registry
        self.safe_executor = safe_executor

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation:
        if decision.action_type == "respond":
            return Observation(observation_id=new_id("obs"), success=True, payload=decision.response_text)

        if decision.action_type == "use_tool":
            assert decision.tool_call is not None
            tool = self.tool_registry.get(decision.tool_call.tool_name)
            if tool is None:
                raise ToolExecutionError(f"未注册工具: {decision.tool_call.tool_name}")
            return await self.safe_executor.execute(
                tool, decision.tool_call.arguments, RetryPolicy(), CacheConfig()
            )

        raise ToolExecutionError(f"本示例暂未处理的 action_type: {decision.action_type}")


# ---- Brain 内部：MAP 五模块 + Reasoner + Critic + DecisionParser ----------

class SimpleReasoner:
    def __init__(self, llm: LLMAdapter, prompt_manager: PromptManager, role_profile: RoleProfile, tools_desc: str):
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.role_profile = role_profile
        self.tools_desc = tools_desc

    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]:
        context_lines = "\n".join(f"- [{r.memory_type}] {r.content}" for r in state.retrieved_context) or "(无历史上下文)"
        prompt = self.prompt_manager.render("react_prompt", {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
        })
        raw = await self.llm.complete(prompt)
        return [raw]


class SimpleDecisionParser:
    _ACTION_ALIASES = {
        "tool_call": "use_tool",
        "call_tool": "use_tool",
        "use_tool": "use_tool",
        "respond": "respond",
        "response": "respond",
        "answer": "respond",
        "reply": "respond",
        "delegate": "delegate",
        "stop": "stop",
        "ask_human": "ask_human",
    }

    def parse(self, raw_output: str, state: TypedState) -> StructuredDecision:
        json_str = self._extract_json(raw_output)
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return StructuredDecision(
                decision_id=new_id("dec"), action_type="respond",
                response_text=raw_output, rationale="解析失败兜底", confidence=0.1,
            )

        raw_action = str(data.get("action_type", "respond")).lower().strip()
        action_type = self._ACTION_ALIASES.get(raw_action, raw_action)

        tool_call = None
        if action_type == "use_tool":
            tool_name = data.get("tool_name") or data.get("tool") or self._infer_tool_name(raw_output)
            arguments = data.get("arguments") or data.get("args") or data.get("parameters") or {}
            if not isinstance(arguments, dict):
                arguments = {"expression": str(arguments)}
            if tool_name:
                tool_call = ToolCall(
                    call_id=new_id("call"),
                    tool_name=tool_name,
                    arguments=arguments,
                )
            else:
                action_type = "respond"

        return StructuredDecision(
            decision_id=new_id("dec"),
            action_type=action_type,  # type: ignore[arg-type]
            tool_call=tool_call,
            response_text=data.get("response_text") or data.get("response") or data.get("text"),
            rationale=data.get("rationale", ""),
            confidence=float(data.get("confidence", 0.5)),
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        """从可能包含 markdown 代码块的文本中提取 JSON。"""
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)
        return text.strip()

    @staticmethod
    def _infer_tool_name(text: str) -> Optional[str]:
        """从 LLM 的 rationale 文本中推断工具名。"""
        if re.search(r"calculator|计算|算术|表达式", text, re.IGNORECASE):
            return "calculator"
        if re.search(r"get_weather|weather|天气|气温", text, re.IGNORECASE):
            return "get_weather"
        return None


class SimpleCritic:
    async def critique(self, state: TypedState, observation: Observation) -> Reflection:
        if observation.success:
            return Reflection(
                reflection_id=new_id("refl"), verdict="on_track",
                lesson=f"步骤{state.step}成功完成" if observation.payload is not None else None,
            )
        return Reflection(
            reflection_id=new_id("refl"), verdict="needs_correction",
            lesson=f"步骤{state.step}失败: {observation.error}",
        )


class SimpleTaskDecomposer:
    async def decompose(self, state: TypedState) -> list[str]:
        return [state.task]  # 单步问答场景：无需真正拆解


class SimpleStatePredictor:
    async def predict(self, state: TypedState, candidate_action: str) -> dict[str, Any]:
        return {"expected_effect": candidate_action}


class SimpleStateEvaluator:
    async def score(self, state: TypedState, predicted_state: dict[str, Any]) -> float:
        return 1.0  # 单候选场景，评分仅用于保持MAP协作链路完整


class SimpleConflictMonitor:
    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]:
        return []


class SimpleTaskCoordinator:
    async def arbitrate(
        self, state: TypedState, candidates: list[StructuredDecision], scores: list[float]
    ) -> StructuredDecision:
        best_idx = max(range(len(candidates)), key=lambda i: scores[i])
        return candidates[best_idx]


class ModularBrain:
    """
    实现 BrainStrategy 协议：think() 内部串联
    Reasoner -> TaskDecomposer -> StatePredictor -> StateEvaluator -> ConflictMonitor -> TaskCoordinator -> DecisionParser，
    reflect() 内部调用 Critic（第4.1节 L1 内部调用链路图的逐行落地）。
    """

    def __init__(
        self,
        reasoner: Reasoner,
        decision_parser: DecisionParser,
        critic: Critic,
        task_decomposer: TaskDecomposer,
        state_predictor: StatePredictor,
        state_evaluator: StateEvaluator,
        conflict_monitor: ConflictMonitor,
        task_coordinator: TaskCoordinator,
    ):
        self.reasoner = reasoner
        self.decision_parser = decision_parser
        self.critic = critic
        self.task_decomposer = task_decomposer
        self.state_predictor = state_predictor
        self.state_evaluator = state_evaluator
        self.conflict_monitor = conflict_monitor
        self.task_coordinator = task_coordinator

    async def think(self, state: TypedState) -> StructuredDecision:
        _subtasks = await self.task_decomposer.decompose(state)
        raw_candidates = await self.reasoner.generate_candidates(state, n=1)
        candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]

        predicted = [await self.state_predictor.predict(state, c.rationale) for c in candidates]
        scores = [await self.state_evaluator.score(state, p) for p in predicted]
        conflicts = await self.conflict_monitor.check(state, candidates)
        if conflicts:
            print(f"  [ConflictMonitor] 检测到冲突: {conflicts}")

        return await self.task_coordinator.arbitrate(state, candidates, scores)

    async def reflect(self, state: TypedState, observation: Observation) -> Reflection:
        return await self.critic.critique(state, observation)


class SimpleMemorySystem:
    """四类记忆的最小实现：内存列表存储 + 简单相关性检索。"""

    def __init__(self) -> None:
        self._layers: dict[str, list[MemoryRecord]] = {
            "working": [], "semantic": [], "episodic": [], "procedural": [],
        }

    async def perceive_and_retrieve(self, state: TypedState) -> TypedState:
        records: list[MemoryRecord] = []
        for layer in self._layers.values():
            records.extend(layer)
        state.retrieved_context = records
        return state

    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None:
        if observation.payload is not None and observation.success:
            self._layers["working"] = [MemoryRecord(
                record_id=new_id("mem"),
                content=f"TOOL_RESULT: {observation.payload}",
                memory_type="working", importance=0.9, source_trace_id=state.trace_id,
            )]
        self._layers["episodic"].append(MemoryRecord(
            record_id=new_id("mem"),
            content=f"step={state.step} success={observation.success} verdict={reflection.verdict}",
            memory_type="episodic", importance=0.5, source_trace_id=state.trace_id,
        ))
        await self.compress()

    async def compress(self) -> None:
        max_episodic = 50
        if len(self._layers["episodic"]) > max_episodic:
            self._layers["episodic"] = self._layers["episodic"][-max_episodic:]


# ============================================================================
# L2 · 认知运行时层 —— CognitiveRuntime（核心 Loop，第6节参考实现的可运行版本）
# ============================================================================

class CognitiveRuntime:
    def __init__(
        self,
        brain: BrainStrategy,
        body: Body,
        memory: MemorySystem,
        hooks: HookRegistryP,
        event_bus: EventBus,
        state_store: StateStore,
    ):
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.event_bus = event_bus
        self.state_store = state_store

    def default_budget(self) -> Budget:
        return Budget(max_steps=10, max_wall_clock_seconds=30)

    async def run(self, task: str, max_steps: int = 10) -> Result:
        state = TypedState(trace_id=new_id("trace"), task=task, budget=self.default_budget())
        await self.hooks.trigger("on_start", state)
        return await self._loop(state, max_steps)

    async def resume(self, snapshot: StateSnapshot, max_steps: int = 10) -> Result:
        state = await self.state_store.load(snapshot.state_ref)
        state.status = "running"
        return await self._loop(state, max_steps)

    async def _loop(self, state: TypedState, max_steps: int) -> Result:
        decision: Optional[StructuredDecision] = None
        reflection: Optional[Reflection] = None

        for step in range(state.step, max_steps):
            state.step = step
            state.budget.used_steps = step
            try:
                await self.hooks.trigger("pre_perceive", state)
                state = await self.memory.perceive_and_retrieve(state)

                await self.hooks.trigger("pre_think", state)
                decision = await self.brain.think(state)
                await self.hooks.trigger("post_think", state, decision=decision)

                await self.hooks.trigger("pre_act", state, decision=decision)
                observation = await self.body.act(decision, state)
                await self.hooks.trigger("post_act", state, observation=observation)

                if decision.action_type == "respond":
                    state.working_memory["final_output"] = decision.response_text

                await self.hooks.trigger("pre_reflect", state, observation=observation)
                reflection = await self.brain.reflect(state, observation)
                await self.hooks.trigger("post_reflect", state, reflection=reflection)

                await self.memory.update_multi_level(state, observation, reflection)

            except ApprovalPendingError:
                state.status = "waiting_human"
                state.checkpoints.append(state.snapshot(reason="pre_approval"))
                await self.hooks.trigger("on_pause", state)
                return self._summarize(state)

            except Exception as err:  # noqa: BLE001
                await self.hooks.trigger("on_error", state, error=err)
                state.status = "failed"
                state.checkpoints.append(state.snapshot(reason="on_error"))
                state.extra["error"] = str(err)
                break

            state.checkpoints.append(state.snapshot())
            self.event_bus.emit("step_completed", {"step": state.step, "status": state.status}, state.trace_id)

            if state.budget.exceeded():
                await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                state.status = "failed"
                break

            if self._should_stop(decision, reflection):
                state.status = "completed"
                break

        await self.hooks.trigger("on_complete", state)
        return self._summarize(state)

    def _should_stop(self, decision: Optional[StructuredDecision], reflection: Optional[Reflection]) -> bool:
        if decision is None or reflection is None:
            return False
        return decision.action_type == "respond" and reflection.verdict != "needs_correction"

    def _summarize(self, state: TypedState) -> Result:
        final_ref = f"mem://{state.trace_id}/{state.step}"
        return Result(
            trace_id=state.trace_id,
            status=state.status if state.status != "running" else "completed",  # type: ignore[arg-type]
            output=state.working_memory.get("final_output"),
            final_state_ref=final_ref,
            total_steps=state.step + 1,
            budget_used=state.budget,
            error=state.extra.get("error"),
        )


# ============================================================================
# L3 · Agent抽象层
# ============================================================================

class BaseAgent:
    def __init__(self, runtime: Runtime, role_profile: RoleProfile, max_steps: int = 10):
        self.runtime = runtime
        self.role_profile = role_profile
        self.max_steps = max_steps

    async def execute(self, task: str) -> Result:
        return await self.runtime.run(task, max_steps=self.max_steps)


# ============================================================================
# L4 · 应用/编排层 —— 极简开发者 API
# ============================================================================

class Agent:
    """三行上手的开发者入口：内部完成 L0-L3 全部对象的 DI 组装。"""

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        tools: list[ToolProtocol],
        llm: LLMAdapter,
        max_steps: int = 10,
    ):
        permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
        role_profile = RoleProfile(role=role, goal=goal, backstory=backstory, tool_permission_manifest=permission_manifest)

        observability = ConsoleObservability()
        prompt_manager = SimplePromptManager()
        prompt_manager.register_template("react_prompt", DEFAULT_REACT_TEMPLATE)

        tool_registry = SimpleToolRegistry()
        for t in tools:
            tool_registry.register(t)
        tools_desc = ", ".join(f"{t.name}" for t in tools) or "(无可用工具)"

        safe_executor = SimpleSafeExecutor(permission_manifest, observability)
        body = SimpleBody(tool_registry, safe_executor)

        reasoner = SimpleReasoner(llm, prompt_manager, role_profile, tools_desc)
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
            task_decomposer=SimpleTaskDecomposer(),
            state_predictor=SimpleStatePredictor(),
            state_evaluator=SimpleStateEvaluator(),
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
        )

        memory = SimpleMemorySystem()
        hooks = SimpleHookRegistry(observability)
        for event_name in [
            "on_start", "pre_perceive", "pre_think", "post_think", "pre_act",
            "post_act", "pre_reflect", "post_reflect", "on_error", "on_pause", "on_complete",
        ]:
            hooks.register(event_name, default_logging_hook)

        event_bus = SimpleEventBus()
        state_store = InMemoryStateStore()

        runtime = CognitiveRuntime(brain, body, memory, hooks, event_bus, state_store)
        self._base_agent = BaseAgent(runtime, role_profile, max_steps=max_steps)

    async def run(self, task: str) -> Result:
        return await self._base_agent.execute(task)


# ============================================================================
# 演示：一个 Agent 回答一个问题（L4 -> L3 -> L2 -> L1 -> L0 全链路串联）
# ============================================================================

def _load_env() -> None:
    """从 /home/lichao/zero-agent/.env 加载环境变量（不依赖 python-dotenv）。"""
    env_path = "/home/lichao/zero-agent/.env"
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _make_agent(llm: Optional[LLMAdapter] = None) -> Agent:
    if llm is None:
        llm = MockLLMAdapter()
    return Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算和天气查询，不臆测数值结果。",
        tools=[CalculatorTool(), GetWeatherTool()],
        llm=llm,
    )


async def main() -> None:
    _load_env()

    api_key = os.getenv("LLM_API_KEY", "")
    if api_key:
        print(f"[配置] LLM={os.getenv('LLM_MODEL', 'gpt-4.1')} base_url={os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1')}")
        llm: LLMAdapter = OpenAICompatAdapter()
    else:
        print("[配置] 未检测到 LLM_API_KEY，降级使用 MockLLMAdapter")
        llm = MockLLMAdapter()

    # 场景 1：算术计算
    print("=" * 70)
    print("场景 1：agent.run('123 乘以 456 等于多少？')")
    print("=" * 70)
    result = await _make_agent(llm).run("123 乘以 456 等于多少？")
    _print_result(result)

    # 场景 2：天气查询
    print()
    print("=" * 70)
    print("场景 2：agent.run('东京现在天气怎么样？')")
    print("=" * 70)
    result = await _make_agent(llm).run("东京现在天气怎么样？")
    _print_result(result)

    # 场景 3：直接并发跑两个工具，验证它们能在同一轮里被同时触发
    print()
    print("=" * 70)
    print("场景 3：并发调用 get_weather + calculator（直接验证工具层）")
    print("=" * 70)
    weather_obs, calc_obs = await asyncio.gather(
        GetWeatherTool().execute({"city": "Tokyo", "unit": "celsius"}),
        CalculatorTool().execute({"expression": "240*0.15"}),
    )
    print(f"  get_weather  → success={weather_obs.success}  payload={weather_obs.payload}  latency={weather_obs.latency_ms}ms")
    print(f"  calculator   → success={calc_obs.success}  payload={calc_obs.payload}  latency={calc_obs.latency_ms}ms")
    print("=" * 70)


def _print_result(result: Result) -> None:
    print(f"  status      = {result.status}")
    print(f"  output      = {result.output}")
    print(f"  total_steps = {result.total_steps}")
    print(f"  used_steps  = {result.budget_used.used_steps}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
