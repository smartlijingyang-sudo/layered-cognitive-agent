"""Manifest, boot wiring and home discovery for the Phase 0 dream scheduler.

Two of the three declaration values the plan proposed are rejected before the
kernel serves a request rather than while it does. ``PluginKind.SERVICE`` is
not a member of the closed enum, so it fails at import. ``layer="L1"``, the
value the avatar template this plugin copies declares, fails at resolve:
``_validate_layer_edges`` raises ``ProfileResolveError`` whenever a consumer's
layer rank is below its provider's, and ``assistant.catalog`` is provided at
L4. Only the profile-resolve test below observes that rule, which is why it is
here rather than left to ``scripts/check_plan_lift.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from lca.application.memory.dream_scheduler import _dream_lock_id, write_dream_evidence
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import utc_now_ms
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.models.assistant.spec import AssistantSpec
from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    AssistantSummary,
    CreateAssistantRequest,
    PlanRevision,
    ProfilePatch,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_common import PluginSpecKind
from lca.harness.plugin_api import definition_from_plugin
from lca.plugins.assistant.profile.profile import render_user_profile
from lca.plugins.memory import dream_scheduler as plugin_module

REPO = Path(__file__).resolve().parents[2]
ASSISTANT_RUNTIME_BUNDLE = REPO / "bundles" / "assistant-runtime.yaml"
WEB_ASSISTANT_PROFILE = REPO / "profiles" / "web-assistant.yaml"
PLUGIN_ID = "lca-memory-dream-scheduler"
PLUGIN_MODULE = "lca.plugins.memory.dream_scheduler"
DISPOSE_LABEL = "memory:dream-scheduler"


class _StubCatalog:
    """``AssistantCatalog`` stand-in.

    Every protocol member is present because the plugin's setup guard is
    ``isinstance(catalog, AssistantCatalog)``, which a runtime-checkable
    protocol answers by member presence.
    """

    def __init__(self, summaries: Sequence[AssistantSummary] = ()) -> None:
        self._summaries = tuple(summaries)
        self.revised: list[tuple[str, ProfilePatch]] = []

    def create(self, req: CreateAssistantRequest) -> Any:
        raise NotImplementedError

    def get(self, assistant_id: str) -> AssistantSpec:
        raise NotImplementedError

    def list(self, user_id: str | None = None) -> tuple[AssistantSummary, ...]:
        del user_id
        return self._summaries

    def revise_profile(
        self, assistant_id: str, patch: ProfilePatch, *, actor: str = "system"
    ) -> PlanRevision:
        del actor
        self.revised.append((assistant_id, patch))
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=1,
            manifest_digest="0" * 64,
            actor="system",
            snapshot_path="revisions/1.json",
        )

    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        raise NotImplementedError

    def retire(self, assistant_id: str, reason: str) -> None:
        raise NotImplementedError


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _StubCtx:
    def __init__(self, catalog: object) -> None:
        self._catalog = catalog
        self._fake_runtime = _FakeRuntime()
        self.required: list[str] = []

    def require(self, key: str) -> Any:
        self.required.append(key)
        return self._catalog

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


def _summary(home: Path) -> AssistantSummary:
    """The shape ``catalog.list()`` really returns: ``home_path`` is a ``str``."""
    return AssistantSummary(
        assistant_id=home.name,
        name=home.name,
        status="active",
        template_id="assistant.default",
        revision_seq=1,
        home_path=str(home),
    )


def _home_with_memory(tmp_path: Path, name: str) -> Path:
    home = (tmp_path / name).resolve()
    (home / "memory").mkdir(parents=True)
    return home


@pytest.fixture
def isolated_lca_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep the sweep's lock directory off the operator's real ``~/.lca``."""
    lca_home = (tmp_path / "lca-home").resolve()
    monkeypatch.setenv("LCA_HOME", str(lca_home))
    return lca_home


# ── Config ────────────────────────────────────────────────────────


def test_config_defaults_put_the_cadence_in_one_place() -> None:
    config = plugin_module.Config()

    assert config.tick_seconds == 300
    assert config.enabled is True


def test_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        plugin_module.Config.model_validate({"tick_seconds": 60, "surprise": 1})


def test_config_rejects_a_cadence_that_would_hot_loop_the_kernel() -> None:
    # A zero interval makes every sweep immediately due and leaves the loop
    # spinning on the event loop the kernel serves HTTP from.
    with pytest.raises(ValidationError):
        plugin_module.Config.model_validate({"tick_seconds": 0})


# ── Manifest ──────────────────────────────────────────────────────


