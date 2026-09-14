"""Tests for ``check_profile_topology`` free function.

Six cases cover the contract:

- 3 distinct bundle paths → no error (clean profile)
- duplicate path → error naming the duplicated path
- reserved bundle id (``__init__``) → error
- underscore-prefixed bundle id → error
- empty profile (0 bundles) → no error
- single legal bundle → no error

The check is profile-level, not plan-level: it inspects the
profile's own bundle path list and never descends into any
individual bundle. Plan-level defects (typed-port wiring,
reachability, terminal policy) are covered by the other
``checks/`` submodules and their dedicated test files.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca_kernel.boot.plan_validation.checks.profile_topology import (
    check_profile_topology,
)


class TestProfileTopologyCheck:
    """Free-function check: same shape, no Plan fixture needed."""

    # ------------------------------------------------------------------
    # Case 1: 3 distinct bundle paths → no error
    # ------------------------------------------------------------------

    def test_three_distinct_paths_pass(self) -> None:
        """A profile with three unique bundle paths is structurally clean."""
        bundle_paths = (
            "bundles/phase_main_outer.yaml",
            "bundles/think.yaml",
            "bundles/act.yaml",
        )
        assert check_profile_topology(bundle_paths) == []

    # ------------------------------------------------------------------
    # Case 2: duplicate path → error
    # ------------------------------------------------------------------

    def test_duplicate_path_raises(self) -> None:
        """A bundle referenced twice produces a structural failure."""
        bundle_paths = (
            "bundles/phase_main_outer.yaml",
            "bundles/think.yaml",
            "bundles/phase_main_outer.yaml",
        )
        errors = check_profile_topology(bundle_paths)
        assert len(errors) == 1
        err = errors[0]
        assert isinstance(err, PlanLiftError)
        assert "duplicate" in str(err)
        assert "phase_main_outer.yaml" in str(err)

    def test_duplicate_path_isolated_to_offending_entry(self) -> None:
        """The duplicate error names the duplicated path, not the unique ones."""
        bundle_paths = (
            "bundles/a.yaml",
            "bundles/b.yaml",
            "bundles/a.yaml",
        )
        errors = check_profile_topology(bundle_paths)
        assert len(errors) == 1
        assert "a.yaml" in str(errors[0])
        assert "b.yaml" not in str(errors[0])

    # ------------------------------------------------------------------
    # Case 3: reserved bundle id (``__init__``) → error
    # ------------------------------------------------------------------

    def test_reserved_bundle_id_raises(self) -> None:
        """``__init__`` collides with Python package semantics → reject."""
        bundle_paths = ("bundles/__init__.yaml",)
        errors = check_profile_topology(bundle_paths)
        assert len(errors) == 1
        err = errors[0]
        assert isinstance(err, PlanLiftError)
        assert "__init__" in str(err)
        assert "reserved" in str(err)

    def test_reserved_pytest_ids_raise(self) -> None:
        """``test`` / ``fixture`` / ``conftest`` collide with pytest → reject."""
        for reserved in ("test", "fixture", "conftest"):
            errors = check_profile_topology((f"bundles/{reserved}.yaml",))
            assert len(errors) == 1, f"expected reject for {reserved!r}"
            assert reserved in str(errors[0])

    # ------------------------------------------------------------------
    # Case 4: underscore-prefixed bundle id → error
    # ------------------------------------------------------------------

    def test_underscore_prefixed_id_raises(self) -> None:
        """A bundle stem starting with ``_`` is a private convention → reject."""
        bundle_paths = ("bundles/_internal.yaml",)
        errors = check_profile_topology(bundle_paths)
        assert len(errors) == 1
        err = errors[0]
        assert isinstance(err, PlanLiftError)
        assert "_internal" in str(err)
        assert "underscore" in str(err) or "reserved" in str(err)

    def test_double_underscore_prefixed_id_raises(self) -> None:
        """``__anything`` is also underscore-prefixed → reject."""
        bundle_paths = ("bundles/__private.yaml",)
        errors = check_profile_topology(bundle_paths)
        assert len(errors) == 1
        assert "__private" in str(errors[0])

    # ------------------------------------------------------------------
    # Case 5: empty profile (0 bundles) → no error
    # ------------------------------------------------------------------

    def test_empty_profile_passes(self) -> None:
        """A profile with zero bundles is a valid empty profile → no error."""
        assert check_profile_topology(()) == []

    # ------------------------------------------------------------------
    # Case 6: single legal bundle → no error
    # ------------------------------------------------------------------

    def test_single_legal_bundle_passes(self) -> None:
        """A profile with one well-formed bundle is clean."""
        bundle_paths = ("bundles/phase_main_outer.yaml",)
        assert check_profile_topology(bundle_paths) == []

    # ------------------------------------------------------------------
    # Meta: the function returns ``list[PlanLiftError]`` consistently
    # ------------------------------------------------------------------

    def test_returns_list_type(self) -> None:
        """Even clean inputs return a (possibly empty) list, not None."""
        result = check_profile_topology(("bundles/x.yaml",))
        assert isinstance(result, list)
        assert all(isinstance(e, PlanLiftError) for e in result)

    def test_profile_name_is_reflected_in_error(self) -> None:
        """The error message names the profile, not ``<profile>``."""
        bundle_paths = ("bundles/__init__.yaml",)
        errors = check_profile_topology(
            bundle_paths, profile_name="my_profile"
        )
        assert len(errors) == 1
        assert "my_profile" in str(errors[0])

    def test_empty_bundle_path_raises(self) -> None:
        """A bundle entry that is itself the empty string is rejected."""
        bundle_paths = ("",)
        errors = check_profile_topology(bundle_paths)
        assert len(errors) >= 1
        assert any("empty" in str(e).lower() for e in errors)

    def test_trailing_slash_path_raises(self) -> None:
        """A path ending in ``/`` has no stem and is rejected."""
        bundle_paths = ("bundles/",)
        errors = check_profile_topology(bundle_paths)
        assert len(errors) >= 1
        assert any("empty" in str(e).lower() for e in errors)

    def test_yaml_extension_with_no_stem_raises(self) -> None:
        """``bundles/.yaml`` has an empty stem and is rejected."""
        bundle_paths = ("bundles/.yaml",)
        errors = check_profile_topology(bundle_paths)
        assert len(errors) >= 1
        assert any("empty" in str(e).lower() for e in errors)

    def test_multiple_independent_defects_each_raise(self) -> None:
        """Two independent defect classes both surface in the same call."""
        bundle_paths = (
            "bundles/__init__.yaml",   # reserved
            "bundles/_private.yaml",   # underscore-prefixed
        )
        errors = check_profile_topology(bundle_paths)
        # Reserved id and underscore-prefix id are independent findings.
        assert len(errors) == 2
        assert any("__init__" in str(e) for e in errors)
        assert any("_private" in str(e) for e in errors)
