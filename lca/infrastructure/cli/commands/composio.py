"""Composio operator commands — status, connect, refresh, migrate."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import emit_report


def register(app: typer.Typer) -> None:
    composio_app = typer.Typer(
        help="LCA-native Composio OAuth connections (reads COMPOSIO_API_KEY from .env).",
        invoke_without_command=True,
    )
    app.add_typer(composio_app, name="composio")

    @composio_app.callback()
    def _composio_root(ctx: typer.Context) -> None:
        if ctx.invoked_subcommand is None:
            typer.echo(
                "composio — LCA-native Composio connection management\n"
                "  status   list local connections\n"
                "  connect  start OAuth for a service (e.g. google-drive)\n"
                "  refresh  poll Composio for connection status\n"
                "  migrate  import connections from LobeHub Postgres\n"
                "\n"
                "Examples:\n"
                "  ./scripts/lca-ops composio status\n"
                "  ./scripts/lca-ops composio connect google-drive\n"
                "  ./scripts/lca-ops composio refresh google-drive\n"
                "  ./scripts/lca-ops composio migrate --database-url $DATABASE_URL\n"
            )
            raise typer.Exit(0)

    @composio_app.command("status")
    def status_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON output"),
    ) -> None:
        """List Composio connections in the LCA connection store."""
        integration = _load_integration()
        rows = [
            _public_row(conn)
            for conn in integration.list_connections()
        ]
        if json_mode:
            emit_report({"connections": rows}, json_mode=True)
            return
        if not rows:
            typer.echo("No Composio connections.")
            return
        for row in rows:
            state = "connected" if row["connected"] else row["status"]
            typer.echo(f"{row['identifier']:20} {state:12} tools={row['tool_count']}")

    @composio_app.command("connect")
    def connect_cmd(
        service: str = typer.Argument(..., help="Composio service identifier, e.g. google-drive"),
        json_mode: bool = typer.Option(False, "--json", help="JSON output"),
        open_browser: bool = typer.Option(False, "--open", help="Open authorization URL"),
    ) -> None:
        """Create or resume an OAuth connection."""
        integration = _load_integration()
        conn = asyncio.run(integration.create_connection(service))
        row = _public_row(conn)
        if json_mode:
            emit_report(row, json_mode=True)
        elif conn.is_active:
            typer.echo(f"{conn.label} is already connected ({len(conn.tools)} tools).")
        else:
            typer.echo(f"Open this URL to authorize {conn.label}:\n{conn.redirect_url}")
            typer.echo(
                f"\nOAuth callback: {integration.settings.callback_url}\n"
                "The callback auto-refreshes; no manual refresh needed after sign-in."
            )
            if open_browser and conn.redirect_url:
                import webbrowser

                webbrowser.open(conn.redirect_url)

    @composio_app.command("refresh")
    def refresh_cmd(
        service: str = typer.Argument(..., help="Composio service identifier"),
        json_mode: bool = typer.Option(False, "--json", help="JSON output"),
    ) -> None:
        """Refresh connection status from Composio."""
        integration = _load_integration()
        try:
            conn = asyncio.run(integration.refresh_connection(service))
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        row = _public_row(conn)
        if json_mode:
            emit_report(row, json_mode=True)
            return
        if conn.is_active:
            typer.echo(f"{conn.label} connected — {len(conn.tools)} tools available.")
        else:
            typer.echo(f"{conn.label} status={conn.status} (not active yet).")

    @composio_app.command("migrate")
    def migrate_cmd(
        database_url: str = typer.Option(
            "",
            "--database-url",
            help="LobeHub DATABASE_URL (default: env DATABASE_URL)",
        ),
        input_json: Path | None = typer.Option(  # noqa: B008
            None,
            "--input",
            help="JSON rows export when Postgres driver unavailable",
        ),
        json_mode: bool = typer.Option(False, "--json", help="JSON output"),
    ) -> None:
        """One-time import of Composio connections from LobeHub DB or JSON."""
        from lca.infrastructure.integrations.composio.migrate_lobehub import (
            fetch_lobehub_rows,
            load_rows_from_json,
            migrate_rows,
        )

        integration = _load_integration()
        if input_json is not None:
            rows = load_rows_from_json(str(input_json))
        else:
            from lca.infrastructure.llm_adapter.factory import load_dotenv_if_present

            load_dotenv_if_present()
            url = database_url.strip() or os.environ.get("DATABASE_URL", "").strip()
            if not url:
                typer.echo("Provide --database-url or set DATABASE_URL in .env", err=True)
                raise typer.Exit(1)
            rows = fetch_lobehub_rows(url)

        result = migrate_rows(integration, rows)
        payload = {
            "imported": result.imported,
            "skipped": result.skipped,
            "identifiers": list(result.identifiers),
        }
        if json_mode:
            emit_report(payload, json_mode=True)
            return
        typer.echo(
            f"Imported {result.imported} connection(s), skipped {result.skipped}."
        )
        if result.identifiers:
            typer.echo("Imported: " + ", ".join(result.identifiers))


def _load_integration():
    from lca.infrastructure.integrations.composio.env_settings import (
        load_composio_settings_from_env,
    )
    from lca.infrastructure.integrations.composio.service import ComposioIntegration

    settings = load_composio_settings_from_env()
    return ComposioIntegration(settings)


def _public_row(conn: object) -> dict[str, object]:
    from lca.infrastructure.integrations.composio.env_settings import connection_to_public_dict

    return connection_to_public_dict(conn)
