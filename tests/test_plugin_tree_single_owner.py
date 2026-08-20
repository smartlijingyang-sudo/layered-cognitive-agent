"""Default plugin tree is the only assembly source for a /runs request."""

from __future__ import annotations

from typing import Any

import pytest

from gateway.runs.execute import create_run_session, execute_run
from gateway.runs.session import RunRegistry, RunStatus
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.harness.profile.boot import boot_entries, boot_profile, load_profile_entries
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.llm_resolver import live_credential
from lca.layer4_app.api import Agent
from lca.layer4_app.spawn import build_perceive_hub, spawn_agent

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
        "lca-dsh-bridge",
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
    return {str(getattr(e, "id", "")) for e in getattr(ctx, "entries", [])}


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
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)


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
        "stop_rules",
        "hooks",
        "middleware_registry.memory",
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
    except KeyError:
        # Provider plugins inject the service; omitting the service fails boot.
        return

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError(f"module-level factory used after omitting {omit_id}")

    monkeypatch.setattr("lca.layer0_infra.sandbox.factory.resolve_sandbox", _boom)
    monkeypatch.setattr("lca.layer0_infra.tools.default_set.resolve_sandbox", _boom)
    monkeypatch.setattr("lca.layer0_infra.file_store.get_default_file_store", _boom)
    monkeypatch.setattr("lca.layer0_infra.tools.default_set.get_default_file_store", _boom)
    monkeypatch.setattr(
        "lca.layer0_infra.tools.default_set.build_g2a_chat_tools",
        _boom,
    )
    monkeypatch.setattr(
        "lca.layer0_infra.skills.factory.resolve_skill_store",
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
    ctx = await _boot_omitting("lca-tools-provider")

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("build_g2a_chat_tools must not run when tools-provider is omitted")

    monkeypatch.setattr("lca.layer0_infra.tools.default_set.build_g2a_chat_tools", _boom)
    from gateway.runs.loop_drivers import _tools_from_ctx

    assert _tools_from_ctx(ctx, None) == ()


@pytest.mark.asyncio
async def test_omitting_skills_provider_does_not_call_resolve_skill_store(
    no_llm_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skills factory gone → compose/execute miss the seam; no module-level store."""
    ctx = await _boot_omitting("lca-skills-provider")

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("resolve_skill_store must not run when skills-provider is omitted")

    monkeypatch.setattr("lca.layer0_infra.skills.factory.resolve_skill_store", _boom)
    monkeypatch.setattr(
        "lca.layer4_app.spawn.resolve_skill_store",
        _boom,
        raising=False,
    )

    from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem

    with pytest.raises(MissingCapabilityError, match="skills"):
        build_perceive_hub(SimpleMemorySystem(), scope=ctx)

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
    adapter = resolver.resolve()
    current = ctx.inject("llm").providers.current()
    assert type(adapter).__name__ == "MockLLMAdapter"
    assert type(current).__name__ == "MockLLMAdapter"
    assert live_credential("${LLM_API_KEY}") is None
    assert live_credential("") is None
    assert live_credential("sk-live") == "sk-live"
    # Placeholder must not flip the service onto a real adapter.
    assert ctx.inject("llm").providers.active == "mock"


@pytest.mark.asyncio
async def test_empty_execution_target_uses_profile_default(no_llm_key: None) -> None:
    ctx = await boot_profile(DEFAULT_PROFILE)
    registry = ctx.inject("run_loop_driver_registry")
    empty = registry.resolve("")
    named = registry.resolve("cognitive")
    assert empty is named
    with pytest.raises(Exception, match="execution_target"):
        registry.resolve("dsh")


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
    ctx = await boot_profile(DEFAULT_PROFILE)
    calls = {"n": 0}
    original = spawn_agent

    def counted(spec: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return original(spec, **kwargs)

    monkeypatch.setattr("lca.layer4_app.api.spawn_agent", counted)
    monkeypatch.setattr("lca.layer4_app.spawn.spawn_agent", counted)
    registry = RunRegistry()
    session = create_run_session(
        registry, question="hello", user_text="hello", mode="solo", ctx=ctx
    )
    await execute_run(registry, run_id=session.run_id, question="hello", mode="solo", ctx=ctx)
    assert calls["n"] == 1
    assert session.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_two_execute_runs_complete_with_mock_text(no_llm_key: None) -> None:
    ctx = await boot_profile(DEFAULT_PROFILE)
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
        assert "通用问题" in journal or "mock" in journal.lower() or "respond" in journal
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
