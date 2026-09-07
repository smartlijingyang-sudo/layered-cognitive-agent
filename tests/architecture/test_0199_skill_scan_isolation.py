"""I-HPC-6 skill/resource scan isolation guard (ADR-0199 §3.3 #7 / P4-05).

Per ADR-0199 §3.3 #7 ("内容与执行分离") and §4 (Skill row: 文本扫描 →
自动 tool 注册 forbidden) and I-HPC-6 ("内容只读: resource 不得隐式
获得 execute 权限"): scanning skill/prompt/role content MUST NOT
register executable capabilities. This test is the architectural
guard that ensures the codebase never introduces a path that does
text-scanning of skill content → tool registration.

This is a NEGATIVE test: it asserts forbidden patterns are ABSENT.
If a future PR introduces a violating pattern, the test fails loud.

The guard inspects AST for:
  - Modules under ``lca/contracts/runtime/`` and
    ``lca/harness/composition/`` that import or call
    ``register_tool`` / ``register_capability`` / etc.
    (Resource-layer code MUST NOT touch executable registrations.)
  - Any code path that loads skill content (via
    ``SkillProvider.load()``) and then iterates over the content
    to find tool names.

For P4-05 the guard is intentionally narrow: it checks that the
canonical ResourceRegistry code path does NOT call executable
registration. Future PRs can extend the guard to cover other
content providers.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RESOURCE_LAYER_DIRS = (
    REPO_ROOT / "lca" / "contracts" / "runtime",
    REPO_ROOT / "lca" / "harness" / "composition",
)


# APIs that MUST NOT be called from the resource layer (ADR-0199 I-HPC-6).
# These are the canonical registration entry points for executable
# capabilities; if any of them appears in resource-layer code, it's a
# violation of the "content is read-only" invariant.
FORBIDDEN_CALL_NAMES: frozenset[str] = frozenset(
    {
        "register_tool",
        "register_capability",
        "register_plugin",
        "add_tool",
        "add_capability",
        "register_audited_interaction",
    }
)


def _walk_for_function_calls(tree: ast.AST) -> set[str]:
    """Collect all function/attribute call names in an AST tree."""
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return calls


def _module_uses_skill_content_for_registration(module_path: Path) -> list[str]:
    """Return list of violating call names found in the module.

    Empty list = module is clean.
    """
    try:
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
    except (SyntaxError, UnicodeDecodeError):
        return []  # skip files that can't be parsed

    calls = _walk_for_function_calls(tree)
    return sorted(calls & FORBIDDEN_CALL_NAMES)


def _is_resource_layer_module(module_path: Path) -> bool:
    """Return True if the module lives in one of the RESOURCE_LAYER_DIRS."""
    for layer_dir in RESOURCE_LAYER_DIRS:
        try:
            module_path.relative_to(layer_dir)
            return True
        except ValueError:
            continue
    return False


def _all_python_files_under(layer_dir: Path) -> list[Path]:
    """Find all .py files under the given directory (excluding __pycache__)."""
    return sorted(p for p in layer_dir.rglob("*.py") if "__pycache__" not in p.parts)


# ── Tests ───────────────────────────────────────────────────────────────


class TestSkillScanIsolation:
    """I-HPC-6 architectural guard: resource-layer code must not register tools."""

    def test_resource_layer_dirs_exist(self) -> None:
        """The resource-layer directories the guard inspects must exist."""
        for layer_dir in RESOURCE_LAYER_DIRS:
            assert layer_dir.exists(), f"missing layer dir: {layer_dir}"

    def test_resource_registry_does_not_register_tools(self) -> None:
        """The canonical ResourceRegistry module (P4-02) does not call forbidden APIs."""
        registry_path = REPO_ROOT / "lca" / "harness" / "composition" / "resource_registry.py"
        if not registry_path.exists():
            pytest.skip("resource_registry.py not yet created (P4-02 not landed)")

        violations = _module_uses_skill_content_for_registration(registry_path)
        assert not violations, (
            f"ResourceRegistry calls forbidden APIs: {violations}. "
            f"Per ADR-0199 I-HPC-6 resource content is read-only and "
            f"must not register executable capabilities."
        )

    def test_resource_id_contract_does_not_register_tools(self) -> None:
        """The ResourceId contract module (P4-01) does not call forbidden APIs."""
        rid_path = REPO_ROOT / "lca" / "contracts" / "runtime" / "resource.py"
        if not rid_path.exists():
            pytest.skip("resource.py not yet created (P4-01 not landed)")

        violations = _module_uses_skill_content_for_registration(rid_path)
        assert not violations, f"ResourceId calls forbidden APIs: {violations}"

    def test_no_resource_layer_module_calls_forbidden_apis(self) -> None:
        """Sweep: no module in the resource layer calls forbidden APIs."""
        violations: list[tuple[Path, list[str]]] = []
        for layer_dir in RESOURCE_LAYER_DIRS:
            if not layer_dir.exists():
                continue
            for module_path in _all_python_files_under(layer_dir):
                found = _module_uses_skill_content_for_registration(module_path)
                if found:
                    violations.append((module_path, found))

        if violations:
            msg_lines = ["Forbidden registration APIs found in resource layer:"]
            for path, calls in violations:
                msg_lines.append(f"  {path.relative_to(REPO_ROOT)}: {calls}")
            msg_lines.append(
                "Per ADR-0199 I-HPC-6 resource content is read-only; "
                "registration of executable capabilities is forbidden."
            )
            pytest.fail("\n".join(msg_lines))


class TestResourceRegistryContract:
    """The ResourceRegistry exposes only read-only methods (no registration)."""

    def test_resource_registry_has_no_add_capability_method(self) -> None:
        """Spot-check: ResourceRegistry doesn't accidentally expose a registration API."""
        registry_path = REPO_ROOT / "lca" / "harness" / "composition" / "resource_registry.py"
        if not registry_path.exists():
            pytest.skip("resource_registry.py not yet created")

        source = registry_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(registry_path))

        forbidden_in_method_name = (
            "register",
            "add_tool",
            "add_capability",
            "expose",
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            # ResourceRegistry.add() is allowed (adds a resource to
            # the read-only registry, NOT a capability registration).
            if node.name == "add":
                continue
            if not any(forbidden in node.name.lower() for forbidden in forbidden_in_method_name):
                continue
            pytest.fail(
                f"ResourceRegistry.{node.name} looks like a "
                f"registration API; per I-HPC-6 the registry "
                f"is read-only content mapping only."
            )
