"""ADR-0247 回归：run 装配把 USER.md profile backfill 回调接到 scope 能力上。

流程测试发现：生产路径构造 ``AssistantMemory`` 时未传 ``profile_backfill``，
USER.md 始终是空模板。本测试锁定装配 helper 的行为。
"""

from __future__ import annotations

import pytest

from lca.contracts.capabilities import ASSISTANT_PROFILE_BACKFILL
from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
    _profile_backfill_for_run,
)


class _FakeBackfillService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def backfill_from_records(self, assistant_id: str, records: object) -> object | None:
        self.calls.append((assistant_id, records))
        return None


class _FakeScope:
    def __init__(self, service: object) -> None:
        self._service = service

    def require(self, key: str) -> object:
        if key == ASSISTANT_PROFILE_BACKFILL.key:
            return self._service
        raise KeyError(key)


def test_profile_backfill_is_none_without_scope() -> None:
    assert _profile_backfill_for_run(None) is None


def test_profile_backfill_is_none_when_capability_missing() -> None:
    class _EmptyScope:
        def require(self, key: str) -> object:
            raise KeyError(key)

    assert _profile_backfill_for_run(_EmptyScope()) is None


@pytest.mark.asyncio
async def test_profile_backfill_wired_from_scope_capability() -> None:
    service = _FakeBackfillService()
    callback = _profile_backfill_for_run(_FakeScope(service))

    assert callback is not None
    await callback("asst_1", ["record"])
    assert service.calls == [("asst_1", ["record"])]
