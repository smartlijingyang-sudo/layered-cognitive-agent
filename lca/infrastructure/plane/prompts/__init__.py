"""Plane prompt templates — L0, no L1 dependency."""

from __future__ import annotations

import importlib.resources


def load_plane_prompt(name: str) -> str:
    return load_plane_data(f"{name}.md")


def load_plane_data(filename: str) -> str:
    try:
        return (
            importlib.resources.files("lca.infrastructure.plane.prompts")
            .joinpath(filename)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, TypeError) as exc:
        msg = f"Plane prompt resource {filename!r} not found"
        raise FileNotFoundError(msg) from exc
