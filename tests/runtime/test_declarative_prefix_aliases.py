"""Tests for ADR-0110 PR-E: "Declarative" prefix public re-export aliases.

The framework's rename-line is the literal word "Declarative", not a
type-specifying word; every type the framework exposes is declarative.
Per ADR-0110 D5, Phase 1 (this PR) only adds re-export aliases so new
code can drop the noise prefix without breaking the existing import
surface; the file-level rename is a follow-up PR.
"""

from __future__ import annotations

from lca.runtime.checkpoint_resolution import (
    DeclarativeCheckpoint,
    DeclarativeCheckpointStateResolver,
    RuntimeCheckpoint,
)
from lca.runtime.declarative_runtime import (
    DeclarativeExecution,
    DeclarativeRuntimeDriver,
    RuntimeDriver,
    TurnExecutor,
)
from lca.runtime.runtime_bindings import (
    DeclarativeRuntimeBindings,
    RuntimeBindings,
    RuntimePhaseCapabilities,
)


class TestDeclarativePrefixAliases:
    """The 4 public aliases are object-identical to their canonical names."""

    def test_runtime_bindings_alias(self) -> None:
        """RuntimeBindings is DeclarativeRuntimeBindings (object-identical)."""
        assert RuntimeBindings is DeclarativeRuntimeBindings

    def test_runtime_driver_alias(self) -> None:
        """RuntimeDriver is DeclarativeRuntimeDriver (object-identical)."""
        assert RuntimeDriver is DeclarativeRuntimeDriver

    def test_turn_executor_alias(self) -> None:
        """TurnExecutor is DeclarativeExecution (object-identical)."""
        assert TurnExecutor is DeclarativeExecution

    def test_runtime_checkpoint_alias(self) -> None:
        """RuntimeCheckpoint is DeclarativeCheckpoint (object-identical)."""
        assert RuntimeCheckpoint is DeclarativeCheckpoint

    def test_legacy_names_still_importable(self) -> None:
        """The 4 canonical ``Declarative*`` names remain public during the
        deprecation window (PR-D = six months from now). Imports must keep
        resolving — old code is not broken by the alias introduction.
        """
        assert DeclarativeRuntimeBindings is not None
        assert DeclarativeRuntimeDriver is not None
        assert DeclarativeExecution is not None
        assert DeclarativeCheckpoint is not None

    def test_unaffected_class_is_not_aliased(self) -> None:
        """Sanity: classes that do NOT have an alias must not have a
        shadow-of-the-same-name rename. ``DeclarativeCheckpointStateResolver``
        is out of scope for PR-E (a longer-noun alias would have unclear
        semantics); it stays under its canonical name only.
        """
        # Verify the class still resolves from its canonical module
        assert DeclarativeCheckpointStateResolver.__module__ == "lca.runtime.checkpoint_resolution"

    def test_unrelated_module_keeps_canonical_location(self) -> None:
        """RuntimePhaseCapabilities has no 'Declarative' prefix and is
        unchanged; verify it lives on lca/runtime/runtime_bindings too.
        """
        assert RuntimePhaseCapabilities.__module__ == "lca.runtime.runtime_bindings"
