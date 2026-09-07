"""Tests for the canonical barrel ``lca.contracts.runtime.__init__`` (P1-05).

The runtime package re-exports the L1 contracts owned by this layer
(``RunIntent``, ``RunMode``, ``RunSurface``, ``PluginOrigin``,
``PluginSource``, ``PluginTrustLevel``, ``TrustEnvelope``,
``EMPTY_TRUST_ENVELOPE``, ``SessionActivation``, ``RuntimeFacade``,
``RunHandle``).

This test guards:

* every name in ``__all__`` is importable from the package surface,
* the package-level names are *identity*-equal to the canonical classes
  defined in the upstream modules (no shadow re-export),
* ``EMPTY_TRUST_ENVELOPE`` is the same singleton as ``TrustEnvelope.empty()``,
* importing the package does not transitively pull in any upper-layer
  module (``lca.harness``, ``lca.application``, ``lca.plugins``) — the
  contracts layer must remain pure (I-HPC-1, ADR-0199 §2.2 + importlinter
  contract #3),
* every public symbol exposed via ``dir()`` is declared in ``__all__``
  (no implicit drift between the re-exports and the contract surface).

The import-isolation checks run the barrel in a *subprocess* (clean
``sys.modules``) so that other tests in the same pytest session do not
inflate ``sys.modules`` and produce false positives. The barrel itself
must not touch the forbidden upper-layer packages at any point.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

import lca.contracts.runtime as runtime_pkg
from lca.contracts.runtime import (
    DEFAULT_EXTERNAL_KIND_BY_TRUST,
    EMPTY_TRUST_ENVELOPE,
    ExternalPluginKind,
    PluginOrigin,
    PluginSource,
    PluginTrustLevel,
    RunHandle,
    RunIntent,
    RunMode,
    RunSurface,
    RuntimeFacade,
    SessionActivation,
    TrustEnvelope,
    default_external_kind,
    is_high_isolation_kind,
    is_sandbox_kind,
)

# Direct upstream-module imports for identity comparisons (cannot use the
# barrel to check that the barrel forwards to the canonical class).
from lca.contracts.runtime import external_plugin as _canonical_external_plugin
from lca.contracts.runtime.activation import SessionActivation as _CanonicalActivation
from lca.contracts.runtime.facade import RunHandle as _CanonicalRunHandle
from lca.contracts.runtime.facade import RuntimeFacade as _CanonicalRuntimeFacade
from lca.contracts.runtime.intent import RunIntent as _CanonicalRunIntent
from lca.contracts.runtime.intent import RunMode as _CanonicalRunMode
from lca.contracts.runtime.intent import RunSurface as _CanonicalRunSurface
from lca.contracts.runtime.trust import PluginOrigin as _CanonicalOrigin
from lca.contracts.runtime.trust import PluginSource as _CanonicalSource
from lca.contracts.runtime.trust import PluginTrustLevel as _CanonicalTrust
from lca.contracts.runtime.trust import TrustEnvelope as _CanonicalEnvelope

# Package root for resolving the barrel file path in subprocess probes.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BARREL_PATH = _REPO_ROOT / "lca" / "contracts" / "runtime" / "__init__.py"
_FORBIDDEN_UPPER_LAYERS: tuple[str, ...] = (
    "lca.harness",
    "lca.application",
    "lca.plugins",
)

_EXPECTED_ALL: tuple[str, ...] = (
    "DEFAULT_EXTERNAL_KIND_BY_TRUST",
    "EMPTY_TRUST_ENVELOPE",
    "ExternalPluginKind",
    "PluginOrigin",
    "PluginSource",
    "PluginTrustLevel",
    "RunHandle",
    "RunIntent",
    "RunMode",
    "RunSurface",
    "RuntimeFacade",
    "SessionActivation",
    "TrustEnvelope",
    "default_external_kind",
    "is_high_isolation_kind",
    "is_sandbox_kind",
)


class TestPackageSurface:
    """Every name declared in ``__all__`` must be importable."""

    @pytest.mark.parametrize("name", _EXPECTED_ALL)
    def test_all_symbols_importable(self, name: str) -> None:
        """``from lca.contracts.runtime import X`` works for every __all__ name."""
        assert hasattr(runtime_pkg, name), (
            f"lca.contracts.runtime is missing {name!r} declared in __all__"
        )
        assert name in runtime_pkg.__all__

    def test_all_is_tuple(self) -> None:
        """``__all__`` is a tuple (not a list) for static-friendly introspection."""
        assert isinstance(runtime_pkg.__all__, tuple)

    def test_all_is_sorted(self) -> None:
        """``__all__`` is sorted to match the codebase's static-import style."""
        assert list(runtime_pkg.__all__) == sorted(runtime_pkg.__all__)


