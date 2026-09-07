"""回归锁:run_1f5360d2fa47 端到端修复验证。

run_1f5360d2fa47 是触发本次重构的根因 run:
- 用户问 "这个文件写了什么?" + 上传 文件分析报告.pdf
- 工具 sandbox 缺 pdftotext,``pdftotext x.pdf`` 三次连续 exit_code=127
- 旧行为:journal.step[3,4,5].tool_result.ok=True 但 error="exit_code=127"
  (矛盾样本),H7 报 100% 成功率 (false green)
- 新行为(本修复):H7.ok=False + detail 含 "工具结果矛盾 step(s)=[3,4,5]"
  + extra.tool_ok_error_conflicts=[3,4,5]

该文件以 ``run_1f5360d2fa47`` spine + manifest 副本为 fixture。
若 traces/runs/ 在仓库中不存在(轻量 clone),测试通过 pytest.skip 优雅降级。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.plugins.transport.webserver.doctor.doctor import diagnose_step_tree

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_DIR = REPO_ROOT / "traces" / "runs" / "run_1f5360d2fa47"


@pytest.fixture(scope="module")
def run_dir() -> Path:
    if not RUN_DIR.is_dir():
        pytest.skip(f"run_1f5360d2fa47 fixture not present at {RUN_DIR}")
    return RUN_DIR


def test_run_1f5360d2fa47_h7_detects_tool_result_contradiction(run_dir: Path) -> None:
    """回归锁:根因 run 在 H7 必须被识别为失败,detail 含矛盾 step 列表。

    修复前(原 bug):H7.ok=True, success_rate=1.0 —— 失真被遮蔽。
    修复后(本次):H7.ok=False, tool_ok_error_conflicts=[3, 4, 5] —— 显式失真。
    """
    journal = run_dir / "journal.json"
    assert journal.exists(), f"journal fixture missing at {journal}"
    report = diagnose_step_tree(journal)
    h7 = report.hops["H7"]
    assert h7.ok is False, (
        "H7 must flag tool_result contradiction; "
        f"got ok={h7.ok}, detail={h7.detail!r}"
    )
    assert "矛盾" in h7.detail or "tool_ok_error_conflicts" in (h7.extra or {}), (
        f"expected contradiction detail or extra, got detail={h7.detail!r} extra={h7.extra}"
    )
    extra = h7.extra or {}
    conflicts = extra.get("tool_ok_error_conflicts", [])
    # 原 run 三次 pdftotext 失败全部进 step 3 / 4 / 5 的 tool_result,
    # error 字段均为 exit_code=127 或 sh: 1: pdftotext: not found。
    assert sorted(conflicts) == [3, 4, 5], (
        f"expected contradictions at steps [3, 4, 5], got {conflicts}"
    )


def test_run_1f5360d2fa47_outcome_failed_with_broken_hop(run_dir: Path) -> None:
    """回归锁:outcome=failed 且 broken_hop 非空(H6 已正确)。"""
    journal = run_dir / "journal.json"
    report = diagnose_step_tree(journal)
    assert report.outcome == "failed"
    assert report.broken_hop in {"H6", "H7"}, (
        f"expected broken_hop H6 or H7, got {report.broken_hop}"
    )


def test_run_1f5360d2fa47_spine_has_pdftotext_failures(run_dir: Path) -> None:
    """回归锁:spine 中 ``phase.tool.call.end.ok=False`` 至少 2 个(三次 pdftotext 失败
    中至少 2 次被写入 ok=False)。

    这是 H7 多源对账路径的输入侧真实样本。
    """
    spine_path = run_dir / "run_1f5360d2fa47.spine.jsonl"
    assert spine_path.exists()
    ok_false = 0
    ok_true = 0
    for ln in spine_path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        rec = json.loads(ln)
        if rec.get("execution_point") == "phase.tool.call.end":
            payload = rec.get("payload") or {}
            if payload.get("ok") is False:
                ok_false += 1
            elif payload.get("ok") is True:
                ok_true += 1
    assert ok_false >= 2, f"expected >=2 spine ok=False for pdftotext, got {ok_false}"
    assert ok_true >= 1, f"expected >=1 spine ok=True (activate_skill), got {ok_true}"
