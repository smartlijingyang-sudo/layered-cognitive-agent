"""RA-074 pin: ADR-0115 的倒置迁移已放弃,harness 模块不得再打出指向
不存在 ``lca_kernel.*`` 模块的 DeprecationWarning。

曾经的六处 import 时警告(``"lca.harness.profile.X is deprecated, use
lca_kernel.Y (ADR-0115)"``)指向从未创建的模块,每次 boot 都在误导。
本测试用源码扫描钉住:``lca/harness/profile`` 下不许再出现
``deprecated, use lca_kernel`` 字样。
"""
from __future__ import annotations

from pathlib import Path

PROFILE_ROOT = Path(__file__).resolve().parents[2] / "lca" / "harness" / "profile"


def test_no_bogus_adr0115_deprecation_warnings() -> None:
    offenders: list[str] = []
    for path in PROFILE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "deprecated, use lca_kernel" in text:
            offenders.append(str(path.relative_to(PROFILE_ROOT)))
    assert not offenders, (
        "bogus ADR-0115 deprecation warnings still present (they name "
        f"lca_kernel.* modules that do not exist): {offenders}"
    )
