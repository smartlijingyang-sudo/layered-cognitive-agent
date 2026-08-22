"""Default cordis ctx must boot on a running loop without run_until_complete."""

from __future__ import annotations

import asyncio
import threading
import unittest
from unittest.mock import patch

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


class TestDefaultCtxAcrossEventLoops(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_ctx = api._default_ctx_holder.ctx
        with api._default_ctx_holder.boot_lock:
            api._default_ctx_holder.ctx = None
            api._default_ctx_holder.booting = False
            api._default_ctx_holder.boot_complete.set()

    def tearDown(self) -> None:
        with api._default_ctx_holder.boot_lock:
            api._default_ctx_holder.ctx = self._previous_ctx
            api._default_ctx_holder.booting = False
            api._default_ctx_holder.boot_complete.set()

    def test_concurrent_event_loops_boot_once(self) -> None:
        barrier = threading.Barrier(3)
        boot_calls = 0
        boot_calls_lock = threading.Lock()
        results: list[object | None] = [None, None]
        failures: list[BaseException] = []

        async def fake_boot_profile(profile_path: str) -> object:
            nonlocal boot_calls
            self.assertEqual(profile_path, "profiles/web-standard.yaml")
            with boot_calls_lock:
                boot_calls += 1
            await asyncio.sleep(0.02)
            return object()

        def worker(index: int) -> None:
            try:

                async def get_context() -> object:
                    barrier.wait()
                    return await api.ensure_default_ctx()

                results[index] = asyncio.run(get_context())
            except BaseException as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        with patch("lca.harness.profile.boot.boot_profile", new=fake_boot_profile):
            threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()

        self.assertEqual(failures, [])
        self.assertEqual(boot_calls, 1)
        self.assertIs(results[0], results[1])
