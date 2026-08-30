"""Code sandbox adapters — Onlyboxes (Docker worker via console REST)."""

from lca.infrastructure.sandbox.factory import resolve_sandbox
from lca.infrastructure.sandbox.onlyboxes_adapter import OnlyboxesSandboxAdapter

__all__ = ["OnlyboxesSandboxAdapter", "resolve_sandbox"]
