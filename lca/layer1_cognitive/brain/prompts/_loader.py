"""Load built-in prompt templates from the prompts/ package directory."""

from __future__ import annotations

import importlib.resources


def load_builtin_prompt(name: str) -> str:
    """Load a built-in prompt template by name.

    Args:
        name: Template filename without extension (e.g. ``"react_prompt"``).

    Returns:
        The template text as a string.

    Raises:
        FileNotFoundError: If the named template does not exist.
    """
    try:
        return (
            importlib.resources.files("lca.layer1_cognitive.brain.prompts")
            .joinpath(f"{name}.md")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, TypeError) as exc:
        available = [
            p.name
            for p in importlib.resources.files("lca.layer1_cognitive.brain.prompts").iterdir()
            if p.name.endswith(".md")
        ]
        msg = f"Built-in prompt template {name!r} not found. Available templates: {available}"
        raise FileNotFoundError(msg) from exc
