"""Phase A integration tests — harness spine acceptance criteria.

Verifies:
1. Profile-driven plugin loading produces equivalent service table to boot_capabilities()
2. AgentComposer.compose(scope=...) works and doesn't import/mount default providers
3. AgentComposer.compose(spec) (legacy) still works
4. ScopedPluginHost parent delegation and ContextVar propagation
5. Loader seam completeness check
6. register_seam_catalog() emits DeprecationWarning
7. PluginManifest + compat adapter round-trip
"""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path

import pytest

from lca.contracts.harness.plugin import (
    ExtensionPoint,
    PluginKind,
    PluginManifest,
    ScopeKind,
)
from lca.harness.kernel.compat import manifest_from_spec
from lca.harness.kernel.scope import ScopedPluginHost, ServiceNotFoundError
from lca.layer0_infra.plugin.include._profile import ProfileLoader
from lca.layer0_infra.plugin.kernel._spec import PluginSpec
from lca.layer0_infra.plugin.loader._loader import Loader, SeamCompletenessError

PROFILE_PATH = Path("profiles/web-standard.yaml")

EXPECTED_SEAM_KEYS = (
    "llm",
    "sandbox",
    "memory",
    "state_store",
    "search",
    "tools",
    "transport",
    "skills",
    "file_store",
    "observability",
)


# ── A.1: PluginManifest contracts ────────────────────────────────────


class TestPluginManifest:
    def test_create_manifest(self):
        m = PluginManifest(
            id="test",
            version="1.0.0",
            api_version="lca-harness/1",
            kind=PluginKind.SERVICE,
            provides=("llm",),
        )
        assert m.id == "test"
        assert m.kind == PluginKind.SERVICE

    def test_manifest_with_extension_points(self):
        m = PluginManifest(
            id="test",
            version="1.0.0",
            api_version="lca-harness/1",
            kind=PluginKind.DEFINITION,
            extension_points=(ExtensionPoint(seam_key="llm", description="LLM adapter"),),
        )
        assert len(m.extension_points) == 1
        assert m.extension_points[0].seam_key == "llm"

    def test_compat_adapter(self):
        spec = PluginSpec(
            name="test",
            apply=lambda ctx, cfg: None,
            provides="llm",
            inject=("memory",),
        )
        manifest = manifest_from_spec(spec, "test-entry")
        assert manifest.id == "test-entry"
        assert manifest.kind == PluginKind.PROVIDER
        assert manifest.provides == ("llm",)
        assert manifest.requires == ("memory",)


# ── A.1b: ScopedPluginHost ──────────────────────────────────────────


class TestScopedPluginHost:
    def test_parent_delegation(self):
        root = ScopedPluginHost(None, ScopeKind.DEPLOYMENT, "deploy-1")
        child = root.fork(ScopeKind.PROFILE, "profile-1")

        # Mount service in root
        from lca.layer0_infra.plugin.kernel._handle import PluginHandle

        spec = PluginSpec(name="t", apply=lambda ctx, cfg: None, provides="llm")
        handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())
        root.host.register_handle(handle)
        root.host.provide(handle, "llm", "root-llm")

        # Child resolves from parent
        assert child.resolve("llm") == "root-llm"

    def test_child_shadow(self):
        root = ScopedPluginHost(None, ScopeKind.DEPLOYMENT, "deploy-1")
        child = root.fork(ScopeKind.PROFILE, "profile-1")

        from lca.layer0_infra.plugin.kernel._handle import PluginHandle

        spec = PluginSpec(name="t", apply=lambda ctx, cfg: None, provides="llm")
        h1 = PluginHandle(entry_id="root-plugin", spec=spec, config={}, injected=())
        root.host.register_handle(h1)
        root.host.provide(h1, "llm", "root-llm")

        h2 = PluginHandle(entry_id="child-plugin", spec=spec, config={}, injected=())
        child.host.register_handle(h2)
        child.host.provide(h2, "llm", "child-llm")

        assert root.resolve("llm") == "root-llm"
        assert child.resolve("llm") == "child-llm"

    def test_service_not_found(self):
        root = ScopedPluginHost(None, ScopeKind.DEPLOYMENT, "deploy-1")
        with pytest.raises(ServiceNotFoundError):
            root.resolve("nonexistent")

    def test_context_var_propagation(self):
        async def _test():
            root = ScopedPluginHost(None, ScopeKind.DEPLOYMENT, "deploy-1")
            child = root.fork(ScopeKind.AGENT, "agent-1")

            async def inner():
                current = ScopedPluginHost.current()
                assert current is child

            await child.run_in_scope(inner())

        asyncio.run(_test())

    def test_current_outside_scope_raises(self):
        with pytest.raises(RuntimeError, match="No active plugin scope"):
            ScopedPluginHost.current()


