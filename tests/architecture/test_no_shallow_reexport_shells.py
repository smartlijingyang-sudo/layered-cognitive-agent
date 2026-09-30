"""Structural guards for the no-``utils`` / no-re-export-shell cleanup.

This round deletes shallow re-export/compat facades so callers import the
concrete implementation directly:

* ``capability/composio/composio.py`` → ``integrations.composio.service.service``
* ``sandbox/paths/paths.py`` → merged into ``sandbox.factory.factory``
* ``host_runtime/providers/user.py`` → ``providers.user_{account,cli,workspace}``
* ``cognition/body/delegation/cache.py`` → ``infrastructure.delegation.cache``

These guards pin the end state: the shells are gone and the concrete
modules remain importable at their canonical locations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_DELETED_REL_PATHS = (
    "lca/infrastructure/capability/composio/composio.py",
    "lca/infrastructure/sandbox/paths/paths.py",
    "lca/infrastructure/sandbox/paths/__init__.py",
    "lca/infrastructure/host_runtime/providers/user.py",
    "lca/cognition/body/delegation/cache.py",
)

_DELETED_MODULES = (
    "lca.infrastructure.capability.composio.composio",
    "lca.infrastructure.sandbox.paths.paths",
    "lca.infrastructure.host_runtime.providers.user",
    "lca.cognition.body.delegation.cache",
)


def test_reexport_shells_no_longer_exist() -> None:
    """The deleted facade modules are gone from the source tree."""
    missing = [p for p in _DELETED_REL_PATHS if (REPO / p).exists()]
    assert not missing, f"re-export shells should be deleted: {missing}"


def test_importing_deleted_shells_raises() -> None:
    """Importing a deleted shell fails loudly instead of resolving elsewhere."""
    for module in _DELETED_MODULES:
        with pytest.raises(ModuleNotFoundError):
            __import__(module)


def test_concrete_modules_are_importable() -> None:
    """The canonical implementation modules expose the moved symbols."""
    from lca.contracts.models.core.state.guest_layout import join_under, outputs_under
    from lca.infrastructure.delegation.cache import (
        cached_delegation_observation,
        tag_delegation_extra,
    )
    from lca.infrastructure.host_runtime.providers.user_account import UserProvider
    from lca.infrastructure.host_runtime.providers.user_cli import CLIProvider
    from lca.infrastructure.host_runtime.providers.user_workspace import WorkspaceProvider
    from lca.infrastructure.integrations.composio.service.service import ComposioIntegration
    from lca.infrastructure.sandbox.factory.factory import ONLYBOXES, GuestLayout

    assert callable(cached_delegation_observation)
    assert callable(tag_delegation_extra)
    assert issubclass(UserProvider, object)
    assert issubclass(CLIProvider, object)
    assert issubclass(WorkspaceProvider, object)
    assert isinstance(ComposioIntegration, type)
    assert isinstance(ONLYBOXES, GuestLayout)
    assert callable(join_under)
    assert callable(outputs_under)


def test_renamed_utils_modules_are_importable() -> None:
    """The renamed modules keep their public helpers under new names."""
    from lca.infrastructure.cli.services.process.proc_scan import (
        find_pid_by_argv,
        port_listening,
    )
    from lca.infrastructure.observability.narrative.formatting import (
        attr_text,
        wrap_words,
    )

    assert callable(attr_text)
    assert callable(wrap_words)
    assert callable(find_pid_by_argv)
    assert callable(port_listening)


__all__ = [
    "test_concrete_modules_are_importable",
    "test_importing_deleted_shells_raises",
    "test_reexport_shells_no_longer_exist",
    "test_renamed_utils_modules_are_importable",
]