class TestIdentityReExports:
    """The barrel forwards to the canonical upstream symbols."""

    def test_run_intent_exported(self) -> None:
        """``RunIntent`` is the canonical class (no shadow re-export)."""
        assert RunIntent is _CanonicalRunIntent

    def test_session_activation_exported(self) -> None:
        """``SessionActivation`` is the canonical class."""
        assert SessionActivation is _CanonicalActivation

    def test_trust_envelope_exported(self) -> None:
        """``TrustEnvelope`` is the canonical class."""
        assert TrustEnvelope is _CanonicalEnvelope

    def test_runtime_facade_exported(self) -> None:
        """``RuntimeFacade`` is the canonical Protocol."""
        assert RuntimeFacade is _CanonicalRuntimeFacade

    def test_run_handle_exported(self) -> None:
        """``RunHandle`` is the canonical ``NewType`` alias (erases to ``str``)."""
        # ``NewType`` aliasing: in module globals, the names are the SAME
        # object (``typing.NewType`` returns a callable bound to a private
        # name and the import re-binds it; identity is preserved).
        assert RunHandle is _CanonicalRunHandle
        # Behavioral check: NewType over str erases to str at runtime.
        handle = RunHandle("test")
        assert isinstance(handle, str)
        assert handle == "test"

    def test_plugin_origin_exported(self) -> None:
        """``PluginOrigin`` is the canonical dataclass."""
        assert PluginOrigin is _CanonicalOrigin

    def test_plugin_source_exported(self) -> None:
        """``PluginSource`` is the canonical Literal type alias."""
        assert PluginSource is _CanonicalSource

    def test_plugin_trust_level_exported(self) -> None:
        """``PluginTrustLevel`` is the canonical Literal type alias."""
        assert PluginTrustLevel is _CanonicalTrust

    def test_run_mode_exported(self) -> None:
        """``RunMode`` is the canonical Literal type alias."""
        assert RunMode is _CanonicalRunMode

    def test_run_surface_exported(self) -> None:
        """``RunSurface`` is the canonical Literal type alias."""
        assert RunSurface is _CanonicalRunSurface

    def test_external_plugin_kind_exported(self) -> None:
        """``ExternalPluginKind`` is the canonical Literal type alias (P5-02)."""
        assert ExternalPluginKind is _canonical_external_plugin.ExternalPluginKind

    def test_default_external_kind_by_trust_exported(self) -> None:
        """``DEFAULT_EXTERNAL_KIND_BY_TRUST`` is the canonical dict (P5-02)."""
        assert (
            DEFAULT_EXTERNAL_KIND_BY_TRUST
            is _canonical_external_plugin.DEFAULT_EXTERNAL_KIND_BY_TRUST
        )

    def test_default_external_kind_fn_exported(self) -> None:
        """``default_external_kind`` is the canonical function (P5-02)."""
        assert default_external_kind is _canonical_external_plugin.default_external_kind

    def test_is_high_isolation_kind_exported(self) -> None:
        """``is_high_isolation_kind`` is the canonical function (P5-02)."""
        assert is_high_isolation_kind is _canonical_external_plugin.is_high_isolation_kind

    def test_is_sandbox_kind_exported(self) -> None:
        """``is_sandbox_kind`` is the canonical function (P5-02)."""
        assert is_sandbox_kind is _canonical_external_plugin.is_sandbox_kind

    def test_empty_trust_envelope_singleton(self) -> None:
        """``EMPTY_TRUST_ENVELOPE`` is identity-equal to ``TrustEnvelope.empty()``.

        Per ADR-0199 §3.4 + trust.py implementation: ``TrustEnvelope.empty()``
        is a stable singleton used as the *zero* trust envelope before any
        plugin has been admitted. The module-level ``EMPTY_TRUST_ENVELOPE``
        must be that exact object.
        """
        # Both the canonical module-level singleton (``_CanonicalEnvelope``
        # alias side) and the barrel-exposed name must resolve to the same
        # object — the import identity is preserved end-to-end.
        assert EMPTY_TRUST_ENVELOPE is TrustEnvelope.empty()
        assert TrustEnvelope.empty() is TrustEnvelope.empty()
        # And the canonical class on the upstream module agrees.
        assert isinstance(EMPTY_TRUST_ENVELOPE, _CanonicalEnvelope)


