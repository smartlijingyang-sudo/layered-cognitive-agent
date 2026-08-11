"""Run-scoped search routing state — contextvar (mirrors LobeHub stepContext)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from lca.layer0_infra.search.models import SearchRunState

_search_state: ContextVar[SearchRunState | None] = ContextVar("lca_search_run_state", default=None)


def get_search_run_state() -> SearchRunState:
    current = _search_state.get()
    if current is None:
        current = SearchRunState()
        _search_state.set(current)
    return current


def reset_search_run_state() -> None:
    _search_state.set(SearchRunState())


@contextmanager
def search_run_scope() -> Iterator[SearchRunState]:
    token: Token = _search_state.set(SearchRunState())
    try:
        yield get_search_run_state()
    finally:
        _search_state.reset(token)


def mark_web_search_attempt(*, provider: str, ok: bool, error: str = "") -> None:
    state = get_search_run_state()
    state.web_search_attempted = True
    state.providers_tried.append(provider)
    if not ok:
        state.web_search_failed = True
        state.prefer_llm_search = True
        if error:
            state.last_error = error


def should_prefer_llm_search() -> bool:
    return get_search_run_state().prefer_llm_search
