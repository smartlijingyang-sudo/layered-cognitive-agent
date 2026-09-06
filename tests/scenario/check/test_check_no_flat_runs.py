"""check_no_flat_runs 单元测试 —— ADR-0065 PR-11。

脚本扫描 ``traces/runs/`` 顶层;只允许 ``run_<hex>/`` 目录。
测试用临时目录覆盖默认路径,不污染真实 traces。
"""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run_check(runs_dir: Path) -> tuple[int, str]:
    """直接 import 脚本模块,改 REPO/RUNS_DIR 后调 main() —— 不走 subprocess。"""
    if "scripts.check_no_flat_runs" in sys.modules:
        del sys.modules["scripts.check_no_flat_runs"]
    module = importlib.import_module("scripts.check_no_flat_runs")
    module.REPO = runs_dir.parent.parent
    module.RUNS_DIR = runs_dir
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = module.main()
    return rc, buf.getvalue().strip()


def _make_runs_dir() -> tuple[Path, tempfile.TemporaryDirectory]:
    """生成 ``<root>/traces/runs/`` 临时结构(模拟脚本默认布局)。"""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    runs_dir = root / "traces" / "runs"
    runs_dir.mkdir(parents=True)
    return runs_dir, tmp


class CheckNoFlatRuns(unittest.TestCase):
    def test_passes_when_only_per_run_dirs(self) -> None:
        runs_dir, tmp = _make_runs_dir()
        try:
            for run_id in ("run_aaa1", "run_bbb2"):
                (runs_dir / run_id).mkdir()
                (runs_dir / run_id / "journal.jsonl").write_text("{}", encoding="utf-8")
            rc, output = _run_check(runs_dir)
            self.assertEqual(rc, 0, msg=output)
            self.assertIn("OK", output)
        finally:
            tmp.cleanup()

    def test_fails_on_flat_jsonl(self) -> None:
        runs_dir, tmp = _make_runs_dir()
        try:
            (runs_dir / "run_aaa1.jsonl").write_text("{}", encoding="utf-8")
            rc, output = _run_check(runs_dir)
            self.assertEqual(rc, 1, msg=output)
            self.assertIn("run_aaa1.jsonl", output)
            self.assertIn("flat-file", output)
        finally:
            tmp.cleanup()

    def test_fails_on_flat_doctor_json(self) -> None:
        runs_dir, tmp = _make_runs_dir()
        try:
            (runs_dir / "run_aaa1.doctor.json").write_text("{}", encoding="utf-8")
            rc, output = _run_check(runs_dir)
            self.assertEqual(rc, 1, msg=output)
            self.assertIn("run_aaa1.doctor.json", output)
        finally:
            tmp.cleanup()

    def test_fails_on_unrelated_file(self) -> None:
        runs_dir, tmp = _make_runs_dir()
        try:
            (runs_dir / "README.txt").write_text("hi", encoding="utf-8")
            rc, output = _run_check(runs_dir)
            self.assertEqual(rc, 1, msg=output)
            self.assertIn("README.txt", output)
        finally:
            tmp.cleanup()

    def test_passes_when_runs_dir_missing(self) -> None:
        """traces/runs/ 不存在(全新环境) —— OK。"""
        tmp = tempfile.TemporaryDirectory()
        try:
            runs_dir = Path(tmp.name) / "traces" / "runs"
            rc, output = _run_check(runs_dir)
            self.assertEqual(rc, 0, msg=output)
        finally:
            tmp.cleanup()

    def test_classify_unrelated_under_per_run_dir(self) -> None:
        """per-run 目录内可有任意文件 — 脚本只扫顶层。"""
        runs_dir, tmp = _make_runs_dir()
        try:
            (runs_dir / "run_aaa1").mkdir()
            (runs_dir / "run_aaa1" / "junk.txt").write_text("hi", encoding="utf-8")
            rc, _ = _run_check(runs_dir)
            self.assertEqual(rc, 0)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
