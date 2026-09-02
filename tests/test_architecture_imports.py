"""Architecture import boundary guards (ADR-0176 D6)。

钉死的依赖方向:
- ``lca.cognition/**`` 不得 import  ``lca.infrastructure.observability.writable_matrix.coordinator``。
  业务 cognition 写路径必须通过 ``StepCoordinator`` Protocol(在
  ``lca.contracts.observability.writable_matrix`` 层 + registry)而非直接
  import coordinator 实现。
- 失败即 fail-fast(CI 必须红)。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COGNITION_DIR = ROOT / "lca" / "cognition"

# 业务 cognition 不应直接 import coordinator 实现。
# 注:这只是「单文件实现」 import 拦截;通过 Protocol / Registry 是允许的。
BANNED_IMPORT_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "writable_matrix.coordinator",
        "cognition 层禁止直接 import StepCoordinator 实现;"
        "业务侧应通过 contracts 层 Protocol + WritableFaceRegistry 解引用",
    ),
)

_BANNED_REGEX = re.compile(
    r"from\s+lca\.infrastructure\.observability\.writable_matrix\.coordinator"
    r"|import\s+lca\.infrastructure\.observability\.writable_matrix\.coordinator"
)


@pytest.mark.parametrize("banned", [name for name, _ in BANNED_IMPORT_PATTERNS])
def test_cognition_does_not_import_banned(banned: str) -> None:
    """扫描 lca/cognition/**.py 源码,确保不直接 import 被禁模块。"""
    offenders: list[str] = []
    if not COGNITION_DIR.exists():
        return
    for py in COGNITION_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if _BANNED_REGEX.search(text):
            offenders.append(str(py.relative_to(ROOT)))
    assert not offenders, (
        "lca/cognition/** 禁止 import writable_matrix.coordinator;违规:\n"
        + "\n".join(f"  - {p}" for p in offenders)
    )


def test_cognition_directory_exists() -> None:
    """sanity:测试本身在仓库迁移/重命名时能 fail-loud。"""
    assert COGNITION_DIR.exists(), f"cognition directory missing: {COGNITION_DIR}"
