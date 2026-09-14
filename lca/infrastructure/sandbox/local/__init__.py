"""Local host-backed Sandbox backend."""

from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter, default_local_root

__all__ = ["LocalSandboxAdapter", "default_local_root"]
