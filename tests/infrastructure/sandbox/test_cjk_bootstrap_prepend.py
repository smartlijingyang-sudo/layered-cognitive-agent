"""Python execute prepends the matplotlib CJK bootstrap. Harvest stubs do not."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.sandbox.onlyboxes.artifacts import ARTIFACT_BEGIN
from lca.infrastructure.sandbox.runtime.scope import bind_sandbox_runtime
from tests.support.inline_sandbox import InlineSandbox


@pytest.mark.asyncio
async def test_user_python_execute_prepends_cjk_bootstrap() -> None:
    tmp = tempfile.TemporaryDirectory()
    store = LocalFileStore(Path(tmp.name))
    sandbox = InlineSandbox()
    try:
        runtime = await bind_sandbox_runtime("run_cjk", sandbox, store, ())
        err = await runtime.ensure_ready()
        assert err is None
        await runtime.execute("print('user')", harvest_artifacts=True)
        user_codes = [code for _, code in sandbox.session_run_calls if "print('user')" in code]
        assert user_codes
        user = user_codes[0]
        assert "apply_matplotlib_cjk" in user
        assert "print('user')" in user
        harvest_codes = [code for _, code in sandbox.session_run_calls if ARTIFACT_BEGIN in code]
        assert harvest_codes
        assert all("apply_matplotlib_cjk" not in code for code in harvest_codes)
    finally:
        await runtime.destroy()
        tmp.cleanup()
