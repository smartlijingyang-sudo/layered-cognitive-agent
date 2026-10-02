"""Regression: ``_exec_terminal`` <-> ``_collect_outputs`` unbounded mutual recursion.

Before the fix, every successful ``_exec_terminal`` entered
``_collect_outputs``, whose ``ls``/``base64`` infrastructure calls went back
through ``_exec_terminal`` — and a successful inner call re-entered
collection, recursing until ``RecursionError`` (swallowed by
``_collect_outputs``'s ``except Exception``, so outputs were silently lost
and hundreds of redundant HTTP calls were issued).

The fix gates collection on a keyword-only ``_collect`` flag:
``_collect_outputs`` issues its infrastructure calls with
``_collect=False``. These tests drive the real (unstubbed) collection path
with a scripted mock HTTP client and assert it terminates after exactly the
expected calls.
"""

from __future__ import annotations

import base64
import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from lca.infrastructure.sandbox.onlyboxes.adapter import OnlyboxesSandboxAdapter
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


def _ok_response(stdout: str) -> MagicMock:
    """Mock response matching POST /api/v1/commands/terminal success."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = json.dumps({"exit_code": 0, "stdout": stdout, "stderr": ""})
    resp.ok = True
    return resp


class CollectRecursionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Same in-process-test pattern as test_onlyboxes_sandbox.py: the
        # observability facade's fail-loud record() needs a bound Session.
        self._publish_session_token = set_publish_session(Session("onlyboxes_collect_test"))

    def tearDown(self) -> None:
        reset_publish_session(self._publish_session_token)
        super().tearDown()

    def _adapter_with_scripted_posts(self):
        """Unlimited scripted responses keyed by command content.

        Deliberately unlimited (not a 3-item side_effect): on the unfixed
        code the recursion only stops via RecursionError, so an exhaustible
        script would mask the bug behind StopAsyncIteration.

        A hard call cap keeps the unfixed code from hanging forever: past
        the cap every call raises, the ``except Exception`` handlers in
        ``_collect_outputs`` swallow it and unwind, and the assertions
        below (entries == 1, exactly 3 calls) fail fast.
        """
        payload = base64.b64encode(b"plot-bytes").decode("ascii")
        calls = 0

        async def scripted_post(url: str, **kwargs: Any) -> MagicMock:
            nonlocal calls
            calls += 1
            if calls > 10:
                raise AssertionError(f"runaway _exec_terminal recursion ({calls} calls)")
            command = kwargs["json"]["command"]
            if "ls -1p" in command:
                return _ok_response("out.png\n")
            if "base64 -w0" in command:
                return _ok_response(payload)
            return _ok_response("hi\n")

        client = AsyncMock()
        client.post = AsyncMock(side_effect=scripted_post)
        client.aclose = AsyncMock()
        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="tok",  # noqa: S106
            client=client,
        )
        return adapter, client

    async def test_successful_exec_collects_outputs_without_recursion(self) -> None:
        """Real collection path terminates: 3 HTTP calls, 1 file collected."""
        adapter, client = self._adapter_with_scripted_posts()

        collect_entries = 0
        orig_collect = OnlyboxesSandboxAdapter._collect_outputs

        async def counting_collect(self, *, session_id: str = ""):
            nonlocal collect_entries
            collect_entries += 1
            return await orig_collect(self, session_id=session_id)

        with patch.object(OnlyboxesSandboxAdapter, "_collect_outputs", counting_collect):
            result = await adapter._exec_terminal("echo hi", invocation_id="t1")

        self.assertTrue(result.success)
        # Collection entered exactly once; inner ls/base64 did not re-enter.
        # (Unfixed code re-enters hundreds of times before RecursionError.)
        self.assertEqual(collect_entries, 1)
        # command + ls + base64, nothing more.
        self.assertEqual(client.post.await_count, 3)
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0].name, "out.png")
        self.assertEqual(result.generated_files[0].data, b"plot-bytes")

    async def test_collect_disabled_skips_output_sweep(self) -> None:
        """_collect=False performs the command with no collection sweep."""
        adapter, client = self._adapter_with_scripted_posts()

        result = await adapter._exec_terminal("echo hi", invocation_id="t1", _collect=False)

        self.assertTrue(result.success)
        self.assertEqual(client.post.await_count, 1)
        self.assertEqual(result.generated_files, ())
