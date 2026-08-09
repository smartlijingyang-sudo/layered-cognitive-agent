"""Code sandbox adapters — Onlyboxes (Docker worker via console REST)."""

from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.onlyboxes_adapter import OnlyboxesSandboxAdapter

__all__ = ["OnlyboxesSandboxAdapter", "resolve_sandbox"]
