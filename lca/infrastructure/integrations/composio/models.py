"""Composio integration DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ComposioToolDef:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ComposioConnection:
    identifier: str
    app_slug: str
    label: str
    connected_account_id: str
    auth_config_id: str
    user_id: str
    status: str
    redirect_url: str | None = None
    tools: list[ComposioToolDef] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status.upper() == "ACTIVE"
