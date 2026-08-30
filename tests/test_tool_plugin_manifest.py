"""ADR-0101 V11: every Tool Provider plugin manifest declares parameters.

The ``ToolManifest`` dataclass gained a typed ``parameters`` mapping per
ADR-0101 §5.2/§6 and §9 (acceptance V11). Each Tool Provider plugin
module is expected to populate that mapping with one
:class:`lca.contracts.models.core.tool.ParameterSpec` entry per real
argument so the LobeHub renderer registry can dispatch on
``tool_name`` without journal-side preview hacks (deprecated by PR-1/2/3).

This test enumerates ``lca.plugins.tools`` modules, picks up the
module-level ``MANIFEST`` constant where present, and asserts that the
``parameters`` field exists and is a populated mapping of
:ParameterSpec: pairs.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator, Mapping
from dataclasses import fields

import pytest

from lca.contracts.models.core.tool import ParameterSpec, ToolManifest
from lca.plugins import tools as tools_pkg


def _iter_tool_modules() -> Iterator[str]:
    """Yield fully-qualified module names under ``lca.plugins.tools``."""
    for _importer, modname, _ispkg in pkgutil.walk_packages(
        tools_pkg.__path__,
        prefix="lca.plugins.tools.",
    ):
        if modname.endswith(".__init__"):
            continue
        yield modname


def _safe_import(modname: str) -> object | None:
    """Import ``modname`` returning ``None`` when the import fails.

    Tool plugins routinely import heavy third-party modules (llm SDKs,
    file stores, …) that may not be available in the unit-test slice.
    Discovery tolerates those failures and carries on.
    """
    try:
        return importlib.import_module(modname)
    except Exception:
        return None


def _discover_tool_manifests() -> list[tuple[str, ToolManifest]]:
    """Collect every module-level ``MANIFEST`` of type :ToolManifest:."""
    found: list[tuple[str, ToolManifest]] = []
    for modname in _iter_tool_modules():
        mod = _safe_import(modname)
        if mod is None:
            continue
        manifest = getattr(mod, "MANIFEST", None)
        if isinstance(manifest, ToolManifest):
            found.append((modname, manifest))
    return found


# ────────────────────────────────────────────────────────────────────
# V11 — every Tool Provider manifest declares ``parameters``
# ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tool_manifests() -> list[tuple[str, ToolManifest]]:
    return _discover_tool_manifests()


def test_all_tools_have_parameters_field(tool_manifests) -> None:
    """V11 acceptance: each ToolManifest exposes a ``parameters`` mapping."""
    assert tool_manifests, "no ToolManifest discovered under lca.plugins.tools"

    field_names = {f.name for f in fields(ToolManifest)}
    assert "parameters" in field_names, (
        "ToolManifest must declare a 'parameters' field (ADR-0101 §5.2)"
    )

    for modname, manifest in tool_manifests:
        params: Mapping[str, ParameterSpec] = manifest.parameters
        assert isinstance(params, Mapping), (
            f"{modname}.MANIFEST.parameters must be a Mapping[str, ParameterSpec]; "
            f"got {type(params).__name__}"
        )
        # The Mapping must hold ParameterSpec values, not raw dicts / strings.
        for arg_name, spec in params.items():
            assert isinstance(spec, ParameterSpec), (
                f"{modname}.MANIFEST.parameters[{arg_name!r}] must be a ParameterSpec; "
                f"got {type(spec).__name__}"
            )
            assert spec.type, f"{modname}.MANIFEST.parameters[{arg_name!r}].type is empty"


def test_every_tool_manifest_lists_at_least_one_parameter(tool_manifests) -> None:
    """V11 follow-up: each manifest populates its real argument schema."""
    assert tool_manifests
    for modname, manifest in tool_manifests:
        assert len(manifest.parameters) > 0, (
            f"{modname}.MANIFEST has an empty parameters map; "
            f"every Tool Provider must declare its real argument names per ADR-0101 §5.2"
        )


# ────────────────────────────────────────────────────────────────────
# ParameterSpec — typed shape and YAML-shaped dict parsing
# ────────────────────────────────────────────────────────────────────


def test_parameter_spec_round_trips_required_fields() -> None:
    spec = ParameterSpec(
        type="string",
        required=True,
        default=None,
        ui_hint="path",
        description="target path",
    )
    assert spec.type == "string"
    assert spec.required is True
    assert spec.default is None
    assert spec.ui_hint == "path"
    assert spec.description == "target path"


def test_parameter_spec_defaults_are_minimal() -> None:
    spec = ParameterSpec(type="integer")
    assert spec.required is False
    assert spec.default is None
    assert spec.ui_hint == ""
    assert spec.description == ""


@pytest.mark.parametrize(
    "raw",
    (
        {"type": "string", "required": True, "ui_hint": "path"},
        {"type": "boolean", "required": False, "default": False},
        {"type": "integer", "required": True, "default": 30, "description": "timeout"},
    ),
)
def test_parameter_spec_parses_yaml_shaped_dict(raw: dict) -> None:
    """Mirror the ADR-0101 §5.2 YAML example by parsing into ParameterSpec."""
    spec = ParameterSpec(**raw)
    for key, value in raw.items():
        assert getattr(spec, key) == value


def test_tool_manifest_defaults_to_empty_parameters() -> None:
    """Backward compatibility: a manifest without ``parameters`` keeps working."""
    from lca.contracts.models.core.tool import ToolApi

    manifest = ToolManifest(
        identifier="compat",
        type="builtin",
        api=(ToolApi(name="noop", description="x", parameters={"type": "object"}),),
    )
    assert manifest.parameters == {}