# ── A.2: Plugin modules + base-spine bundle ─────────────────────────


class TestBaseSpine:
    @pytest.fixture()
    def tree(self):
        async def _load():
            pl = ProfileLoader()
            entries = pl.load_profile(PROFILE_PATH)
            loader = Loader()
            return await loader.load(entries)

        return asyncio.run(_load())

    def test_all_seams_loaded(self, tree):
        for key in EXPECTED_SEAM_KEYS:
            svc = tree.host.get_service(key)
            assert svc is not None, f"Service '{key}' not loaded"

    def test_entry_count(self, tree):
        # 11 plugins: seam_definitions + 10 services
        assert len(tree.entries) == 11

    def test_all_plugins_active(self, tree):
        for entry in tree.entries:
            handle = tree.host.handles.get(entry.id)
            assert handle is not None
            from lca.layer0_infra.plugin.kernel import PluginState

            assert handle.state == PluginState.ACTIVE

    def test_seam_definitions_has_extension_points(self, tree):
        mod = None
        for entry in tree.entries:
            original = getattr(entry, "_original_module", None)
            if original is not None:
                m = getattr(original, "manifest", None)
                if m is not None and m.id == "lca.seam.definitions":
                    mod = m
                    break
        assert mod is not None
        assert mod.kind == PluginKind.BUNDLE
        assert len(mod.extension_points) == 10


# ── A.5: AgentComposer scope integration ─────────────────────────────


