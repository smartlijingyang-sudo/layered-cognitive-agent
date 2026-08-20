"""Default cordis ctx must boot on a running loop without run_until_complete."""

from __future__ import annotations

import asyncio
import unittest

import lca.layer4_app.api as api


class TestDefaultCtxOnRunningLoop(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # ADR-0033 refactor moved the lazy-init cache to a holder dataclass
        # (``_default_ctx_holder``); reset it directly here.
        self._prev = api._default_ctx_holder.ctx
        api._default_ctx_holder.ctx = None

    async def asyncTearDown(self) -> None:
        api._default_ctx_holder.ctx = self._prev

    async def test_ensure_default_ctx_boots_on_running_loop(self) -> None:
        first, second = await asyncio.gather(api.ensure_default_ctx(), api.ensure_default_ctx())
        self.assertIs(first, second)
        self.assertIs(await api.ensure_default_ctx(), first)

    async def test_sync_lazy_boot_does_not_nest_the_running_loop(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            api.get_or_create_default_ctx()
        self.assertNotIn("already running", str(caught.exception).lower())
