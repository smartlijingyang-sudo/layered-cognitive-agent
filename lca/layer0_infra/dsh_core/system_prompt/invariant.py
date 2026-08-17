"""1:1 port of ``@deepseek-ai/dsh-system-prompt/invariant``.

Package-owned prompt-assembly invariants.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from lca.layer0_infra.dsh_core.system_prompt import PromptAssembly

PACKAGE_NAME: str = "@deepseek-ai/dsh-system-prompt"
_VARIABLE_NAME: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")

# ---------------------------------------------------------------------------
# Invariant types (from ``@deepseek-ai/dsh-invariants``)
# ---------------------------------------------------------------------------

InvariantFailure = Callable[[str], None]
InvariantInstaller = Callable[["object", InvariantFailure], None]

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------

name: str = "system-prompt-invariant"
"""Cordis companion plugin name."""

inject: tuple[str, ...] = ("invariants",)
"""Service required before the companion can reserve package ownership."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_assembly(assembly: PromptAssembly, fail: InvariantFailure) -> None:
    """Validate the authoritative assembly returned by the waterfall."""
    section_names: set[str] = set()
    for section in assembly.sections:
        if len(section.name) == 0:
            fail("assembled section names must be non-empty")
        if section.name in section_names:
            fail(f'assembled section name "{section.name}" is duplicated')
        section_names.add(section.name)
        if not isinstance(section.text, str):
            fail(f'assembled section "{section.name}" text must be a string')

    context_names: set[str] = set()
    for context in assembly.contexts:
        if len(context.name) == 0:
            fail("assembled context names must be non-empty")
        if context.name in context_names:
            fail(f'assembled context name "{context.name}" is duplicated')
        context_names.add(context.name)
        if not isinstance(context.text, str):
            fail(f'assembled context "{context.name}" text must be a string')

    for tool in assembly.tools:
        if len(tool.name) == 0:
            fail("assembled tool names must be non-empty")

    for var_name, value in assembly.variables.items():
        if not _VARIABLE_NAME.match(var_name):
            fail(f'assembled variable name "{var_name}" is invalid')
        if value is not None and not isinstance(value, str):
            fail(f'assembled variable "{var_name}" must be a string or None')


# ---------------------------------------------------------------------------
# Installer
# ---------------------------------------------------------------------------


def _install(ctx: object, fail: InvariantFailure) -> None:
    """Install validation around the authoritative assembly waterfall result."""

    async def on_assemble(
        assembly: PromptAssembly, context: object, next_: Callable
    ) -> PromptAssembly:
        assembled: PromptAssembly = await next_()
        validate_assembly(assembled, fail)
        return assembled

    ctx.on("system-prompt/assemble", on_assemble, global_=True, prepend=True)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def apply(ctx: object) -> Callable[[], None]:
    """Register the system-prompt invariant companion.

    Returns:
        The installed registration's disposer after setup succeeds.
    """
    ctx.invariants.register(PACKAGE_NAME, _install)  # type: ignore[attr-defined]
    return lambda: None
