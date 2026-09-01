"""Plugin Manifests for the three EventSpine wrap kinds.

Behavioral coverage for ``install_ctx_*`` / ``wrap_instrument`` stays in
``test_runtime_hooks.py``. This module pins that Profile can load each
wrap via ``$module`` and that each ``setup`` declares the expected id /
provides / requires.
"""

from __future__ import annotations

from lca.harness.plugin_api import PluginKind
from lca.harness.plugin_declaration import definition_from_plugin
from lca.plugins.observability.spine.wraps import assembler, ctx_effect, ctx_intercept


def test_ctx_effect_plugin_declares_expected_metadata() -> None:
    """``spine.wrap.ctx_effect`` provides ``ctx_effect_wrap``."""
    assert hasattr(ctx_effect, "setup")
    definition = definition_from_plugin(ctx_effect.setup, module=__name__)
    assert definition.id == "spine.wrap.ctx_effect"
    assert definition.spec.layer == "L0"
    assert definition.spec.kind == PluginKind.SEAM
    assert definition.provided_capability_keys == ("ctx_effect_wrap",)
    assert any(req.key == "emit_pipeline" for req in definition.spec.requires)


def test_ctx_intercept_plugin_declares_expected_metadata() -> None:
    """``spine.wrap.ctx_intercept`` provides ``ctx_intercept_wrap``."""
    assert hasattr(ctx_intercept, "setup")
    definition = definition_from_plugin(ctx_intercept.setup, module=__name__)
    assert definition.id == "spine.wrap.ctx_intercept"
    assert definition.spec.layer == "L0"
    assert definition.spec.kind == PluginKind.SEAM
    assert definition.provided_capability_keys == ("ctx_intercept_wrap",)
    assert any(req.key == "emit_pipeline" for req in definition.spec.requires)


def test_assembler_plugin_declares_expected_metadata() -> None:
    """``spine.wrap.assembler`` provides ``assembler_wrap``."""
    assert hasattr(assembler, "setup")
    definition = definition_from_plugin(assembler.setup, module=__name__)
    assert definition.id == "spine.wrap.assembler"
    assert definition.spec.layer == "L0"
    assert definition.spec.kind == PluginKind.SEAM
    assert definition.provided_capability_keys == ("assembler_wrap",)
    assert any(req.key == "emit_pipeline" for req in definition.spec.requires)


def test_runtime_hooks_no_longer_registers_wrap_plugins() -> None:
    """Installers stay in ``runtime_hooks``; ``@plugin`` setups do not."""
    import lca.plugins.observability.spine.runtime_hooks as runtime_hooks

    assert not hasattr(runtime_hooks, "setup_ctx_effect")
    assert not hasattr(runtime_hooks, "setup_ctx_intercept")
    assert "install_ctx_effect_hook" in runtime_hooks.__all__
    assert "install_ctx_intercept_hook" in runtime_hooks.__all__
