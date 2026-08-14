"""Plane prompt templates — L0, no L1 dependency."""

from __future__ import annotations

import importlib.resources


def load_plane_prompt(name: str) -> str:
    try:
        return (
            importlib.resources.files("lca.layer0_infra.plane.prompts")
            .joinpath(f"{name}.md")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, TypeError) as exc:
        msg = f"Plane prompt template {name!r} not found"
        raise FileNotFoundError(msg) from exc
