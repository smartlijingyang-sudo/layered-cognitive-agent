"""Execution surface is a profile: agent still sees /mnt/data."""

from __future__ import annotations

from lca.layer0_infra.sandbox.factory import set_sandbox_resolver
from lca.layer0_infra.sandbox.surface import (
    BACKEND_HOST,
    current_surface,
    environment_note,
    skill_preamble,
)


class _Host:
    name = "host"


def test_host_surface_keeps_guest_root() -> None:
    set_sandbox_resolver(lambda: _Host())  # type: ignore[arg-type,return-value]
    try:
        surface = current_surface()
        assert surface.backend == BACKEND_HOST
        assert surface.guest_root == "/mnt/data"
        note = environment_note(surface)
        assert "/mnt/data" in note
        assert "$HOME" in note or "家目录" in skill_preamble(surface)
        assert "CLOUD SANDBOX" not in note
    finally:
        set_sandbox_resolver(None)


def test_onlyboxes_surface_default() -> None:
    set_sandbox_resolver(lambda: None)
    try:
        surface = current_surface()
        assert surface.backend == "onlyboxes"
        assert "CLOUD SANDBOX" in environment_note(surface)
    finally:
        set_sandbox_resolver(None)