class TestComposerScope:
    def test_legacy_path_unchanged(self):
        """Legacy compose(spec) without scope still works."""
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.composer import AgentComposer
        from tests.support.agent_specs import make_spec

        composer = AgentComposer()
        spec = make_spec("tester", MockLLMAdapter())
        agent = composer.compose(spec)
        assert agent is not None

    def test_scope_path(self):
        """compose(spec, scope=...) resolves from plugin tree."""
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.composer import AgentComposer
        from tests.support.agent_specs import make_spec

        async def _test():
            from lca.harness.profile.boot import boot_profile

            tree = await boot_profile(PROFILE_PATH, check_seam_completeness=False)
            profile_scope = ScopedPluginHost.wrap(tree.host, ScopeKind.PROFILE, "web-standard")

            composer = AgentComposer()
            spec = make_spec("tester", MockLLMAdapter())
            agent = composer.compose(spec, scope=profile_scope)
            assert agent is not None

        asyncio.run(_test())

    def test_scope_compose_does_not_mutate_parent_services(self):
        from lca.harness.profile.boot import boot_profile
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.composer import AgentComposer
        from tests.support.agent_specs import make_spec

        async def _test():
            tree = await boot_profile(PROFILE_PATH)
            parent = ScopedPluginHost.wrap(tree.host, ScopeKind.PROFILE, "web-standard")
            parent_llm = parent.resolve("llm")
            before = list(parent_llm.providers.names())

            composer = AgentComposer()
            composer.compose(make_spec("a", MockLLMAdapter()), scope=parent)
            composer.compose(make_spec("b", MockLLMAdapter()), scope=parent)

            assert parent.resolve("llm") is parent_llm
            assert parent_llm.providers.names() == before
            assert "spec" not in parent_llm.providers.names()

        asyncio.run(_test())

    def test_legacy_and_scope_paths_equivalent_calculator(self):
        from dataclasses import replace

        from lca.contracts.models.team.role_team import ToolPermissionManifest
        from lca.harness.profile.boot import boot_profile
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer0_infra.tools.calculator import build_tools as build_calculator_tools
        from lca.layer4_app.composer import AgentComposer
        from tests.support.agent_specs import make_spec

        tools = tuple(build_calculator_tools())
        spec = replace(
            make_spec("tester", MockLLMAdapter(), max_steps=8),
            tools=tools,
            profile=replace(
                make_spec("tester", MockLLMAdapter()).profile,
                tool_permission_manifest=ToolPermissionManifest(
                    allowed_tools=[t.name for t in tools]
                ),
            ),
        )

        async def _test():
            tree = await boot_profile(PROFILE_PATH)
            scope = ScopedPluginHost.wrap(tree.host, ScopeKind.PROFILE, "web-standard")
            composer = AgentComposer()
            legacy = composer.compose(spec)
            scoped = composer.compose(spec, scope=scope)
            question = "123 乘以 456 等于多少？"
            r1 = await legacy.run(question)
            r2 = await scoped.run(question)
            assert r1.status == r2.status == "completed"
            assert r1.output is not None and r2.output is not None
            assert "56088" in r1.output
            assert "56088" in r2.output

        asyncio.run(_test())


# ── A.7: Seam completeness + deprecation ─────────────────────────────


class TestSeamCompleteness:
    def test_loader_seam_check_passes(self):
        async def _test():
            pl = ProfileLoader()
            entries = pl.load_profile(PROFILE_PATH)
            loader = Loader(check_seam_completeness=True)
            tree = await loader.load(entries)
            assert len(tree.entries) == 1 + len(EXPECTED_SEAM_KEYS)

        asyncio.run(_test())

    def test_missing_llm_provider_fails_completeness(self):
        async def _test():
            pl = ProfileLoader()
            entries = [e for e in pl.load_profile(PROFILE_PATH) if e.id != "lca.llm.service"]
            with pytest.raises(SeamCompletenessError, match="llm"):
                await Loader(check_seam_completeness=True).load(entries)

        asyncio.run(_test())

    def test_register_seam_catalog_deprecated(self):
        from lca.layer4_app.capability_boot import register_seam_catalog

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            register_seam_catalog()
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1

    def test_boot_capabilities_suppresses_warning(self):
        """boot_capabilities() still works without emitting visible warnings."""
        from lca.layer4_app.capability_boot import boot_capabilities

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            hub = boot_capabilities()
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            # Internal deprecation is suppressed
            assert len(deprecation_warnings) == 0
        assert hub is not None
        assert hub.require("llm") is not None


class TestInspectAndBoot:
    def test_boot_profile_and_format_tree(self):
        from lca.harness.diagnostics.inspect import format_plugin_tree, inspect_profile_tree

        async def _test():
            tree = await inspect_profile_tree(PROFILE_PATH)
            dump = format_plugin_tree(tree, profile=str(PROFILE_PATH))
            assert "lca.llm.service" in dump
            assert "provides: llm" in dump
            assert "Seam completeness: PASS" in dump

        asyncio.run(_test())

    def test_wrap_reuses_loaded_host(self):
        from lca.harness.profile.boot import boot_profile

        async def _test():
            tree = await boot_profile(PROFILE_PATH)
            scope = ScopedPluginHost.wrap(tree.host, ScopeKind.PROFILE, "web-standard")
            assert scope.resolve("llm") is not None
            assert scope.host is tree.host

        asyncio.run(_test())
