#!/usr/bin/env python3
"""Kernel / Transport 边界汇总检查(ADR-0115 决定 3 + ADR-0118)。

聚合三路检查,任何一路失败 exit 1:

1. ``pytest tests/lca_kernel/test_boundary.py`` —— AST 级 kernel 边界测试
   (transport framework import 守 + 文件数上限 + 单例守)。
2. ``pytest tests/lca_kernel/`` —— 全套 kernel 测试(K1–K8 + transport-isolation)。
3. ``lint-imports``(importlinter)—— ``kernel-domain-isolation`` 与
   ``transport-isolation`` 两个 contract。

Usage::

    python scripts/check_kernel_boundary.py [--json] [--skip-imports]

Exit codes:
    0  all green
    1  any check failed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class CheckResult:
    name: str
    ok: bool
    exit_code: int
    duration_s: float
    output_tail: str = ""
    note: str = ""


def _run(cmd: list[str], note: str = "", timeout_s: float = 180.0) -> CheckResult:
    """Run ``cmd`` via ``subprocess.run``, capture exit + tail of output."""
    import time

    name = cmd[0] if cmd else "<empty>"
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 — cmd is hard-coded by callers
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        duration = time.monotonic() - started
        stdout_tail = (proc.stdout or "")[-800:]
        stderr_tail = (proc.stderr or "")[-800:]
        output_tail = (
            stdout_tail + ("\n--- stderr ---\n" + stderr_tail if stderr_tail else "")
        ).strip()
        return CheckResult(
            name=name,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            duration_s=round(duration, 3),
            output_tail=output_tail,
            note=note,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name=name,
            ok=False,
            exit_code=124,
            duration_s=round(time.monotonic() - started, 3),
            output_tail=f"timeout after {timeout_s}s",
            note=note,
        )


def run_all(skip_imports: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []

    # 1. AST boundary tests
    results.append(
        _run(
            [
                "uv",
                "run",
                "pytest",
                "tests/lca_kernel/test_boundary.py",
                "--no-cov",
                "-q",
            ],
            note="AST-level kernel boundary (no transport imports, file count, no singletons)",
        )
    )

    # 2. Full kernel test suite
    results.append(
        _run(
            [
                "uv",
                "run",
                "pytest",
                "tests/lca_kernel/",
                "--no-cov",
                "-q",
            ],
            note="Full lca_kernel test suite (K1–K8 + boundary + boot events + HMR)",
        )
    )

    # 3. importlinter contracts
    if skip_imports:
        results.append(
            CheckResult(
                name="lint-imports",
                ok=True,
                exit_code=0,
                duration_s=0.0,
                output_tail="(skipped)",
                note="skipped via --skip-imports",
            )
        )
    else:
        results.append(
            _run(
                ["uv", "run", "lint-imports"],
                note="importlinter contracts (kernel-domain-isolation, transport-isolation)",
                timeout_s=300.0,
            )
        )

    return results


def _format_text(results: list[CheckResult]) -> str:
    lines = ["kernel/transport boundary check", "=" * 35, ""]
    for r in results:
        marker = "OK " if r.ok else "FAIL"
        lines.append(f"[{marker}] {r.name} (exit={r.exit_code}, {r.duration_s}s)")
        if r.note:
            lines.append(f"    note: {r.note}")
        if not r.ok and r.output_tail:
            lines.append("    --- output tail ---")
            for line in r.output_tail.splitlines()[-15:]:
                lines.append(f"    {line}")
    lines.append("")
    lines.append(f"summary: {sum(1 for r in results if r.ok)}/{len(results)} checks passed")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of text",
    )
    parser.add_argument(
        "--skip-imports",
        action="store_true",
        help="skip the lint-imports checks (faster, AST-level only)",
    )
    args = parser.parse_args(argv)

    results = run_all(skip_imports=args.skip_imports)
    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print(_format_text(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
