"""Think-cluster assembly helpers for plan-bound graph composition."""

from __future__ import annotations

from typing import Any

from lca.cognition.brain.modular_brain import ModularBrain
from lca.cognition.brain.reasoner import PromptReasoner
from lca.contracts.capabilities import BRAIN_PROMPT_CATALOG_FACTORY, BRAINS
from lca.contracts.mechanisms import consume
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.protocols import (
    Brain,
    BrainPromptCatalog,
    BrainPromptCatalogFactory,
    DecisionGate,
    LLMAdapter,
)
from lca.contracts.protocols.journal.spec import AgentSpec
from lca.infrastructure.observability.adapters import (
    ModelVisibleLLMAdapter,
    TelemetryLLMAdapter,
)
from lca.plugins.composer.composition.skill_store import active_skill_store

_MODEL_VISIBLE_HOOK_KEY = "llm.adapter.hook.model_visible"


def instrument_llm(
    llm: LLMAdapter,
    *,
    ctx: object | None = None,
) -> LLMAdapter:
    """Wrap ``llm`` with model-visible + telemetry decorators (组合根 PR-12.5 / PR-3)。

    装配顺序(外 → 内):
        ModelVisibleHookAdapter → TelemetryLLMAdapter → inner

    PR-3 切线(ADR-0185 §5 / PR-3):当 ``ctx`` 非 None 且能从
    ``ctx.soft_get("llm.adapter.hook.model_visible")`` 拿到 PR-2
    :class:`ModelVisibleHook` 实例,改用
    :class:`ModelVisibleHookAdapter` 取代旧
    :class:`ModelVisibleLLMAdapter`,把 model-visible 落盘从
    ``<run_dir>/model_visible/step_<NN>/{...}.json`` + 旧
    ``llm.request.header`` EP 切到 ``<run_id>.spine.jsonl`` 两条 model-visible
    spine event(``spine.llm.request.header`` + ``spine.llm.request.header.assistant``)。

    ctx 缺失 / hook 未挂载 / 不支持软查 ⇒ 回退旧 wiring(测试 + 离 boot 路径)。
    双轨期(PR-3 → PR-4)用新 wiring 时旧 ``ModelVisibleLLMAdapter`` 不再被
    composer 装配(还在仓里,供单测 / 直接 import 的消费者使用);PR-4 一并删
    旧 adapter 与旁路文件。

    - LLM 调用前 hook ``capture_pre_llm`` fold 优化 + publish
      ``spine.llm.request.header``(ADR-0185 §3.5)
    - LLM 调用后 hook ``capture_post_llm`` publish
      ``spine.llm.request.header.assistant``,顺手修复 Note
      ``2026-09-03-model-visible-incomplete-projection.md`` 的 3 BUG
    - 任何 hook 缺席 / publish 抛错 ⇒ 透明透传(不写盘、不落 EP、业务继续)

    Telemetry 部分:

    - LLM 调用前后 TelemetryLLMAdapter 记 LlmCallCompleted / Otel projection /
      token usage(ADR-0169 §C7 控制/观察分离)
    """

    # 已有 TelemetryLLMAdapter 时,复用之;否则用 llm 自身
    existing_telemetry = llm._inner if isinstance(llm, TelemetryLLMAdapter) else llm
    # session_append 接线位:thinking.* Session 双写需要 per-session
    # SessionStore(lca/harness/session/store.py),它由 SessionActivator 按
    # session 创建、经 build_live_agent 传给 CognitiveLiveAgent,不注册在
    # cordis scope 上;composer 入口此处只有 scope,拿不到 per-session store,
    # 故保持 session_append=None。完整接线方式见 PR-4 同一收口:届时
    # instrument_llm 扩签名携带 session_append,在此透传给 TelemetryLLMAdapter。
    # COMPAT(delete-when: PR-4 收口完成,或 thinking.* Session 双写按
    #   TelemetryLLMAdapter._append_thinking_session_event 的删除条件退役;
    #   tracking: thinking.* Session 双写改动, 2026-09-04)
    instrumented = TelemetryLLMAdapter(existing_telemetry)
    model_name = _resolve_model_name(instrumented)

    hook = _resolve_model_visible_hook(ctx)
    if hook is not None:
        from lca.plugins.events.hooks.model_visible.adapter import (
            ModelVisibleHookAdapter,
        )

        return ModelVisibleHookAdapter(instrumented, hook)

    return ModelVisibleLLMAdapter(instrumented, model=model_name)


