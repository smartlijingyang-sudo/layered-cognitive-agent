"""Built-in FieldSpec tuple factories for common tool patterns."""

from __future__ import annotations

from lca.layer0_infra.tools.contract.render import FieldSpec
from lca.layer0_infra.tools.contract.schema import COMMON


def sandbox_state() -> tuple[FieldSpec, ...]:
    """Standard sandbox observation state fields."""
    return (
        COMMON["stdout"],
        COMMON["stderr"],
        COMMON["files"],
        COMMON["exit_code"],
        COMMON["execution_env"],
        COMMON["error_summary"],
        COMMON["error_kind"],
    )


def skill_args() -> tuple[FieldSpec, ...]:
    """Common skill argv fields."""
    return (
        COMMON["skill_id"],
        COMMON["identifier"],
        COMMON["url"],
        COMMON["path"],
        COMMON["query"],
        COMMON["command"],
    )


def skill_state() -> tuple[FieldSpec, ...]:
    """Common skill observation state fields."""
    return (
        COMMON["name"],
        COMMON["title"],
        COMMON["description"],
        COMMON["has_resources"],
        COMMON["content"],
        COMMON["size"],
        COMMON["file_type"],
        COMMON["encoding"],
    )
