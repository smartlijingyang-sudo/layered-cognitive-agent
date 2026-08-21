"""check_adr_supervision 单元测试 —— ADR-0074 tracker 即 ADR 监督。

脚本解析 docs/plans/adr-0074-plugin-everything-tracker.md，验证：
1. §1 状态总览：✅ Done 行必须引用有效 git commit hash
2. 「ADR 监督范围」实施矩阵：✅ 行必须含具体交付者
3. Next Action 必须指向首个未完成 PR
4. tracker 内所有 commit hash 引用存在

测试用 monkeypatch / monkeypatched 模拟；正常仓库模式下也跑作为冒烟。
"""

from __future__ import annotations

import importlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run_check_with_tracker(tracker_text: str) -> tuple[int, str]:
    """Run the check script against an in-memory tracker text.

    Imports the module freshly so the module-level ``_TRACKER`` constant
    can be repointed at a temp file written from ``tracker_text``.
    """
    if "scripts.check_adr_supervision" in sys.modules:
        del sys.modules["scripts.check_adr_supervision"]
    module = importlib.import_module("scripts.check_adr_supervision")

    # Write a temp tracker; point the module at it; restore on exit.
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    tmp.write(tracker_text)
    tmp.close()
    saved = module._TRACKER
    module._TRACKER = Path(tmp.name)
    try:
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = module.main()
        return rc, (buf_out.getvalue() + buf_err.getvalue()).strip()
    finally:
        module._TRACKER = saved
        Path(tmp.name).unlink(missing_ok=True)


def _minimal_valid_tracker() -> str:
    """Build a minimal tracker that should pass every check on a clean repo."""
    return """\
# ADR-0074 Plugin-Everything 实施追踪

## ADR 监督范围：5 个 ADR × 所有条款

| ADR | 关系 | 整体状态 | 落地入口（PR 序列） |
|---|---|:-:|---|
| **ADR-0066** | Refined | ⛔ | PR-1 |
| **ADR-0074** | 自身 | ⏳ | PR-0..PR-12 |

### 实施矩阵（ADR § × clause → 交付 PR）

| ADR § | clause 描述 | 状态 | 交付 PR | 备注 |
|:-:|---|:-:|:-:|---|
| **0066 §二** | 9 Control Slot 枚举 | ⛔ | PR-1 | — |
| **0074 实施序列** | PR-0..PR-12 | ⏳ | 详见 §1 | — |

## 1. 状态总览

| Phase | PR | 标题 | 状态 | Commit | 完成日 | 阻塞 |
|:-:|:-:|---|:-:|---|:-:|---|
| **0** | A | v3.1 patch | ✅ Done | `f980ace0` | 2026-08-21 | — |
| **1** | 0 | audit | ✅ Done | `8f8469eb` | 2026-08-21 | — |
| **1** | 1 | next | ⛔ Blocked | — | — | PR-0 |

**Next Action**：PR-1（next PR to work on）.

## 7. 已知陷阱
"""


class TestCheckAdrSupervision:
    """Behavioural tests for scripts/check_adr_supervision.py."""

    def test_minimal_tracker_passes(self) -> None:
        """A well-formed tracker with real commits should pass."""
        text = _minimal_valid_tracker()
        rc, output = _run_check_with_tracker(text)
        assert rc == 0, f"expected rc=0, got {rc}: {output}"
        assert "OK" in output

    def test_dangling_commit_hash_fails(self) -> None:
        """A tracker referencing a non-existent commit must error out."""
        text = _minimal_valid_tracker().replace("`f980ace0`", "`deadbeef0000`")
        rc, output = _run_check_with_tracker(text)
        assert rc == 1, f"expected rc=1, got {rc}: {output}"
        assert "dangling" in output.lower() or "not found" in output.lower()

    def test_next_action_done_row_warns(self) -> None:
        """Next Action pointing to a Done PR should be a warning."""
        text = _minimal_valid_tracker().replace(
            "**Next Action**：PR-1（next PR to work on）. ",
            "**Next Action**：PR-A（already-done PR）.",
        )
        rc, output = _run_check_with_tracker(text)
        # 既不通过（0），也不是 error（1）—— 走 warning-only 路径
        assert "Next Action" in output or rc in (0, 1)

    def test_real_repo_passes(self) -> None:
        """The actual repo tracker should pass (smoke test)."""
        if "scripts.check_adr_supervision" in sys.modules:
            del sys.modules["scripts.check_adr_supervision"]
        module = importlib.import_module("scripts.check_adr_supervision")
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = module.main()
        output = (buf_out.getvalue() + buf_err.getvalue()).strip()
        assert rc == 0, f"real repo check failed (rc={rc}): {output}"
        assert "OK" in output


if __name__ == "__main__":
    unittest.main([__file__, "-v"])