def test_the_manifest_declares_the_layer_its_capability_provider_allows() -> None:
    definition = definition_from_plugin(plugin_module.setup)

    assert definition.id == PLUGIN_ID
    assert definition.spec.layer == "L4", (
        "assistant.catalog is provided at L4, and a consumer below its provider's "
        "rank is a ProfileResolveError, not a warning"
    )
    assert definition.provided_capability_keys == ()
    assert definition.required_capability_keys == ("assistant.catalog",)
    assert "filesystem" in definition.spec.effects


def test_the_module_exports_its_public_surface() -> None:
    assert plugin_module.__all__ == ["Config", "setup"]
    assert callable(plugin_module.setup.setup)


def test_the_manifest_declares_its_kind_group_scope_and_ownership() -> None:
    definition = definition_from_plugin(plugin_module.setup)
    contract = definition.contract

    assert definition.spec.kind is PluginSpecKind.PROVIDER
    assert plugin_module.setup.meta["kind"] == "provider", (
        "the declared kind, not the projection: spec_projection folds SEAM into PROVIDER "
        "for any plugin with non-none effects, so the spec alone cannot tell them apart"
    )
    assert definition.spec.verification.test_suite == str(Path(__file__).relative_to(REPO)), (
        "the declared suite is the file that pins this plugin, so it cannot rot silently"
    )
    assert contract is not None
    # G3_FACTS is where the v3-to-0069 mapping puts Memory; the sweep writes
    # semantic rows and the USER.md projection, both facts.
    assert contract.architecture.group is FunctionalGroup.G3_FACTS
    assert contract.lifecycle.allowed_scopes == (Scope.PROFILE,), (
        "the loop lives as long as the profile that loaded it, not as long as a run"
    )
    assert definition.ownership is not None
    assert definition.ownership.reads == ("assistant.catalog",)
    assert definition.ownership.state_mutation == "forbidden"


# ── home discovery ────────────────────────────────────────────────


def test_homes_reads_the_catalog_path_string_and_resolves_it(tmp_path: Path) -> None:
    home = _home_with_memory(tmp_path, "asst_1")

    found = plugin_module._homes(_StubCatalog([_summary(home)]))

    assert found == [home]


def test_two_spellings_of_one_home_take_one_lock(tmp_path: Path) -> None:
    # R22. ``_dream_lock_id`` hashes the path string, so an unresolved spelling
    # reaching the scheduler would let one home hold two locks and be dreamed
    # concurrently by two passes.
    home = _home_with_memory(tmp_path, "asst_1")
    alias = tmp_path / "alias"
    alias.symlink_to(home)

    found = plugin_module._homes(_StubCatalog([_summary(home), _summary(alias)]))

    assert found == [home, home]
    assert len({_dream_lock_id(path) for path in found}) == 1


def test_a_home_without_a_memory_tree_is_not_dreamed(tmp_path: Path) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    remembered = _home_with_memory(tmp_path, "asst_1")

    found = plugin_module._homes(_StubCatalog([_summary(bare), _summary(remembered)]))

    assert found == [remembered], (
        "consolidating a home that never had memory would manufacture a memory tree in it"
    )


def test_homes_keeps_catalog_order(tmp_path: Path) -> None:
    # Listed late-first, so neither a reversal nor a sort can pass. Catalog
    # order decides which home a tick that overruns the fleet starves, so the
    # sweep has no business reordering it.
    late = _home_with_memory(tmp_path, "zz_late")
    early = _home_with_memory(tmp_path, "aa_early")

    found = plugin_module._homes(_StubCatalog([_summary(late), _summary(early)]))

    assert found == [late, early]


# ── setup wiring ──────────────────────────────────────────────────


