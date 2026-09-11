"""Tests for ADR-0220 §7.3 — RuntimePlane.current_bindings() typed seam.

The seam exposes a per-turn ``BindingsViewBuilder`` to the graph layer;
``BindingsViewBuilder.build()`` projects it onto the typed
``BindingsView`` boundary DTO (replacing ``AgentState._xxx_ref``
private attrs).

Cases:
1. Default state: ``current_bindings()`` returns ``None`` — no
   per-turn bindings registered.
2. ``set_capability_bindings(builder)`` binds the builder; the
   ContextVar round-trip returns the same instance.
3. ``reset_capability_bindings(token)`` clears the binding;
   ``current_bindings()`` returns ``None`` again.
4. ``current_bindings_view()`` projects the builder onto a frozen
   ``BindingsView`` whose every field matches the builder's.
5. ``BindingsViewBuilder.build()`` with all ``None`` fields produces
   a valid (but empty) ``BindingsView`` — fall-through is a
   runtime wiring concern, not a builder concern.
6. Token leak: a second ``set_capability_bindings`` without
   resetting the first token does NOT raise at the seam (a caller
   bug); the reset path is the canonical release.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.models.cognition.boundary import BindingsView
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    current_bindings,
    current_bindings_view,
    reset_capability_bindings,
    set_capability_bindings,
)


@dataclass(frozen=True, slots=True)
class _FileStoreStub:
    name: str = "fs-stub"


@dataclass(frozen=True, slots=True)
class _SearchStub:
    name: str = "search-stub"


def test_default_seam_state_returns_none() -> None:
    """§7.3 — no per-turn binding registered → ``current_bindings()`` is None."""
    assert current_bindings() is None
    assert current_bindings_view() is None


def test_set_capability_bindings_round_trips_via_contextvar() -> None:
    """set + read returns the same ``BindingsViewBuilder`` instance."""
    builder = BindingsViewBuilder(file_store=_FileStoreStub())
    token = set_capability_bindings(builder)
    try:
        assert current_bindings() is builder
        assert current_bindings_view() is not None
        assert current_bindings_view().file_store is builder.file_store
    finally:
        reset_capability_bindings(token)
    assert current_bindings() is None


def test_reset_clears_seam_state() -> None:
    """``reset_capability_bindings(token)`` returns the seam to None."""
    builder = BindingsViewBuilder(search=_SearchStub())
    token = set_capability_bindings(builder)
    reset_capability_bindings(token)
    assert current_bindings() is None
    assert current_bindings_view() is None


def test_current_bindings_view_projects_typed_boundary_dto() -> None:
    """The seam projects onto the typed ``BindingsView`` boundary DTO."""
    fs = _FileStoreStub()
    sb = object()
    ss = object()
    builder = BindingsViewBuilder(
        file_store=fs,
        sandbox=sb,
        skill_store=ss,
        machine_resolver=None,
        search=_SearchStub(),
        bindings=None,
    )
    token = set_capability_bindings(builder)
    try:
        view = current_bindings_view()
        assert isinstance(view, BindingsView)
        assert view.file_store is fs
        assert view.sandbox is sb
        assert view.skill_store is ss
        assert view.machine_resolver is None
        assert view.search is not None
        assert view.bindings is None
    finally:
        reset_capability_bindings(token)


def test_builder_with_all_none_fields_still_emits_typed_view() -> None:
    """A builder with all ``None`` fields projects to a valid empty view."""
    view = BindingsViewBuilder().build()
    assert isinstance(view, BindingsView)
    assert view.file_store is None
    assert view.sandbox is None
    assert view.skill_store is None
    assert view.machine_resolver is None
    assert view.search is None
    assert view.bindings is None


def test_token_leak_silently_overwrites_previous_binding() -> None:
    """A second ``set_capability_bindings`` without resetting the first
    token does NOT raise — the seam is permissive to make setup
    ergonomic; the canonical release path is the matching reset.
    """
    builder_a = BindingsViewBuilder(file_store=_FileStoreStub(name="a"))
    builder_b = BindingsViewBuilder(file_store=_FileStoreStub(name="b"))
    token_a = set_capability_bindings(builder_a)
    token_b = set_capability_bindings(builder_b)
    try:
        assert current_bindings() is builder_b
    finally:
        reset_capability_bindings(token_b)
        reset_capability_bindings(token_a)
    assert current_bindings() is None


def test_builder_is_immutable() -> None:
    """``BindingsViewBuilder`` is a frozen dataclass — replacing fields
    raises ``dataclasses.FrozenInstanceError`` so accidental mutation
    in the runtime entry point fails loud.
    """
    builder = BindingsViewBuilder()
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError on CPython
        builder.file_store = object()  # type: ignore[misc]