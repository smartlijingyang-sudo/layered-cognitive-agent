"""Local PTY: a real short-lived process, no gateway."""

from __future__ import annotations

import asyncio

import pytest

from host.pty import LocalPty


@pytest.mark.asyncio
async def test_pty_runs_printf() -> None:
    chunks: list[str] = []
    done = asyncio.Event()

    async def emit(payload: dict) -> None:
        if payload.get("type") == "pty_output":
            chunks.append(str(payload.get("data") or ""))
        if payload.get("type") == "pty_exit":
            done.set()

    session = LocalPty("s1", emit, ["/bin/sh", "-c", "printf hi"], cols=40, rows=10)
    await session.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=3)
    finally:
        session.close()
    assert "hi" in "".join(chunks)
