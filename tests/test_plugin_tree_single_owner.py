"""Default plugin tree is the only assembly source for a /runs request."""

from __future__ import annotations

from typing import Any

import pytest

from gateway.runs.execute import create_run_session, execute_run
from gateway.runs.session import RunRegistry, RunStatus
from lca.contracts.atoms.enums import ActionScope
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.harness.profile.boot import boot_entries, boot_profile, load_profile_entries
from lca.harness.profile.boot_products import resolved_profile_from_scope
from lca.harness.profile.resolve import ProfileResolveError
from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
from lca.infrastructure.llm_resolver import live_credential
from lca.application.api import Agent
from lca.application.spawn import spawn_agent
from lca.plugins.composer.internal.perceive import build_perceive_hub

DEFAULT_PROFILE = "profiles/web-standard.yaml"

DEAD_DEFAULT_IDS = frozenset(
    {
        "lca-system-prompt-service",
        "lca-session-service",
        "lca-workspace-service",
        "lca-workspace-provider",
        "lca-attachment-service",
        "lca-attachment-provider",
        "lca-llm-provider",
        "lca-team-lead-board",
        "lca-blackboard-memory",
        "lca-synthesizer-concat",
        "lca-brain-modular",
    }
)

# Plugin id → seam whose absence must not be papered over by a module-level factory.
SEAM_OMIT_IDS = (
    "lca-llm-resolver",
    "lca-tools-service",
    "lca-sandbox-service",
    "lca-search-service",
    "lca-file-store-service",
    "lca-skills-service",
    "lca-skills-provider",
    "lca-observability-service",
    "lca-memory-service",
    "lca-memory-provider",
    "lca-state-store-service",
    "lca-state-store-provider",
    "lca-loop-cognitive",
    "lca-run-loop-driver-registry",
)


def _entry_ids(ctx: Any) -> set[str]:
    resolved = resolved_profile_from_scope(ctx)
    if resolved is None:
        return set()
    return {plugin.id for plugin in resolved.plugins if not plugin.disabled}


async def _boot_omitting(omit: str) -> Any:
    entries = [e for e in load_profile_entries(DEFAULT_PROFILE) if e["id"] != omit]
    return await boot_entries(entries)


def _unwrap_llm(llm: Any) -> Any:
    inner = llm
    while hasattr(inner, "_inner"):
        inner = inner._inner
    return inner


