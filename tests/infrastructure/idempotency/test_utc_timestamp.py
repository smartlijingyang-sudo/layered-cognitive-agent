"""SqliteIdempotencyStore ``updated_at`` 走共享 UTC seam 的回归测试。

历史上 ``_timestamp()`` 用 ``datetime.now().astimezone()`` 落本地时区（潜在
正确性漂移）；本轮改为 ``utc_now_iso()``（``%Y-%m-%dT%H:%M:%SZ``）。这里直接
读 SQLite 列断言持久化值永远是 UTC ISO-8601，而不是本地时区偏移。
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

import pytest

from lca.infrastructure.idempotency.store import SqliteIdempotencyStore

_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _updated_at(path: str, plan_ref: str, key: str) -> str:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT updated_at FROM effect_idempotency WHERE plan_ref=? AND idempotency_key=?",
            (plan_ref, key),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None, "claim 必须已持久化 effect_idempotency 行"
    return str(row[0])


@pytest.mark.asyncio
async def test_claim_writes_utc_iso_timestamp(tmp_path) -> None:
    path = tmp_path / "idempotency.sqlite3"
    store = SqliteIdempotencyStore(path)
    assert (await store.claim("plan-1", "effect-1")).status == "new"

    updated_at = _updated_at(path, "plan-1", "effect-1")
    assert _ISO_UTC_RE.match(updated_at), f"updated_at 应为 UTC ISO-8601，得到 {updated_at!r}"
    parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_complete_updates_timestamp_in_utc(tmp_path) -> None:
    path = tmp_path / "idempotency.sqlite3"
    store = SqliteIdempotencyStore(path)
    await store.claim("plan-1", "effect-1")
    await store.complete("plan-1", "effect-1", {"receipt": "body.acted"})

    updated_at = _updated_at(path, "plan-1", "effect-1")
    assert _ISO_UTC_RE.match(updated_at), f"updated_at 应为 UTC ISO-8601，得到 {updated_at!r}"
