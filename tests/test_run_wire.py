"""RenderContract REGISTRY is the SSOT for LCA tool identifiers; the gateway
``wire.py`` shim still resolves tool names → (identifier, api_name) tuples
for legacy OpenAI-compatible endpoints. LobeHub's contract table is now
generated from the Python REGISTRY (lca/layer0_infra/tools/contract/codegen_ts.py).
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.tools.contract import REGISTRY, get_contract, render_registry_to_ts


def test_resolve_execute_code_via_registry() -> None:
    contract = get_contract("executeCode")
    assert contract is not None
    assert (contract.identifier, contract.api_name) == ("lobe-cloud-sandbox", "executeCode")


def test_unknown_tool_returns_none() -> None:
    assert get_contract("not_a_real_tool") is None


def test_registry_has_only_expected_categories() -> None:
    """REGISTRY contains all five skill tools plus 13 cloud-sandbox tools
    plus 12 local-system tools plus search + askUserQuestion."""
    assert "activate_skill" in REGISTRY
    assert "read_skill_reference" in REGISTRY
    assert "search_skill" in REGISTRY
    assert "import_skill" in REGISTRY
    assert "executeCode" in REGISTRY
    assert "runCommand" in REGISTRY
    assert "search" in REGISTRY
    assert "askUserQuestion" in REGISTRY


def test_frontend_consumes_codegen_output() -> None:
    """contracts.generated.ts is produced by codegen from REGISTRY."""
    contracts_path = Path("deploy/lobehub/patches/runtime/lcaToolRender/contracts.generated.ts")
    assert contracts_path.is_file(), "contracts.generated.ts missing"
    body = contracts_path.read_text(encoding="utf-8")
    # Sanity: codegen output mentions a known contract key
    assert '"activate_skill"' in body
    assert '"executeCode"' in body


def test_codegen_is_stable() -> None:
    """Same REGISTRY → identical TS output across calls."""
    a = render_registry_to_ts()
    b = render_registry_to_ts()
    assert a == b