def _resolve_model_visible_hook(ctx: object | None) -> Any:
    """从 ``ctx`` 软查 :class:`ModelVisibleHook` 实例,无则返回 ``None``。

    兼容三种 ctx 形态(按优先级):
    1. :class:`AuditedPluginContext` / 任何实现 ``soft_get(str) -> Any | None``
       的 wrapper —— 首选(plugin setup 路径用)。
    2. cordis :class:`Context`(Composer 装配路径收到 scope 即 cordis Context)
       —— 走 :func:`collect_context_bindings` 沿 ``own_bindings`` + ``parent``
       链查;子 scope 找不到时上溯到父 scope(对齐 :meth:`Context.inject` 解析
       顺序)。
    3. ``None`` / 其它 —— 直接返回 ``None``,由 caller 走旧 wiring。
    """
    if ctx is None:
        return None
    soft_get = getattr(ctx, "soft_get", None)
    if callable(soft_get):
        try:
            return soft_get(_MODEL_VISIBLE_HOOK_KEY)
        except Exception:  # INTENTIONAL: ctx 软查失败不挡装配
            return None
    own_bindings = getattr(ctx, "own_bindings", None)
    if own_bindings is not None:
        from lca.harness.plugin_context import collect_context_bindings

        return collect_context_bindings(ctx).get(_MODEL_VISIBLE_HOOK_KEY)
    return None


def _resolve_model_name(adapter: LLMAdapter) -> str:
    """从装饰链取模型名(供 ModelVisible 记录 manifest.model)。"""
    inner = getattr(adapter, "_inner", None) or adapter
    for attr in ("_model", "model"):
        name = getattr(inner, attr, None)
        if isinstance(name, str) and name:
            return name
    return "unknown"


def resolve_brain(spec: AgentSpec, llm: LLMAdapter, *, scope: object) -> Brain:
    """Build the selected Brain with its model-visible prompt catalog.

    The active skill provider is resolved only for this Think-cluster
    concern, keeping skill discovery and prompt rendering out of
    unrelated graph composers.
    """

    if not isinstance(spec.brain, str):
        return spec.brain

    brains = require_capability(scope, BRAINS.key)
    try:
        factory = brains.resolve(spec.brain)
    except KeyError as exc:
        raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {brains.names()}") from exc

    prompt_catalog_factory = require_capability(scope, BRAIN_PROMPT_CATALOG_FACTORY.key)
    if not isinstance(prompt_catalog_factory, BrainPromptCatalogFactory):
        raise TypeError(
            "brain_prompt_catalog_factory must implement BrainPromptCatalogFactory, "
            f"got {type(prompt_catalog_factory).__name__}"
        )
    prompt_catalog = prompt_catalog_factory.create(
        skill_store=active_skill_store(scope),
        tools=spec.tools,
    )
    if not isinstance(prompt_catalog, BrainPromptCatalog):
        raise TypeError(
            "brain_prompt_catalog_factory.create must return BrainPromptCatalog, "
            f"got {type(prompt_catalog).__name__}"
        )
    brain = factory(
        consume("llm", llm, PromptReasoner),
        spec.profile,
        prompt_catalog,
        tools=list(spec.tools),
    )
    if not isinstance(brain, Brain):
        raise TypeError(
            f"brain factory {spec.brain!r} produced {type(brain).__name__}, expected Brain"
        )
    return brain


def apply_lead_brain(brain: Brain, decision_gate: DecisionGate) -> Brain:
    """Return a lead Brain whose closed-set gate is installed explicitly."""

    if not isinstance(brain, ModularBrain):
        raise TypeError(f"lead composition requires ModularBrain (got {type(brain).__name__})")
    return ModularBrain(
        reasoner=brain.reasoner,
        reducer=brain.reducer,
        classifier=brain.classifier,
        critic=brain.critic,
        skill_router=brain.skill_router,
        decision_gate=decision_gate,
        agent_gates=brain.agent_gates,
        think_pipeline=brain.think_pipeline,
        reflection_pipeline=brain.reflection_pipeline,
    )


__all__ = ["apply_lead_brain", "instrument_llm", "resolve_brain"]