@pytest.fixture
def no_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block dotenv reload and clear credential env so boot has no real key."""
    monkeypatch.setattr(
        "lca.infrastructure.llm.config.prepare_llm_environ",
        lambda: None,
    )
    monkeypatch.setattr(
        "lca.infrastructure.llm_adapter.factory.load_dotenv_if_present",
        lambda path=None: None,
    )
    for key in (
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_OPENAI_BASE_URL",
        "LLM_MODEL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.asyncio
async def test_dead_ids_absent_from_default_boot(no_llm_key: None) -> None:
    ctx = await boot_profile(DEFAULT_PROFILE)
    ids = _entry_ids(ctx)
    assert DEAD_DEFAULT_IDS.isdisjoint(ids)
    for dead in DEAD_DEFAULT_IDS:
        assert dead not in ids


@pytest.mark.asyncio
async def test_every_default_entry_is_consumed(no_llm_key: None) -> None:
    ctx = await boot_profile(DEFAULT_PROFILE)
    injected: set[str] = set()
    orig = ctx.inject

    def spy(key: str, **kwargs: Any) -> Any:
        injected.add(key)
        return orig(key, **kwargs)

    ctx.inject = spy  # type: ignore[method-assign]
    from tests.support.gateway_scripted import ScriptedLLMResolver

    ctx.provide("llm_resolver", ScriptedLLMResolver())
    registry = RunRegistry()
    session = create_run_session(registry, question="ping", user_text="ping", mode="solo", ctx=ctx)
    await execute_run(registry, run_id=session.run_id, question="ping", mode="solo", ctx=ctx)
    consumed_keys = {
        "llm",
        "llm_resolver",
        "tools",
        "sandbox",
        "search",
        "file_store",
        "skills",
        "observability",
        "memory",
        "state_store",
        "transport",
        "run_loop_driver_registry",
        "brains",
        "bodies",
        "safe_executor.simple",
        "stop_policy",
        "hooks",
        "journal_store",
        "perceive",
    }
    missing = consumed_keys - injected
    assert not missing, f"execute/compose never injected {sorted(missing)}"
    ids = _entry_ids(ctx)
    # Providers fill a consumed service; loop plugin registers the driver.
    assert ids, "default boot produced no entries"
    assert "lca-llm-resolver" in ids
    assert "lca-loop-cognitive" in ids
    assert "lca-brain-simple" in ids


@pytest.mark.asyncio
@pytest.mark.parametrize("omit_id", SEAM_OMIT_IDS)
async def test_omitting_seam_plugin_does_not_bypass(
    omit_id: str, no_llm_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        ctx = await _boot_omitting(omit_id)
    except (KeyError, ProfileResolveError):
        # Resolve or boot rejects an incomplete provider graph before it can
        # become a module-level fallback path.
        return

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError(f"module-level factory used after omitting {omit_id}")

    monkeypatch.setattr("lca.infrastructure.sandbox.factory.resolve_sandbox", _boom)
    monkeypatch.setattr("lca.infrastructure.tools.default_set.resolve_sandbox", _boom)
    import lca.infrastructure.file_store as file_store_module

    assert not hasattr(file_store_module, "get_default_file_store")
    assert not hasattr(file_store_module, "set_default_file_store")
    monkeypatch.setattr(
        "lca.infrastructure.tools.default_set.build_g2a_chat_tools",
        _boom,
    )
    monkeypatch.setattr(
        "lca.infrastructure.skills.factory.resolve_skill_store",
        _boom,
    )

    registry = RunRegistry()
    try:
        session = create_run_session(
            registry, question="ping", user_text="ping", mode="solo", ctx=ctx
        )
        await execute_run(registry, run_id=session.run_id, question="ping", mode="solo", ctx=ctx)
        execute_ok = session.status == RunStatus.COMPLETED and not session.error
    except (MissingCapabilityError, KeyError, RuntimeError, TypeError, AssertionError):
        execute_ok = False
    assert not execute_ok, f"omitting {omit_id} still completed via a bypass"


@pytest.mark.asyncio
async def test_omitting_tools_provider_skips_g2a_not_fallback(
    no_llm_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """省略 lca-tools-provider 时，g2a 不应被 fallback 调用。

    实现差异：web-standard 现默认加载 scenario-cordis-creator bundle，bash /
    file_write 通过 setup 直接 register() 进 tools 服务（不依赖 lca-tools-provider）。
    本测试断言在 lca-tools-provider 缺位时：
    1. g2a factory 不被调用（mock _boom）；
    2. tools_from_scope 返回结果里不含任何 *_skill / *_chat 工具
       （这些只能由 g2a 产出）。
    """
    ctx = await _boot_omitting("lca-tools-provider")

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("build_g2a_chat_tools must not run when tools-provider is omitted")

    monkeypatch.setattr("lca.infrastructure.tools.default_set.build_g2a_chat_tools", _boom)
    from gateway.runs.runnable_assembly import tools_from_scope

    tools = tools_from_scope(ctx, None)
    tool_names = [t.name for t in tools]
    # g2a 出来的工具（search / askUserQuestion / *_skill 系列）一律不应出现
    assert not any(name.endswith("_skill") for name in tool_names), tool_names
    assert "search" not in tool_names
    assert "askUserQuestion" not in tool_names
    # bash / file_write 是 scenario-cordis-creator bundle 直挂的，缺 lca-tools-provider
    # 时仍可用（这是设计：creator 工具独立于 g2a chain）


@pytest.mark.asyncio
async def test_omitting_skills_provider_does_not_call_resolve_skill_store(
    no_llm_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skills factory gone → compose/execute miss the seam; no module-level store."""
    from tests.support.gateway_scripted import ScriptedLLMResolver

    ctx = await _boot_omitting("lca-skills-provider")
    ctx.provide("llm_resolver", ScriptedLLMResolver())

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("resolve_skill_store must not run when skills-provider is omitted")

    monkeypatch.setattr("lca.infrastructure.skills.factory.resolve_skill_store", _boom)

    from lca.cognition.memory.simple_memory import SimpleMemorySystem

    with pytest.raises(MissingCapabilityError, match="skills"):
        build_perceive_hub(
            SimpleMemorySystem(),
            store=object(),
            scope=ctx,
            action_scope=ActionScope.SOLO,
        )

    registry = RunRegistry()
    session = create_run_session(registry, question="ping", user_text="ping", mode="solo", ctx=ctx)
    await execute_run(registry, run_id=session.run_id, question="ping", mode="solo", ctx=ctx)
    assert session.status != RunStatus.COMPLETED
    assert session.error
    assert "skills" in session.error.lower() or "MissingCapability" in session.error


@pytest.mark.asyncio
async def test_llm_single_owner_without_key(no_llm_key: None) -> None:
    ctx = await boot_profile(DEFAULT_PROFILE)
    resolver = ctx.inject("llm_resolver")
    assert resolver.is_available() is False
    with pytest.raises(Exception, match="LLM_API_KEY"):
        resolver.resolve()
    assert live_credential("${LLM_API_KEY}") is None
    assert live_credential("") is None
    assert live_credential("sk-live") == "sk-live"
    # No mock/deepseek provider registered on the llm seam.
    assert "mock" not in set(ctx.inject("llm").providers.names())
    assert "deepseek" not in set(ctx.inject("llm").providers.names())


