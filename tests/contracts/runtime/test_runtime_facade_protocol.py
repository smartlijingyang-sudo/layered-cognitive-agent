"""Tests for ``lca.contracts.runtime.facade.RuntimeFacade`` Protocol.

Scope (PR-0199-P1-04):
    - ``RuntimeFacade`` is ``@runtime_checkable`` (structural isinstance).
    - Minimal implementation with the three methods is an instance.
    - Missing-method objects are NOT instances.
    - ``RunHandle`` is a ``NewType``-over-``str`` (erases at runtime).
    - Method arity matches the contract.
    - Importing the module does not pull in ``lca.application`` /
      ``lca.harness`` / ``lca.plugins`` (I-HPC-1: contracts purity).
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path

import pytest

from lca.contracts.runtime.facade import (
    FORBIDDEN_UPPER_LAYER_IMPORTS,
    RunHandle,
    RuntimeFacade,
)

# ── fixtures ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _FakeActivation:
    """Stand-in for ``SessionActivation`` (used only as a return value)."""

    activation_ref: str = "act-fake"
    plan_ref: str = "plan-fake"
    graph_ref: str = "graph-fake"
    plugin_set_ref: str = "set-fake"
    profile_path: str = "p.yaml"
    session_id: str = "s-1"


class _MinimalFacade:
    """Concrete class structurally satisfying ``RuntimeFacade``."""

    def resolve_activation(self, intent):
        return _FakeActivation()

    def dispatch_run(self, activation, intent):
        return RunHandle("run-abc")

    def dispatch_resume(self, activation, run_id):
        return RunHandle("run-" + run_id)


class _MissingDispatchResume:
    """Concrete class missing ``dispatch_resume``."""

    def resolve_activation(self, intent):
        return None

    def dispatch_run(self, activation, intent):
        return RunHandle("run-abc")


# ── Protocol shape ──────────────────────────────────────────


class TestRuntimeFacadeProtocol:
    def test_runtime_facade_is_protocol(self) -> None:
        # ``__protocol_attrs__`` is set by the @runtime_checkable machinery.
        assert hasattr(RuntimeFacade, "__protocol_attrs__")

    def test_minimal_implementation_passes_protocol(self) -> None:
        assert isinstance(_MinimalFacade(), RuntimeFacade)

    def test_missing_method_fails_protocol(self) -> None:
        assert not isinstance(_MissingDispatchResume(), RuntimeFacade)

    def test_defines_expected_methods(self) -> None:
        for method in ("resolve_activation", "dispatch_run", "dispatch_resume"):
            assert hasattr(RuntimeFacade, method), method


# ── RunHandle semantics ────────────────────────────────────


class TestRunHandleNewType:
    def test_run_handle_is_str_subtype(self) -> None:
        # NewType erases to ``str`` at runtime (PEP 484).
        handle = RunHandle("abc")
        assert type(handle) is str
        assert handle == "abc"


# ── Method signatures ──────────────────────────────────────


class TestMethodSignatures:
    def test_resolve_activation_takes_intent_returns_activation(self) -> None:
        sig = inspect.signature(RuntimeFacade.resolve_activation)
        # ``Protocol`` instance methods always carry ``self`` as the first parameter.
        assert list(sig.parameters) == ["self", "intent"]
        # Under ``from __future__ import annotations`` the return annotation
        # is the literal string "SessionActivation".
        assert sig.return_annotation == "SessionActivation"

    def test_dispatch_run_takes_activation_and_intent_returns_handle(self) -> None:
        sig = inspect.signature(RuntimeFacade.dispatch_run)
        # ``dispatch_run`` carries the activation (already-resolved) plus
        # the originating RunIntent (PR-0199-P1-10) so the dispatcher can
        # see the user-facing request payload.
        assert list(sig.parameters) == ["self", "activation", "intent"]
        assert sig.return_annotation == "RunHandle"

    def test_dispatch_resume_takes_activation_and_run_id(self) -> None:
        sig = inspect.signature(RuntimeFacade.dispatch_resume)
        assert list(sig.parameters) == ["self", "activation", "run_id"]
        assert sig.return_annotation == "RunHandle"

    def test_protocol_method_arity(self) -> None:
        # Each method declares exactly the contract arity (excluding ``self``).
        resolve_params = list(inspect.signature(RuntimeFacade.resolve_activation).parameters)
        dispatch_run_params = list(inspect.signature(RuntimeFacade.dispatch_run).parameters)
        dispatch_resume_params = list(inspect.signature(RuntimeFacade.dispatch_resume).parameters)
        # All methods must include ``self``.
        assert resolve_params[0] == "self"
        assert dispatch_run_params[0] == "self"
        assert dispatch_resume_params[0] == "self"
        # Contract arity (excluding ``self``).
        # resolve_activation: 1 (intent)
        # dispatch_run:       2 (activation, intent) — PR-0199-P1-10
        # dispatch_resume:    2 (activation, run_id)
        assert len(resolve_params) - 1 == 1
        assert len(dispatch_run_params) - 1 == 2
        assert len(dispatch_resume_params) - 1 == 2


# ── Import isolation (I-HPC-1, importlinter contract #3) ────


def _collect_module_level_imports(path: Path) -> list[tuple[str, str | None]]:
    """Return ``(module, name)`` pairs for every import at module top-level.

    ``from X import Y`` → ``(X, Y)``; ``import X`` → ``(X, None)``.
    Imports inside ``if TYPE_CHECKING:`` blocks are still recorded — the
    contracts layer's importlinter forbids upper-layer imports regardless of
    whether they are type-check-time only.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[tuple[str, str | None]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, None))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append((module, alias.name))
        elif isinstance(node, ast.If):
            # Descend into ``if TYPE_CHECKING:`` blocks so we still catch
            # type-only upper-layer imports that would violate the contract.
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                for child in node.body:
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            imports.append((alias.name, None))
                    elif isinstance(child, ast.ImportFrom):
                        module = child.module or ""
                        for alias in child.names:
                            imports.append((module, alias.name))
    return imports


@pytest.mark.parametrize("forbidden", FORBIDDEN_UPPER_LAYER_IMPORTS)
def test_facade_does_not_import_upper_layer(forbidden: str) -> None:
    """``lca/contracts/runtime/facade.py`` must not import any upper-layer module.

    Per ADR-0199 I-HPC-1 and ``pyproject.toml`` importlinter contract #3
    (contracts purity: forbidden dependencies on ``lca.infrastructure``,
    ``lca.cognition``, ``lca.runtime``, ``lca.agent``, ``lca.application``,
    ``lca.harness``, ``lca.plugins``).
    """
    facade_path = (
        Path(__file__).resolve().parents[3] / "lca" / "contracts" / "runtime" / "facade.py"
    )
    assert facade_path.is_file(), facade_path

    offenders = [
        (module, name)
        for module, name in _collect_module_level_imports(facade_path)
        if module == forbidden or module.startswith(forbidden + ".")
    ]
    assert offenders == [], (
        f"{facade_path.relative_to(Path.cwd())} imports upper-layer "
        f"{forbidden!r}; offenders: {offenders!r}"
    )
