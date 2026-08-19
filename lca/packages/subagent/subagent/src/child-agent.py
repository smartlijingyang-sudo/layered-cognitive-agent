"""Auto-generated surface skeleton for upstream ``subagent/subagent/src/child-agent.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``subagent/subagent/src/child-agent.ts``
"""


from __future__ import annotations

from typing import Protocol

__all__: list[str] = [
    "SUBAGENT_DELEGATION_CONTEXT",
    "ChildComposition",
    "ChildCreateInputs",
    "DelegatedPolicyOverrides",
    "SubagentDepthError",
    "appendDelegatedPolicyOverrides",
    "applyChildComposition",
    "captureDelegatedPolicyOverrides",
    "childSessionMeta",
    "resolveChildAgentOptions",
    "resolveChildDepth",
]

SUBAGENT_DELEGATION_CONTEXT = None  # port: surface stub

def appendDelegatedPolicyOverrides(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``appendDelegatedPolicyOverrides``."""
    raise NotImplementedError("port appendDelegatedPolicyOverrides from subagent/subagent/src/child-agent.ts")

def applyChildComposition(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``applyChildComposition``."""
    raise NotImplementedError("port applyChildComposition from subagent/subagent/src/child-agent.ts")

def captureDelegatedPolicyOverrides(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``captureDelegatedPolicyOverrides``."""
    raise NotImplementedError("port captureDelegatedPolicyOverrides from subagent/subagent/src/child-agent.ts")

def childSessionMeta(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``childSessionMeta``."""
    raise NotImplementedError("port childSessionMeta from subagent/subagent/src/child-agent.ts")

def resolveChildAgentOptions(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveChildAgentOptions``."""
    raise NotImplementedError("port resolveChildAgentOptions from subagent/subagent/src/child-agent.ts")

def resolveChildDepth(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveChildDepth``."""
    raise NotImplementedError("port resolveChildDepth from subagent/subagent/src/child-agent.ts")

class SubagentDepthError:
    """Surface stub for upstream class ``SubagentDepthError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SubagentDepthError.__init__ from subagent/subagent/src/child-agent.ts")

class ChildComposition(Protocol):
    """Surface stub for upstream interface ``ChildComposition``."""
    pass

class ChildCreateInputs(Protocol):
    """Surface stub for upstream interface ``ChildCreateInputs``."""
    pass

class DelegatedPolicyOverrides(Protocol):
    """Surface stub for upstream interface ``DelegatedPolicyOverrides``."""
    pass