@pytest.mark.asyncio
async def test_empty_execution_target_uses_profile_default(no_llm_key: None) -> None:
    ctx = await boot_profile(DEFAULT_PROFILE)
    registry = ctx.inject("run_loop_driver_registry")
    empty = registry.resolve("")
    named = registry.resolve("cognitive")
    assert empty is named
    with pytest.raises(Exception, match="execution_target"):
        registry.resolve("never-registered-loop")


@pytest.mark.asyncio
async def test_overlapping_compose_keeps_distinct_adapters(no_llm_key: None) -> None:
    ctx = await boot_profile(DEFAULT_PROFILE)
    one = MockLLMAdapter()
    two = MockLLMAdapter()
    a1 = Agent(role="a", goal="", backstory="", tools=(), llm=one, scope=ctx)
    a2 = Agent(role="b", goal="", backstory="", tools=(), llm=two, scope=ctx)
    assert _unwrap_llm(a1._agent.runtime.brain.reasoner.llm) is one
    assert _unwrap_llm(a2._agent.runtime.brain.reasoner.llm) is two


@pytest.mark.asyncio
async def test_cognitive_driver_composes_once(
    no_llm_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.support.gateway_scripted import ScriptedLLMResolver

    ctx = await boot_profile(DEFAULT_PROFILE)
    ctx.provide("llm_resolver", ScriptedLLMResolver())
    calls = {"n": 0}
    original = spawn_agent

    def counted(spec: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return original(spec, **kwargs)

    monkeypatch.setattr("lca.application.api.spawn_agent", counted)
    monkeypatch.setattr("lca.application.spawn.spawn_agent", counted)
    registry = RunRegistry()
    session = create_run_session(
        registry, question="hello", user_text="hello", mode="solo", ctx=ctx
    )
    await execute_run(registry, run_id=session.run_id, question="hello", mode="solo", ctx=ctx)
    assert calls["n"] == 1
    assert session.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_two_execute_runs_complete_with_scripted_text(no_llm_key: None) -> None:
    from tests.support.gateway_scripted import ScriptedLLMResolver

    ctx = await boot_profile(DEFAULT_PROFILE)
    ctx.provide("llm_resolver", ScriptedLLMResolver())
    outputs: list[str] = []
    for question in ("say hello in one word", "say goodbye in one word"):
        registry = RunRegistry()
        session = create_run_session(
            registry, question=question, user_text=question, mode="solo", ctx=ctx
        )
        await execute_run(registry, run_id=session.run_id, question=question, mode="solo", ctx=ctx)
        assert session.status == RunStatus.COMPLETED, session.error
        journal = session.jsonl_path.read_text(encoding="utf-8")
        assert journal.strip(), "run journal is empty"
        assert "通用问题" in journal or "respond" in journal or "solo" in journal.lower()
        outputs.append(journal)
    assert len(outputs) == 2


@pytest.mark.asyncio
async def test_dump_profile_matches_boot_ids() -> None:
    from lca.harness.profile.boot import load_profile_entries

    ctx = await boot_profile(DEFAULT_PROFILE)
    dumped = {
        e["id"]
        for e in load_profile_entries(DEFAULT_PROFILE)
        if not e.get("disabled")
        and not (isinstance(e.get("config"), dict) and e["config"].get("disabled"))
    }
    assert dumped == _entry_ids(ctx)


@pytest.mark.asyncio
async def test_unknown_execution_target_writes_journal_and_session_error(
    no_llm_key: None,
) -> None:
    """sandbox/device/etc. → plane hint; missing-loop token → error visible
    in both the snapshot endpoint (``session.error``) and the journal
    jsonl that ``lca-ops logs`` replays.
    """
    from tests.support.gateway_scripted import ScriptedLLMResolver

    ctx = await boot_profile(DEFAULT_PROFILE)
    ctx.provide("llm_resolver", ScriptedLLMResolver())
    registry = RunRegistry()
    session = create_run_session(
        registry,
        question="你好吗",
        user_text="你好吗",
        mode="solo",
        execution_target="sandbox",  # plane hint, profile default driver
        ctx=ctx,
    )
    await execute_run(
        registry,
        run_id=session.run_id,
        question="你好吗",
        mode="solo",
        ctx=ctx,
    )
    assert session.error == "", session.error
    assert session.status in {RunStatus.FAILED, RunStatus.COMPLETED}

    session2 = create_run_session(
        registry,
        question="x",
        user_text="x",
        mode="solo",
        execution_target="no-such-loop",
        ctx=ctx,
    )
    await execute_run(
        registry,
        run_id=session2.run_id,
        question="x",
        mode="solo",
        ctx=ctx,
    )
    assert session2.status == RunStatus.FAILED
    assert "no-such-loop" in (session2.error or "")
    assert "loop plugin" in (session2.error or "").lower()
    # Internal exception class name must not leak to end users.
    assert "_UnknownExecutionTargetError" not in (session2.error or "")
    journal = session2.jsonl_path.read_text(encoding="utf-8")
    assert "AgentRunFinished" in journal
    assert "no-such-loop" in journal
