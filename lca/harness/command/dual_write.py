"""Shadow dual-write executor for migration safety (spec §B.3)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from lca.harness.diagnostics.normalizer import (
    DivergenceReport,
    ResultNormalizer,
)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ShadowConfig:
    """Configuration for shadow dual-write mode."""

    timeout_seconds: float = 30.0
    log_divergence: bool = True
    session_id: str = "shadow"


class ShadowExecutor:
    """Runs both legacy and new execution paths in shadow mode.

    Returns legacy result (authoritative during shadow phase).
    Logs divergence when results don't match.
    """

    def __init__(
        self,
        normalizer: ResultNormalizer | None = None,
        config: ShadowConfig | None = None,
    ) -> None:
        self._normalizer = normalizer or ResultNormalizer()
        self._config = config or ShadowConfig()

    async def execute_shadow(
        self,
        *,
        legacy_fn: Callable[[], Awaitable[Any]],
        new_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Run both paths concurrently, return legacy result.

        Args:
            legacy_fn: Callable that executes the legacy path.
            new_fn: Callable that executes the new harness path.

        Returns:
            The legacy result (authoritative during shadow).
        """
        legacy_task: asyncio.Task[Any] = asyncio.create_task(legacy_fn())  # type: ignore[arg-type]
        new_task: asyncio.Task[Any] = asyncio.create_task(new_fn())  # type: ignore[arg-type]

        # Wait for legacy (authoritative)
        legacy_result = await asyncio.wait_for(
            legacy_task,
            timeout=self._config.timeout_seconds,
        )

        # Wait for new (best-effort) — timeout/failure doesn't block legacy
        try:
            new_result = await asyncio.wait_for(
                new_task,
                timeout=self._config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            _log.warning("shadow_new_path_timeout")
            return legacy_result
        except Exception as exc:
            _log.warning("shadow_new_path_error", error=str(exc))
            return legacy_result

        # Compare (non-blocking)
        if self._config.log_divergence:
            try:
                report = self.compare(legacy_result, new_result, journal=[])
                if report.divergences:
                    _log.warning(
                        "shadow_divergence",
                        divergences=list(report.divergences),
                    )
            except Exception as exc:
                _log.warning("shadow_compare_error", error=str(exc))

        return legacy_result

    def compare(
        self,
        legacy_result: Any,
        new_result: Any,
        *,
        journal: list | None = None,
    ) -> DivergenceReport:
        """Compare normalized results from both paths."""
        norm_legacy = self._normalizer.from_task_result(legacy_result)
        norm_new = self._normalizer.from_projection(
            new_result,
            journal=journal or [],
        )

        divergences: list[str] = []
        if norm_legacy.status != norm_new.status:
            divergences.append(f"status: {norm_legacy.status} != {norm_new.status}")
        if norm_legacy.llm_calls != norm_new.llm_calls:
            divergences.append(f"llm_calls: {norm_legacy.llm_calls} vs {norm_new.llm_calls}")

        return DivergenceReport(
            session_id=self._config.session_id,
            divergences=tuple(divergences),
            legacy=norm_legacy,
            new=norm_new,
        )
