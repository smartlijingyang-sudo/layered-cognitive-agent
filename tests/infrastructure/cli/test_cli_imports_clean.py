"""CLI assembly imports cleanly after the dead ``diagnose`` command removal.

The v3 diagnostics module (``lca.infrastructure.observability.diagnostics``)
was deleted; the CLI command referencing it is removed too.  These tests
assert the surviving CLI packages load without ``import-not-found`` and the
retired command is no longer registered.
"""

from __future__ import annotations

import importlib


def test_cli_commands_package_imports_cleanly() -> None:
    commands = importlib.import_module("lca.infrastructure.cli.commands")
    assert not hasattr(commands, "diagnostics")


def test_cli_app_module_imports_cleanly() -> None:
    cli = importlib.import_module("lca.infrastructure.cli.cli.cli")
    assert hasattr(cli, "app")


def test_cli_app_no_longer_registers_diagnose_command() -> None:
    from lca.infrastructure.cli.cli.cli import app

    names = {
        cmd.name if cmd.name is not None else cmd.callback.__name__
        for cmd in app.registered_commands
    }
    assert "diagnose" not in names
    assert "diagnose-model-not-seen" not in names
    assert "diagnose-loop-stuck" not in names
    assert "diagnose-memory-poisoned" not in names
    assert "diagnose-approval-rejected" not in names