async def test_setup_injects_the_production_seams(
    isolated_lca_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class _Recorder:
        def __init__(self, homes: Any, **kwargs: Any) -> None:
            captured["homes"] = homes
            captured.update(kwargs)

        async def run_forever(self) -> None:
            return None

        def stop(self) -> None:
            return None

    monkeypatch.setattr(plugin_module, "DreamScheduler", _Recorder)
    assistants = isolated_lca_home / "assistants"
    home = _home_with_memory(assistants, "asst_1")
    other = _home_with_memory(assistants, "asst_0")
    catalog = _StubCatalog([_summary(home), _summary(other)])
    ctx = _StubCtx(catalog)

    await plugin_module.setup.setup(ctx, plugin_module.Config(tick_seconds=42))

    assert captured["tick_seconds"] == 42
    assert captured["lock_dir"] == isolated_lca_home / "locks", (
        "the sweep shares the host routine lock directory the cron daemon uses"
    )
    assert captured["now_ms"] is utc_now_ms, (
        "the scheduler and RoutineFileLock must read one clock, or the reclaim bound lies"
    )
    assert captured["evidence_writer"] is write_dream_evidence

    render, backfill = captured["callbacks"](home)
    assert render is render_user_profile, (
        "a scheduler that boots clean and never re-projects USER.md is the silent failure "
        "this wiring exists to end, so the pair itself is pinned rather than its presence"
    )
    assert backfill is not None
    backfill("asst_1", [])
    assert [assistant_id for assistant_id, _ in catalog.revised] == ["asst_1"], (
        "the injected backfill writes through the catalog this plugin resolved"
    )

    assert captured["homes"]() == [home, other], (
        "catalogued late-first by name, so neither a reversal nor a sort can pass"
    )


async def test_the_registered_dispose_stops_the_background_sweep(
    isolated_lca_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del isolated_lca_home
    ctx = _StubCtx(_StubCatalog([]))
    created: list[asyncio.Task[Any]] = []
    real_create_task = asyncio.create_task

    def recording_create_task(coro: Any) -> asyncio.Task[Any]:
        task = real_create_task(coro)
        created.append(task)
        return task

    monkeypatch.setattr(plugin_module.asyncio, "create_task", recording_create_task)

    await plugin_module.setup.setup(ctx, plugin_module.Config())

    assert len(created) == 1, "one background sweep per boot"
    dispose = [fn for fn, label in ctx._fake_runtime.effects if label == DISPOSE_LABEL]
    assert dispose, "the loop is stopped by the fiber's dispose chain, not left running"

    dispose[0]()
    await asyncio.wait_for(created[0], timeout=5)

    assert created[0].done()


async def test_a_disabled_config_starts_nothing(
    isolated_lca_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del isolated_lca_home
    ctx = _StubCtx(_StubCatalog([]))
    created: list[asyncio.Task[Any]] = []
    real_create_task = asyncio.create_task

    def recording_create_task(coro: Any) -> asyncio.Task[Any]:
        task = real_create_task(coro)
        created.append(task)
        return task

    monkeypatch.setattr(plugin_module.asyncio, "create_task", recording_create_task)

    await plugin_module.setup.setup(ctx, plugin_module.Config(enabled=False))

    assert created == []
    assert ctx._fake_runtime.effects == []


async def test_setup_rejects_a_capability_that_is_not_a_catalog(
    isolated_lca_home: Path,
) -> None:
    del isolated_lca_home
    ctx = _StubCtx(object())

    with pytest.raises(TypeError, match=r"assistant\.catalog"):
        await plugin_module.setup.setup(ctx, plugin_module.Config())


def test_the_stub_catalog_satisfies_the_runtime_checkable_protocol() -> None:
    # Guards the guard: if this fails, the TypeError test above passes for the
    # wrong reason and setup would reject the real catalog at boot.
    assert isinstance(_StubCatalog(), AssistantCatalog)


# ── bundle and profile ────────────────────────────────────────────


def test_the_bundle_points_at_the_module_that_declares_the_id() -> None:
    bundle = yaml.safe_load(ASSISTANT_RUNTIME_BUNDLE.read_text(encoding="utf-8"))

    entry = next(entry for entry in bundle["entries"] if entry["id"] == PLUGIN_ID)

    assert entry["$module"] == PLUGIN_MODULE, (
        "a $module whose @plugin id differs from the entry id is a dead bundle reference"
    )


def test_the_running_profile_writes_the_cadence_down() -> None:
    profile = yaml.safe_load(WEB_ASSISTANT_PROFILE.read_text(encoding="utf-8"))

    patch = next(entry for entry in profile["patch"] if entry["id"] == PLUGIN_ID)

    assert patch["config"]["tick_seconds"] <= 300, (
        "ADR-0287 §4 wants the cadence upper bound in configuration, not in prose"
    )


def test_the_running_profile_resolves_the_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lca.harness.profile.resolve.resolve import resolve_profile

    # composio-tools declares api_key as required env; this test pins profile
    # shape, not credentials.
    monkeypatch.setenv("COMPOSIO_API_KEY", "placeholder-not-a-credential")

    resolved = resolve_profile(WEB_ASSISTANT_PROFILE)

    entry = next(plugin for plugin in resolved.plugins if plugin.id == PLUGIN_ID)
    assert entry.disabled is False
    assert isinstance(entry.config, plugin_module.Config)
    assert entry.config.tick_seconds == 300
