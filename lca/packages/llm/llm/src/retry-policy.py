"""Auto-generated surface skeleton for upstream ``llm/llm/src/retry-policy.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``llm/llm/src/retry-policy.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AlwaysRetryPolicyConfig",
    "BackoffConfig",
    "NormalRetryPolicyConfig",
    "ResolvedAlwaysRetryPolicy",
    "ResolvedNormalRetryPolicy",
    "ResolvedRetryBackoff",
    "ResolvedRetryPolicy",
    "RetryPolicyConfig",
    "RetryPolicySchema",
    "resolveRetryPolicy",
]

ResolvedRetryPolicy: TypeAlias = object  # port: surface stub

RetryPolicyConfig: TypeAlias = object  # port: surface stub

RetryPolicySchema = None  # port: surface stub

def resolveRetryPolicy(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveRetryPolicy``."""
    raise NotImplementedError("port resolveRetryPolicy from llm/llm/src/retry-policy.ts")

class AlwaysRetryPolicyConfig(Protocol):
    """Surface stub for upstream interface ``AlwaysRetryPolicyConfig``."""
    pass

class BackoffConfig(Protocol):
    """Surface stub for upstream interface ``BackoffConfig``."""
    pass

class NormalRetryPolicyConfig(Protocol):
    """Surface stub for upstream interface ``NormalRetryPolicyConfig``."""
    pass

class ResolvedAlwaysRetryPolicy(Protocol):
    """Surface stub for upstream interface ``ResolvedAlwaysRetryPolicy``."""
    pass

class ResolvedNormalRetryPolicy(Protocol):
    """Surface stub for upstream interface ``ResolvedNormalRetryPolicy``."""
    pass

class ResolvedRetryBackoff(Protocol):
    """Surface stub for upstream interface ``ResolvedRetryBackoff``."""
    pass
