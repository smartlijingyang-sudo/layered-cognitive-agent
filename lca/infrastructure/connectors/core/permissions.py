"""Double-layer connector permissions engine (INV-04).

Layer 1: Provider OAuth Scopes (coarse-grained remote ticket).
Layer 2: LCA Action Permissions (fine-grained local switches: ALLOW / ASK / DENY).
Effective Permission = Scope_provider ∩ Action_LCA.
"""

from __future__ import annotations

import contextlib
import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.infrastructure.path.locator import get_lca_home


class ActionPermission(StrEnum):
    ALLOW = "ALLOW"
    ASK = "ASK"
    DENY = "DENY"


class ActionPermissionDeniedError(PermissionError):
    """Raised when an action is explicitly DENIED by user policy (INV-04)."""


class ActionCheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str  # "ALLOW", "ASK", "SCOPE_MISSING"
    permission: ActionPermission = ActionPermission.ALLOW
    missing_scope: str | None = None
    reason: str | None = None


class ConnectorPermissionEngine:
    """Evaluates the double-layer permission matrix for connector operations."""

    def __init__(self, user_id: str = "lca-local-user", lca_home: Path | None = None) -> None:
        self._user_id = user_id
        self._lca_home = lca_home or get_lca_home()

    def _get_permissions_file(self) -> Path:
        return self._lca_home / "users" / self._user_id / "connectors" / "permissions.json"

    def _load_permissions(self) -> dict[str, dict[str, str]]:
        file_path = self._get_permissions_file()
        if file_path.is_file():
            with contextlib.suppress(Exception):
                data = json.loads(file_path.read_text(encoding="utf-8"))
                return data.get("permissions", {})
        return {}

    def get_action_permission(self, service: str, action: str) -> ActionPermission:
        perms = self._load_permissions()
        service_perms = perms.get(service.lower(), {})
        if action in service_perms:
            val = service_perms[action].upper()
            try:
                return ActionPermission(val)
            except ValueError:
                pass

        # Safe defaults if not explicitly set
        act_lower = action.lower()
        if any(act_lower.startswith(w) for w in ("delete", "drop", "purge", "destroy")):
            return ActionPermission.DENY
        if any(w in act_lower for w in ("send", "write", "upload", "create", "modify", "merge")):
            return ActionPermission.ASK
        return ActionPermission.ALLOW

    def check_action(
        self,
        service: str,
        action: str,
        current_scopes: list[str],
        required_scope: str | None = None,
    ) -> ActionCheckResult:
        # Layer 1: Check Provider Scope
        if required_scope and required_scope not in current_scopes:
            return ActionCheckResult(
                status="SCOPE_MISSING",
                permission=ActionPermission.ASK,
                missing_scope=required_scope,
                reason=f"Provider OAuth scope '{required_scope}' is required.",
            )

        # Layer 2: Check LCA Action Permission
        perm = self.get_action_permission(service, action)
        if perm == ActionPermission.DENY:
            raise ActionPermissionDeniedError(
                f"Action '{action}' on service '{service}' is DENIED by user policy (INV-04)."
            )

        if perm == ActionPermission.ASK:
            return ActionCheckResult(
                status="ASK",
                permission=ActionPermission.ASK,
                reason="User policy requires human approval for this action.",
            )

        return ActionCheckResult(
            status="ALLOW",
            permission=ActionPermission.ALLOW,
        )
