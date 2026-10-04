"""Gmail Connector CLI driver (demo: staged-file flow, not yet wired to Gmail API).

Implements the INV-06 two-phase write guardrail (``--upload <staged_file>`` required).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.infrastructure.connectors.core.state import (
    ConnectionState,
    format_connector_auth_widget,
)
from lca.infrastructure.connectors.core.vault import ConnectorVault


class GmailConnectorCLI:
    """CLI executor for Gmail connector commands."""

    def __init__(self, vault: ConnectorVault | None = None) -> None:
        self._vault = vault or ConnectorVault()

    def execute(
        self,
        cmd_line: list[str],
        account_id: str = "default",
    ) -> dict[str, Any]:
        if not cmd_line:
            return {"error": "No command specified"}

        cmd = cmd_line[0]

        if cmd == "status":
            return self._handle_status(account_id)
        if cmd == "accounts":
            return self._handle_accounts()
        if cmd == "+send":
            return self._handle_send(cmd_line[1:], account_id)
        if cmd in ("+read", "+search"):
            return self._handle_read(cmd_line[1:], account_id)

        return {"error": f"Unknown Gmail command: {cmd}"}

    def _handle_status(self, account_id: str) -> dict[str, Any]:
        conn = self._vault.get_connection("gmail", account_id=account_id)
        if conn.state == ConnectionState.ACTIVE:
            return {
                "status": "active",
                "service": "gmail",
                "account_id": account_id,
                "connectionId": conn.connection_id or "",
            }

        conn_id = conn.connection_id or "ca_gmail_auth"
        auth_url = (
            conn.auth_url or f"https://backend.composio.dev/api/v1/auth/redirect?token={conn_id}"
        )
        # Zero Model URL Exposure: 真实 auth_url 只进 intent vault，
        # widget 标签与返回体只携带 intentId（与 composio 路径同模式）。
        from lca.infrastructure.connectors.core.intent_vault import get_default_intent_vault

        intent_id = get_default_intent_vault().create_intent(
            service="gmail",
            app_name="Gmail",
            auth_url=auth_url,
            connection_id=conn_id,
            user_id=account_id or "default",
        )
        widget = format_connector_auth_widget(
            app_name="Gmail",
            intent_id=intent_id,
            connection_id=conn_id,
        )
        return {
            "status": "not_connected",
            "service": "gmail",
            "account_id": account_id,
            "appName": "Gmail",
            "intentId": intent_id,
            "connectionId": conn_id,
            "widget": widget,
        }

    def _handle_accounts(self) -> dict[str, Any]:
        all_conns = self._vault.list_connections()
        gmail_conns = [c for c in all_conns if c.service == "gmail"]
        if not gmail_conns:
            # Default unconfigured stub
            return {
                "accounts": [
                    {
                        "account_id": "default",
                        "state": ConnectionState.NOT_CONNECTED,
                        "connection_id": None,
                    }
                ]
            }

        return {
            "accounts": [
                {
                    "account_id": c.account_id,
                    "state": c.state,
                    "connection_id": c.connection_id,
                }
                for c in gmail_conns
            ]
        }

    def _handle_send(self, args: list[str], default_account_id: str) -> dict[str, Any]:
        """Demo stub: stages a draft file and reports success; not wired to Gmail API."""
        # Parse arguments
        to_addr = ""
        subject = ""
        upload_path_str = ""
        account_id = default_account_id

        i = 0
        while i < len(args):
            flag = args[i]
            if flag == "--to" and i + 1 < len(args):
                to_addr = args[i + 1]
                i += 2
            elif flag == "--subject" and i + 1 < len(args):
                subject = args[i + 1]
                i += 2
            elif flag == "--upload" and i + 1 < len(args):
                upload_path_str = args[i + 1]
                i += 2
            elif flag == "--account" and i + 1 < len(args):
                account_id = args[i + 1]
                i += 2
            else:
                i += 1

        # INV-06: Two-Phase Write Guardrail
        if not upload_path_str:
            return {
                "success": False,
                "error": (
                    "INV-06 Safety Violation: +send requires '--upload <staged_file>'. "
                    "Inline body is forbidden to protect against prompt injection "
                    "and unreviewed outbound modifications."
                ),
            }

        upload_path = Path(upload_path_str)
        if not upload_path.is_file():
            return {
                "success": False,
                "error": f"Upload draft file not found: {upload_path}",
            }

        try:
            body = upload_path.read_text(encoding="utf-8")
        except Exception as exc:
            return {"success": False, "error": f"Failed to read draft file: {exc}"}

        return {
            "success": True,
            "to": to_addr,
            "subject": subject,
            "account_id": account_id,
            "upload_file": str(upload_path),
            "content_preview": body[:300],
            "message": f"Email successfully dispatched to {to_addr}",
        }

    def _handle_read(self, args: list[str], account_id: str) -> dict[str, Any]:
        """Demo stub: returns canned messages; not wired to Gmail API."""
        # Quick read metadata
        return {
            "success": True,
            "account_id": account_id,
            "messages": [
                {
                    "id": "msg_001",
                    "from": "notifications@github.com",
                    "subject": "New pull request review requested",
                    "snippet": "Alice requested your review on PR #42...",
                }
            ],
        }
