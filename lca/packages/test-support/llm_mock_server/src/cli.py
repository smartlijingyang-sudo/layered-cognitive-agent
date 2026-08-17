"""Auto-generated surface skeleton for upstream ``test-support/llm-mock-server/src/cli.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/llm-mock-server/src/cli.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "CONNECTION_REFUSED_BEHAVIOR",
    "MOCK_LLM_CLI_USAGE",
    "MockLlmCliConfig",
    "MockLlmCliParseResult",
    "parseMockLlmCliArgs",
]

MockLlmCliParseResult: TypeAlias = object  # port: surface stub

CONNECTION_REFUSED_BEHAVIOR = None  # port: surface stub

MOCK_LLM_CLI_USAGE = None  # port: surface stub

def parseMockLlmCliArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parseMockLlmCliArgs``."""
    raise NotImplementedError("port parseMockLlmCliArgs from test-support/llm-mock-server/src/cli.ts")

class MockLlmCliConfig(Protocol):
    """Surface stub for upstream interface ``MockLlmCliConfig``."""
    pass
