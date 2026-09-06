"""Search plane result models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    content: str = ""
    score: float = 0.0
    published_date: str = ""


@dataclass(frozen=True)
class SearchResponse:
    query: str
    provider: str
    results: tuple[SearchHit, ...] = ()
    answer: str = ""
    error: str = ""
    latency_ms: int = 0

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.results or self.answer)


@dataclass
class SearchRunState:
    """Run-scoped search routing state (mirrors LobeHub stepContext search flags)."""

    web_search_attempted: bool = False
    web_search_failed: bool = False
    prefer_llm_search: bool = False
    last_error: str = ""
    providers_tried: list[str] = field(default_factory=list)
