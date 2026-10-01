"""Runtime row and Developer timestamp sections — ADR-0255 §1.3 & §1.4.

This module provides the deterministic runtime metadata row and the developer
timestamp message anchoring the agent's perception of "now".
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols.runtime.infra.infra import Tool


_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def render_runtime_row(
    *,
    session: str = "main chat",
    os_name: str = "linux",
    model: str = "Muse Spark",
    shell: str = "bash",
    chat: str = "main",
    depth: int = 0,
    max_depth: int = 2,
    can_spawn: bool = True,
) -> str:
    """Render the single-line runtime environment status (ADR-0255 §1.3)."""
    spawn_str = "yes" if can_spawn else "no"
    return (
        f"Runtime: session={session} | os={os_name} | model={model} | "
        f"shell={shell} | chat={chat} | depth={depth} | max_depth={max_depth} | "
        f"can_spawn={spawn_str}"
    )


def render_developer_timestamp(
    dt: datetime | None = None,
    *,
    tz_name: str = "Asia/Shanghai",
    device_id: str = "",
    sent_from: str = "web",
) -> str:
    """Render the developer timestamp message anchoring current time (ADR-0255 §1.4)."""
    if dt is None:
        cst = timezone(timedelta(hours=8), name="CST")
        dt = datetime.now(cst)
    weekday = _WEEKDAYS[dt.weekday()]
    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M:%S")
    tz_abbr = dt.tzname() or "CST"
    device_part = f" [device_id={device_id}]" if device_id else ""
    line1 = f"[{weekday} {date_str} {time_str} {tz_abbr}] [client_timezone={tz_name}]{device_part}"
    line2 = f"Sent from: {sent_from}"
    return f"{line1}\n{line2}"


class RuntimeEnvSection:
    """Pure section emitting the Runtime row."""

    name: ClassVar[str] = "runtime_env"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        del role_profile, tools
        return SectionOutput(text=render_runtime_row())


class DeveloperTimestampSection:
    """Pure section emitting the Developer timestamp message."""

    name: ClassVar[str] = "developer_timestamp"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        del role_profile, tools
        return SectionOutput(text=render_developer_timestamp())


def build_runtime_env(config: BaseModel) -> RuntimeEnvSection:
    del config
    return RuntimeEnvSection()


def build_developer_timestamp(config: BaseModel) -> DeveloperTimestampSection:
    del config
    return DeveloperTimestampSection()


__all__ = [
    "DeveloperTimestampSection",
    "RuntimeEnvSection",
    "build_developer_timestamp",
    "build_runtime_env",
    "render_developer_timestamp",
    "render_runtime_row",
]
