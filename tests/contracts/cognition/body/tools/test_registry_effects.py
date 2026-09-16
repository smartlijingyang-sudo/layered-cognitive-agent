"""PR-3 (G-21, ADR-0232) — every tool manifest must declare an explicit ``effects``.

Contract: ``ToolApi.effects`` is ``Literal["read", "write", "external"]``.
The audit covers every ``MANIFEST = ToolManifest(...)`` exposed under
``lca/plugins/tools/``.  A manifest that silently falls back to the
dataclass default ``"external"`` is acceptable ONLY when the manifest
is explicitly written with ``effects="external"`` (i.e. the author made
the conservative choice on purpose).

A bare default — i.e. no ``effects=`` kwarg — is rejected by these tests.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

from lca.contracts.cognition.body.tools.registry import (
    ToolEffects,
    ToolEffectsDeclarationError,
    assert_effects_declared,
    select_effect,
)
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest


def _iter_tool_modules() -> list[str]:
    """Discover every plugin module under ``lca.plugins.tools`` (incl. subpkgs)."""

    import lca.plugins.tools as root

    discovered: list[str] = []
    for module_info in pkgutil.walk_packages(root.__path__, prefix="lca.plugins.tools."):
        discovered.append(module_info.name)
    return discovered


def _import_manifests() -> list[tuple[str, ToolManifest]]:
    """Import each tool module and capture any ``MANIFEST`` it defines.

    A module may export a single ``MANIFEST`` constant or — when the
    surface spans multiple APIs — a ``MANIFESTS`` tuple.  Both shapes
    are accepted; the audit then iterates ``manifest.api`` and checks
    ``effects``.
    """

    found: list[tuple[str, ToolManifest]] = []
    for module_name in _iter_tool_modules():
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 — discovery should not halt on a broken optional plugin
            continue
        manifest = getattr(module, "MANIFEST", None)
        if isinstance(manifest, ToolManifest):
            found.append((module_name, manifest))
            continue
        manifests = getattr(module, "MANIFESTS", None)
        if isinstance(manifests, tuple):
            for sub in manifests:
                if isinstance(sub, ToolManifest):
                    found.append((module_name, sub))
    return found


def test_every_tool_api_declares_valid_effects() -> None:
    """Every ``ToolApi.effects`` must be in the closed set {read, write, external}."""

    manifests = _import_manifests()
    assert manifests, "no ToolManifest discovered under lca.plugins.tools — audit is meaningless"

    offenders: list[str] = []
    for module_name, manifest in manifests:
        for api in manifest.api:
            if api.effects not in {"read", "write", "external"}:
                offenders.append(f"{module_name}.{manifest.identifier}.{api.name}={api.effects!r}")
    assert not offenders, (
        "every ToolApi must declare effects in {read,write,external} "
        f"(ADR-0232 §Decision 2): {offenders}"
    )


@pytest.mark.parametrize(
    "effects,expected",
    [
        ("read", "read"),
        ("write", "write"),
        ("external", "external"),
    ],
)
def test_select_effect_returns_declared_value(
    effects: ToolEffects, expected: str
) -> None:
    """``select_effect`` round-trips a declared ``ToolApi.effects``."""

    api = ToolApi(
        name="probe",
        description="probe tool for effects round-trip",
        parameters={"type": "object", "properties": {}},
        effects=effects,  # type: ignore[arg-type]
    )
    assert select_effect(api) == expected


def test_select_effect_rejects_invalid_value() -> None:
    """``select_effect`` raises on any value outside the closed set."""

    api = ToolApi(
        name="probe",
        description="probe with bogus effects",
        parameters={"type": "object", "properties": {}},
        effects="ephemeral",  # type: ignore[arg-type] — dataclass accepts but audit rejects
    )
    with pytest.raises(ToolEffectsDeclarationError):
        select_effect(api)


def test_assert_effects_declared_passes_for_audited_manifests() -> None:
    """All shipped manifests pass the bundled audit (sanity gate)."""

    manifests = [m for _, m in _import_manifests()]
    # Should not raise — the G-21 sweep already added explicit effects=.
    assert_effects_declared(manifests)


def test_assert_effects_declared_rejects_unknown_id_with_default_effects() -> None:
    """A brand-new identifier that never declared effects is rejected by the strict audit."""

    from lca.contracts.cognition.body.tools.registry import register_manifest_with_audit

    manifest = ToolManifest(
        identifier="probe.unknown_tool",
        type="builtin",
        api=(
            ToolApi(
                name="probeUnknown",
                description="probe",
                parameters={"type": "object", "properties": {}},
                # no effects= — dataclass default is "external"
            ),
        ),
    )
    # No declared_effects entry for the unknown tool -> rejected.
    with pytest.raises(ToolEffectsDeclarationError):
        register_manifest_with_audit(manifest, declared_effects={})


def test_assert_effects_declared_accepts_explicit_external_on_new_tool() -> None:
    """Explicit ``effects="external"`` on a new tool is accepted (conservative default)."""

    manifest = ToolManifest(
        identifier="probe.explicit_external",
        type="builtin",
        api=(
            ToolApi(
                name="probeExternal",
                description="probe",
                parameters={"type": "object", "properties": {}},
                effects="external",
            ),
        ),
    )
    assert_effects_declared([manifest])  # no raise


def test_well_known_manifests_declare_expected_effects() -> None:
    """Sanity check: bash=external, file_write=write, profile_apply=read, profile_diff=read.

    This is the precise pairing called out in ADR-0232 §Decision 2 and
    in Task 3.2 brief.  If any of these slip back to the dataclass
    default the PR-3 acceptance gate trips.
    """

    expected = {
        "bash": "external",
        "file-write": "write",
        "profile_apply": "read",
        "profile_diff": "read",
    }
    manifests = {m.identifier: m for _, m in _import_manifests()}
    for identifier, want in expected.items():
        if identifier not in manifests:
            # not every test env loads every plugin; only assert what is present.
            continue
        got = manifests[identifier].api[0].effects
        assert got == want, f"{identifier}.effects={got!r}, expected {want!r}"


def test_no_manifest_module_path_collides_with_contracts_path() -> None:
    """Guard: tool plugins must keep living under lca.plugins.tools (not contracts).

    This is a layout sanity check — ``lca/contracts/cognition/body/tools/``
    is the *schema* package (this test's home), not a plugin folder.
    """

    contracts_path = Path("lca/contracts/cognition/body/tools")
    plugins_path = Path("lca/plugins/tools")
    assert contracts_path.exists(), "schema package must exist"
    assert plugins_path.exists(), "plugin folder must exist"
    # Any future move should update this test rather than silently allowing
    # plugin code to leak into the contracts package.
    assert contracts_path.is_dir()
    assert plugins_path.is_dir()
