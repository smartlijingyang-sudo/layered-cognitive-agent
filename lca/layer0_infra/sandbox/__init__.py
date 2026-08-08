"""Code sandbox adapters (ADR-0044) — E2B cloud / local microVM / Mock test double."""

from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.mock_adapter import MockSandboxAdapter

__all__ = ["MockSandboxAdapter", "resolve_sandbox"]
