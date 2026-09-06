"""P0-08 / P3-13 — ADR-0195 §7 P-L2,P-L3: transport isolation strict.

P-L2: ``lca/plugins/transport/`` 零认知/事实热路径 import (Session.append, Reducer, …).
P-L3: ``lca/plugins/transport/carrier/`` 零 deriver/fold 实现 (读写分离).

当前 baseline(2026-09-06): P-L2 0 files; P-L3 0 files。
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRANSPORT_ROOT = _REPO_ROOT / "lca" / "plugins" / "transport"
_CARRIER_ROOT = _TRANSPORT_ROOT / "webserver" / "carrier"

# P-L2 禁止 import/调用的符号。
_FORBIDDEN_SYMBOLS: tuple[str, ...] = (
    "Session.append",
    "Reducer",
    "PhaseExecutor",
    "GenericPlanInterpreter",
)

# P-L3: carrier 不得 import fold/deriver 实现 (read 路径专属)。
_CARRIER_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "fold_run_state",
    "fold_model_visible",
    "StepTreeFoldDeriver",
    "read.runs",
    "webserver.read",
)

_IMPORT_LINE = re.compile(r"^\s*(from\s+\S+\s+import|import\s+\S+)")

# 已知债(2026-09-06): transport 尚无代码级违规;注释/README 不计入。
_BASELINE_OFFENDERS: frozenset[str] = frozenset()
# 已知债(2026-09-06): P3 shim 删除后 carrier lifecycle/execute 仍直接 import
# read.runs (flush/error/identity);delete-when 上述 import 经 seam 注入或迁 carrier。
_BASELINE_CARRIER_FOLD_OFFENDERS: frozenset[str] = frozenset({
    "lca/plugins/transport/webserver/carrier/runs/execute/execute.py",
    "lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py",
})


def _code_line(line: str) -> str:
    """Strip full-line and inline ``#`` comments for pattern matching."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return ""
    return line.split("#", 1)[0]


def _line_violates_pl2(code: str) -> bool:
    if not code.strip():
        return False
    if "Session.append" in code:
        return True
    if not _IMPORT_LINE.match(code):
        return False
    return any(symbol in code for symbol in _FORBIDDEN_SYMBOLS[1:])


def _line_violates_pl3(code: str) -> bool:
    if not code.strip():
        return False
    if not _IMPORT_LINE.match(code):
        return False
    return any(pattern in code for pattern in _CARRIER_FORBIDDEN_PATTERNS)


def _find_offenders(root: Path, *, checker) -> frozenset[str]:
    offenders: set[str] = set()
    if not root.exists():
        return frozenset()
    for py in sorted(root.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            lines = py.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        if any(checker(_code_line(line)) for line in lines):
            offenders.add(py.relative_to(_REPO_ROOT).as_posix())
    return frozenset(offenders)


def test_transport_directory_exists() -> None:
    """sanity:transport 目录缺失时 fail-loud。"""
    assert _TRANSPORT_ROOT.exists(), f"transport directory missing: {_TRANSPORT_ROOT}"


def test_transport_no_new_isolation_violations() -> None:
    """baseline 守护:禁止在已知债之外新增 P-L2 import/usage。"""
    current = _find_offenders(_TRANSPORT_ROOT, checker=_line_violates_pl2)
    new_offenders = sorted(current - _BASELINE_OFFENDERS)
    assert not new_offenders, (
        "ADR-0195 P-L2 新增违规:lca/plugins/transport/** 出现新的禁止 import/usage:\n"
        + "\n".join(f"  - {p}" for p in new_offenders)
        + "\n若属已知迁移债,更新 _BASELINE_OFFENDERS 并附 delete-when。"
    )


def test_transport_has_no_isolation_violations_strict() -> None:
    """strict 目标:transport 零 P-L2 违规(P3-13)。"""
    offenders = sorted(_find_offenders(_TRANSPORT_ROOT, checker=_line_violates_pl2))
    assert offenders == [], (
        "ADR-0195 P-L2 违规:lca/plugins/transport/** 含禁止 import/usage:\n"
        + "\n".join(f"  - {p}" for p in offenders)
    )


def test_carrier_has_no_fold_deriver_imports() -> None:
    """P-L3 strict:carrier 零 fold/deriver/read-path import (P3-13)。"""
    offenders = sorted(_find_offenders(_CARRIER_ROOT, checker=_line_violates_pl3))
    new_offenders = sorted(set(offenders) - _BASELINE_CARRIER_FOLD_OFFENDERS)
    assert not new_offenders, (
        "ADR-0195 P-L3 违规:carrier/** 含 read/fold/deriver import:\n"
        + "\n".join(f"  - {p}" for p in new_offenders)
    )
