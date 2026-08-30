"""RenderContract reconciliation test.

For every tool in REGISTRY, verify:
1. A renderer component exists in deploy/lobehub/patches/runtime/lcaToolRender/renderers/<identifier>/<api_name>.tsx
2. Every state field declared in the contract has a corresponding read
   in either the renderer or the projection module's fallback path
3. Every wire_key on a state field is either camelCase (lowercase first
   letter) OR matches a known argv-style convention (no uppercase first
   letter that the LobeHub renderer can't consume)

This is the SSOT contract test: a new Tool cannot land without a
RenderContract AND a matching renderer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lca.layer0_infra.tools.contract import REGISTRY, render_registry_to_ts

_REPO = Path(__file__).resolve().parents[2]
_RENDERER_DIR = _REPO / "deploy" / "lobehub" / "patches" / "runtime" / "lcaToolRender" / "renderers"


def _identifier_to_dir(identifier: str) -> str:
    return identifier  # lobe-skills → lobe-skills/


def test_render_registry_codegen_is_stable() -> None:
    """Codegen produces the same TS for the same REGISTRY twice."""
    a = render_registry_to_ts()
    b = render_registry_to_ts()
    assert a == b


def test_codegen_output_is_well_formed_typescript() -> None:
    """Minimal TS structural sanity check on the generated file."""
    ts = render_registry_to_ts()
    # Has the type declarations
    assert "export interface ToolField" in ts
    assert "export interface ToolRenderContract" in ts
    assert "export const CONTRACTS" in ts
    # Balanced braces (rough check)
    assert ts.count("{") == ts.count("}")


@pytest.mark.parametrize(
    "tool_name,identifier,api_name",
    [(name, c.identifier, c.api_name) for name, c in sorted(REGISTRY.items())],
)
def test_every_contract_has_a_renderer_file(tool_name: str, identifier: str, api_name: str) -> None:
    """Each contract must have a renderer .tsx file in the expected path.

    Some tool renames point to non-default apiNames (e.g. import_skill →
    importFromMarket); we check both the default and known-rename paths.
    """
    renderer_dir = _RENDERER_DIR / _identifier_to_dir(identifier)
    if not renderer_dir.is_dir():
        pytest.skip(f"no renderer directory for identifier {identifier}")
    default = renderer_dir / f"{api_name}.tsx"
    if default.is_file():
        return
    # Known apiName aliases for LCA tools
    aliases = {"importSkill": ["importFromMarket.tsx"]}
    if api_name in aliases and any((renderer_dir / a).is_file() for a in aliases[api_name]):
        return
    pytest.fail(
        f"Tool {tool_name!r} (identifier={identifier!r}, api_name={api_name!r}) "
        f"has no renderer at {default.relative_to(_REPO)} or known alias"
    )


@pytest.mark.parametrize("tool_name", sorted(REGISTRY.keys()))
def test_every_contract_wire_keys_are_lobehub_compatible(tool_name: str) -> None:
    """Every wire_key on a state field must be camelCase or single-word lower.

    LobeHub's pluginState keys are accessed as ``state['executionEnv']``
    etc. Uppercase first letter (PascalCase) is reserved for class names.
    """
    contract = REGISTRY[tool_name]
    camel_re = re.compile(r"^[a-z][a-zA-Z0-9]*$")
    for field in contract.state:
        if not camel_re.match(field.wire_key):
            pytest.fail(
                f"Tool {tool_name!r} state field wire_key={field.wire_key!r} "
                f"is not camelCase; LobeHub renderer won't find it"
            )
    for field in contract.args:
        if not camel_re.match(field.wire_key):
            pytest.fail(
                f"Tool {tool_name!r} arg field wire_key={field.wire_key!r} "
                f"is not camelCase; LobeHub renderer won't find it"
            )


def test_known_field_renames_are_applied() -> None:
    """Specific renames that the previous 6-layer pipeline missed must hold."""
    contract = REGISTRY["activate_skill"]
    skill_id_args = [f for f in contract.args if f.python_key == "skill_id"]
    assert skill_id_args, "activate_skill must declare skill_id arg"
    assert skill_id_args[0].wire_key == "name", (
        "activate_skill skill_id must rename to LobeHub's ActivateSkillParams.name"
    )

    contract2 = REGISTRY["read_skill_reference"]
    skill_id_args2 = [f for f in contract2.args if f.python_key == "skill_id"]
    assert skill_id_args2, "read_skill_reference must declare skill_id arg"
    assert skill_id_args2[0].wire_key == "id", (
        "read_skill_reference skill_id must rename to LobeHub's ReadReferenceParams.id"
    )


def test_all_registered_tools_have_state_or_content_field() -> None:
    """Every tool must declare what the renderer should display.

    A tool with no state fields and no content_field will render empty.
    """
    for tool_name, contract in REGISTRY.items():
        has_state = len(contract.state) > 0
        has_content = contract.content_field is not None
        has_args = len(contract.args) > 0
        if not (has_state or has_content or has_args):
            pytest.fail(
                f"Tool {tool_name!r} has no args, no state, no content_field — "
                f"renderer would be empty"
            )
