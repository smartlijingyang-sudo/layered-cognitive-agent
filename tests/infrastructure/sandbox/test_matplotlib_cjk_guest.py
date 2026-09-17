"""Matplotlib CJK is a guest fact. Model rcParams must not drop Chinese glyphs.

run_22b8456caffd set font.sans-serif to WenQuanYi Zen Hei / Noto Sans CJK.
Those families are not on the worker. Glyphs fell back to DejaVu Sans. The
model then spent a turn on fc-list and hit the 300s wall clock.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_USER_OVERRIDE = r"""
import warnings
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "Noto Sans CJK"]
plt.rcParams["axes.unicode_minus"] = False
fig, ax = plt.subplots()
ax.set_title("资产负债结构")
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    fig.savefig({path!r}, dpi=80)
    plt.close(fig)
    missing = [str(item.message) for item in caught if "Glyph" in str(item.message) and "missing" in str(item.message).lower()]
print("MISSING" if missing else "OK")
"""


def _run(script: str) -> str:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_missing_family_override_drops_cjk_glyphs(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    out = tmp_path / "without_bootstrap.png"
    assert _run(_USER_OVERRIDE.format(path=str(out))) == "MISSING"
    assert out.is_file()


def test_bootstrap_keeps_cjk_after_missing_family_override(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    from lca.infrastructure.sandbox.cjk.matplotlib_guest import guest_bootstrap_source

    out = tmp_path / "with_bootstrap.png"
    script = guest_bootstrap_source() + _USER_OVERRIDE.format(path=str(out))
    assert _run(script) == "OK"
    assert out.is_file() and out.stat().st_size > 0
