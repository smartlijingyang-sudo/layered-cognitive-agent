"""Auto-generated surface skeleton for upstream ``compaction/compaction-basic/src/summarizer.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``compaction/compaction-basic/src/summarizer.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "SummarizationInput",
    "SummaryResult",
    "frameSummary",
    "summarizeWithLlm",
]

SummaryResult: TypeAlias = object  # port: surface stub

def frameSummary(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``frameSummary``."""
    raise NotImplementedError("port frameSummary from compaction/compaction-basic/src/summarizer.ts")

def summarizeWithLlm(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``summarizeWithLlm``."""
    raise NotImplementedError("port summarizeWithLlm from compaction/compaction-basic/src/summarizer.ts")

class SummarizationInput(Protocol):
    """Surface stub for upstream interface ``SummarizationInput``."""
    pass
