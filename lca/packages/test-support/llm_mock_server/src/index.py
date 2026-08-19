"""Auto-generated surface skeleton for upstream ``test-support/llm-mock-server/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/llm-mock-server/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_MOCK_LLM_RANDOM_WEIGHTS",
    "MAX_MOCK_LLM_TIMER_DELAY_MS",
    "MOCK_LLM_BEHAVIORS",
    "ConcreteMockLlmBehavior",
    "MockLlmBehavior",
    "MockLlmRandomWeights",
    "MockLlmRequestOutcome",
    "MockLlmRequestRecord",
    "MockLlmServer",
    "MockLlmServerEvent",
    "MockLlmServerOptions",
    "startMockLlmServer",
]

ConcreteMockLlmBehavior: TypeAlias = object  # port: surface stub

MockLlmBehavior: TypeAlias = object  # port: surface stub

MockLlmRandomWeights: TypeAlias = object  # port: surface stub

MockLlmRequestOutcome: TypeAlias = object  # port: surface stub

MockLlmServerEvent: TypeAlias = object  # port: surface stub

DEFAULT_MOCK_LLM_RANDOM_WEIGHTS = None  # port: surface stub

MAX_MOCK_LLM_TIMER_DELAY_MS = None  # port: surface stub

MOCK_LLM_BEHAVIORS = None  # port: surface stub

def startMockLlmServer(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``startMockLlmServer``."""
    raise NotImplementedError("port startMockLlmServer from test-support/llm-mock-server/src/index.ts")

class MockLlmRequestRecord(Protocol):
    """Surface stub for upstream interface ``MockLlmRequestRecord``."""
    pass

class MockLlmServer(Protocol):
    """Surface stub for upstream interface ``MockLlmServer``."""
    pass

class MockLlmServerOptions(Protocol):
    """Surface stub for upstream interface ``MockLlmServerOptions``."""
    pass
