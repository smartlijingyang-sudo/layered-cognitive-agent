"""Top-level pytest fixtures for the LCA test suite."""

from __future__ import annotations

from typing import Any

import pytest

from gateway.runs.loop_drivers import register_default_drivers


@pytest.fixture(autouse=True)
def _register_gateway_loop_drivers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pop the gateway's default loop drivers into every freshly-booted ctx.

    ADR-0062 §6 / PR-5: driver registration moved out of plugins into the
    gateway boot path. Tests that boot the plugin tree directly (without
    going through gateway/app.py) need the same post-boot step.

    Scope: wraps ``lca.harness.profile.boot.boot_profile`` and
    ``boot_entries`` only — does NOT touch ``lca.layer4_app.api`` (the
    L4 fallback ctx path), because production code never reads that
    cache; tests that exercise it manage their own isolation.
    """
    import lca.harness.profile.boot as boot_mod

    original_boot_profile = boot_mod.boot_profile
    original_boot_entries = boot_mod.boot_entries

    async def _boot_with_drivers(arg: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(arg, list):
            ctx = await original_boot_entries(arg, *args, **kwargs)
        else:
            ctx = await original_boot_profile(arg, *args, **kwargs)
        register_default_drivers(ctx.inject("run_loop_driver_registry"))
        return ctx

    monkeypatch.setattr(boot_mod, "boot_profile", _boot_with_drivers)
    monkeypatch.setattr(boot_mod, "boot_entries", _boot_with_drivers)

    # Rewrite local bindings for every test module.
    import sys

    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith("tests."):
            continue
        if hasattr(mod, "boot_profile"):
            monkeypatch.setattr(mod, "boot_profile", _boot_with_drivers)
        if hasattr(mod, "boot_entries"):
            monkeypatch.setattr(mod, "boot_entries", _boot_with_drivers)
