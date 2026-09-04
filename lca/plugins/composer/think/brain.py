"""Think-cluster assembly helpers for plan-bound graph composition."""

from __future__ import annotations

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


def instrument_llm(llm: LLMAdapter) -> LLMAdapter:
    """Wrap ``llm`` with model_visible + telemetry decorators (组合根 PR-12.5)。

    装配顺序(外 → 内):
        ModelVisibleLLMAdapter → TelemetryLLMAdapter → inner

    这样:
    - LLM 调用前先落 ``model_visible/step_<NN>/{...}.json`` + 1 条
      ``llm.request.header`` EP(ADR-0169 D7 + I-MV1)
    - 然后 TelemetryLLMAdapter 记 LlmCallCompleted / Otel projection / token
      usage(ADR-0169 §C7 控制/观察分离)
    - 任何 capture 缺失(profile 关闭 model_visible)cursor + capture contextvar
      未绑 ⇒ 透明透传(不写盘、不落 EP,业务继续)

    # TODO(ADR-0185 PR-4, tracking: PR-4 delete-when):composer 装配
    # 入口缺乏 PluginContext,无法在 instrument_llm 时从
    # ``ctx.soft_get("llm.adapter.hook.model_visible")`` 拿到 PR-2
    # ``ModelVisibleHook`` 实例。PR-3 不切:旧 ``ModelVisibleLLMAdapter``
    # 装饰链仍工作(旁路文件 + 旧 EP),新 ``ModelVisiblePublisher`` plugin
    # setup 后处于未挂载态(双轨期业务侧走旧 capture 路径,viewer 走新
    # fold 路径读取 spine.jsonl)。PR-4 收口时一并改造 composer:
    # 把 ``instrument_llm`` 签名扩成 ``(llm, *, ctx: PluginContext | None)``,
    # 优先 ctx.soft_get('llm.adapter.hook.model_visible') 走 fold 路径,
    # ctx=None 时回退旧 wiring(测试 / 离 boot 路径)。
    """

    # 已有 TelemetryLLMAdapter 时,复用之;否则用 llm 自身
    existing_telemetry = llm._inner if isinstance(llm, TelemetryLLMAdapter) else llm
    instrumented = TelemetryLLMAdapter(existing_telemetry)
    model_name = _resolve_model_name(instrumented)
    return ModelVisibleLLMAdapter(instrumented, model=model_name)


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
