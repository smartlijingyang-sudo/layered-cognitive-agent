"""Command Line Interface for LCA Local Companion (ADR-0246 M3)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from lca.infrastructure.computer.companion.client import CompanionClient, CompanionConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lca-companion",
        description="LCA Local Companion Daemon for User-Machine Execution",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: pair
    p_pair = subparsers.add_parser("pair", help="Pair this machine with LCA Gateway")
    p_pair.add_argument("--server", default="http://127.0.0.1:8765", help="Gateway URL")
    p_pair.add_argument("--device-id", default=None, help="Explicit device ID")
    p_pair.add_argument("--label", default=None, help="Device label")
    p_pair.add_argument("--token-file", default=None, help="Custom token file path")

    # Subcommand: start
    p_start = subparsers.add_parser("start", help="Start the companion daemon")
    p_start.add_argument("--server", default="http://127.0.0.1:8765", help="Gateway URL")
    p_start.add_argument("--token", default=None, help="Machine token override")
    p_start.add_argument("--device-id", default=None, help="Explicit device ID")
    p_start.add_argument("--label", default=None, help="Device label")
    p_start.add_argument("--token-file", default=None, help="Custom token file path")
    p_start.add_argument(
        "--allow-path",
        action="append",
        dest="allowed_paths",
        default=[],
        help="Permitted directory path",
    )
    p_start.add_argument(
        "--no-commands",
        action="store_false",
        dest="allow_commands",
        help="Disable command execution",
    )

    # Subcommand: status
    p_status = subparsers.add_parser("status", help="Show companion pairing status")
    p_status.add_argument("--token-file", default=None, help="Custom token file path")

    args = parser.parse_args()

    token_file = Path(args.token_file) if getattr(args, "token_file", None) else None

    if args.subcommand == "pair":
        cfg = CompanionConfig(
            server_url=args.server,
            token_file=token_file or Path.home() / ".lca" / "companion_token.json",
        )
        if args.device_id:
            cfg.device_id = args.device_id
        if args.label:
            cfg.label = args.label
        client = CompanionClient(cfg)
        try:
            asyncio.run(client.pair())
        except KeyboardInterrupt:
            print("\nPairing aborted by user.")
            sys.exit(130)
        except Exception as exc:
            print(f"\n[!] Pairing failed: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.subcommand == "start":
        cfg = CompanionConfig(
            server_url=args.server,
            token_file=token_file or Path.home() / ".lca" / "companion_token.json",
            allowed_paths=tuple(args.allowed_paths),
            allow_commands=args.allow_commands,
        )
        if args.token:
            cfg.machine_token = args.token
        if args.device_id:
            cfg.device_id = args.device_id
        if args.label:
            cfg.label = args.label
        client = CompanionClient(cfg)

        if not client.config.machine_token:
            print(
                "[!] No machine token found. Please run 'lca-companion pair' first.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(
            f"[*] Starting LCA Companion (device: {client.config.device_id}, label: {client.config.label})"
        )
        print(f"[*] Connecting to {client.config.server_url}...")
        try:
            asyncio.run(client.connect_and_run())
        except KeyboardInterrupt:
            print("\nCompanion stopped.")
            sys.exit(0)
        except Exception as exc:
            print(f"\n[!] Companion error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.subcommand == "status":
        cfg = CompanionConfig(
            token_file=token_file or Path.home() / ".lca" / "companion_token.json"
        )
        token = cfg.load_token()
        print(f"Token file: {cfg.token_file}")
        if token:
            print("Paired: Yes")
            print(f"Device ID: {cfg.device_id}")
            print(f"Label: {cfg.label}")
            print(f"Token: {token[:8]}...{token[-6:]}")
        else:
            print("Paired: No")


if __name__ == "__main__":
    main()
