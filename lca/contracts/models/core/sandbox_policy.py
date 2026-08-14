"""SandboxPolicy — filesystem / network / env isolation contract.

Aligns with LobeHub ``@lobechat/device-sandbox`` SandboxPolicy.
Pure data — no enforcement here (ADR-0015).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxPolicy:
    """What a sandboxed process may touch."""

    writable_roots: tuple[str, ...]
    readable_roots: tuple[str, ...] | None = None
    denied_write_roots: tuple[str, ...] | None = None
    denied_read_roots: tuple[str, ...] | None = None
    allow_network: bool = True
    allowed_network_domains: tuple[str, ...] | None = None
    env_allowlist: tuple[str, ...] | None = None
    on_unavailable: str = "warn-allow"


DEFAULT_POLICY = SandboxPolicy(
    writable_roots=("/home/sandbox-user",),
    readable_roots=None,
    denied_write_roots=("/home/sandbox-user/.ssh", "/home/sandbox-user/.lca"),
    allow_network=True,
    allowed_network_domains=None,
)