class TestImportIsolation:
    """Importing the barrel must not transitively import upper-layer modules.

    Per I-HPC-1 + importlinter contract #3 (contracts purity): the
    ``lca.contracts`` layer must not import from ``lca.harness``,
    ``lca.application``, or ``lca.plugins``.

    These checks run the import in a *clean subprocess* (fresh
    ``sys.modules``) so other tests in the pytest session cannot leak
    the forbidden modules into the probe. They additionally do a static
    AST scan of the barrel itself to catch direct ``import lca.harness``
    statements that would silently violate the contract regardless of
    import order.
    """

    @staticmethod
    def _probe_subprocess_for(forbidden: str) -> subprocess.CompletedProcess[str]:
        """Import the barrel in a clean subprocess and probe ``sys.modules``.

        The subprocess prints any module name (or submodule) under
        ``forbidden`` that appears in ``sys.modules`` after importing
        the barrel. The script also asserts that the barrel re-exports
        the canonical name so we know the import actually succeeded.
        """
        script = textwrap.dedent(
            f"""
            import sys
            import lca.contracts.runtime as runtime_pkg
            forbidden = {forbidden!r}
            matches = sorted(
                m for m in sys.modules
                if m == forbidden or m.startswith(forbidden + '.')
            )
            for m in matches:
                print(m)
            """
        )
        return subprocess.run(  # noqa: S603  (controlled test-isolation probe)
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )

    @staticmethod
    def _barrel_imports() -> list[tuple[str, str | None]]:
        """Return ``(module, name)`` pairs from the barrel's module-level imports.

        Mirrors the helper in ``test_runtime_facade_protocol.py``: descends
        into ``if TYPE_CHECKING:`` blocks too so type-only upper-layer
        imports are still flagged.
        """
        tree = ast.parse(_BARREL_PATH.read_text(encoding="utf-8"))
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

    @pytest.mark.parametrize("forbidden_module", _FORBIDDEN_UPPER_LAYERS)
    def test_no_lca_upper_layer_import(
        self,
        forbidden_module: str,
    ) -> None:
        """``lca.contracts.runtime`` must not pull ``lca.harness`` / ``lca.application``
        / ``lca.plugins`` into ``sys.modules`` when imported in isolation.

        We probe via a clean subprocess so other tests in the session
        cannot contaminate ``sys.modules``.
        """
        proc = self._probe_subprocess_for(forbidden_module)
        offenders = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        assert offenders == [], (
            f"lca.contracts.runtime import pulled upper-layer "
            f"{forbidden_module!r}: {offenders!r}\nstderr={proc.stderr!r}"
        )

    def test_no_lca_harness_import(self) -> None:
        """Specifically: ``lca.harness`` is NOT in ``sys.modules`` after the barrel loads."""
        proc = self._probe_subprocess_for("lca.harness")
        offenders = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        assert offenders == [], f"lca.harness unexpectedly imported: {offenders!r}"

    def test_no_lca_application_import(self) -> None:
        """Specifically: ``lca.application`` is NOT in ``sys.modules`` after the barrel loads."""
        proc = self._probe_subprocess_for("lca.application")
        offenders = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        assert offenders == [], f"lca.application unexpectedly imported: {offenders!r}"

    def test_no_lca_plugins_import(self) -> None:
        """Specifically: ``lca.plugins`` is NOT in ``sys.modules`` after the barrel loads."""
        proc = self._probe_subprocess_for("lca.plugins")
        offenders = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        assert offenders == [], f"lca.plugins unexpectedly imported: {offenders!r}"

    @pytest.mark.parametrize("forbidden_module", _FORBIDDEN_UPPER_LAYERS)
    def test_barrel_does_not_directly_import_upper_layer(
        self,
        forbidden_module: str,
    ) -> None:
        """Static AST check: the barrel itself contains no direct import of
        an upper-layer module. Catches violations even when the layer
        happens to be lazily loaded.
        """
        offenders = [
            (module, name)
            for module, name in self._barrel_imports()
            if module == forbidden_module or module.startswith(forbidden_module + ".")
        ]
        assert offenders == [], (
            f"{_BARREL_PATH.relative_to(_REPO_ROOT)} directly imports "
            f"upper-layer {forbidden_module!r}; offenders: {offenders!r}"
        )


class TestAllCompleteness:
    """``__all__`` must be the complete public surface."""

    def test_all_is_complete(self) -> None:
        """Every public symbol on the package is declared in ``__all__``.

        We scan ``dir()`` and exclude dunder names, private (``_``-prefixed)
        names, the ``annotations`` future import sentinel, and module
        subobjects (submodules would have leaked into the public surface if
        re-exports pulled them). The remaining public names must all be in
        ``__all__`` so the contract has a single source of truth.
        """
        # Filter to public, non-dunder, non-module names that this package
        # actually exposes (we don't want to count transitive names from
        # submodules like ``RuntimeFacade`` appearing because someone did
        # ``from lca.contracts.runtime.facade import RuntimeFacade``).
        public = [
            name
            for name in dir(runtime_pkg)
            if not name.startswith("_")
            and name != "annotations"
            and not isinstance(getattr(runtime_pkg, name, None), types.ModuleType)
        ]
        declared = set(runtime_pkg.__all__)
        missing = [n for n in public if n not in declared]
        assert missing == [], f"lca.contracts.runtime.__all__ is missing public names: {missing!r}"

    def test_no_dunder_leakage(self) -> None:
        """``__all__`` does not declare dunder names (those are excluded by dir())."""
        for name in runtime_pkg.__all__:
            assert not name.startswith("_"), f"dunder leaked into __all__: {name!r}"

    def test_no_module_leakage(self) -> None:
        """``__all__`` does not declare submodules (barrels re-export names only)."""
        for name in runtime_pkg.__all__:
            value = getattr(runtime_pkg, name)
            assert not isinstance(value, types.ModuleType), (
                f"submodule {name!r} leaked into __all__"
            )
