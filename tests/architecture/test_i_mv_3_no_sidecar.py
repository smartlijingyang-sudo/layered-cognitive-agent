"""I-MV-3 架构不变量 —— ADR-0185 §4。

I-MV-3: 禁止任何生产代码读 ``<run_dir>/model_visible/`` 旁路文件,或引用
旧 capture 默认实现类。该不变量在 PR-4 删旁路文件后由本测试守住,确保
未来回归时不会重新引入旁路文件目录约定或旧 capture 类。

白名单:
- ``docs/adr/0*.md`` 历史归档(0169 / 0175 / 0176 + 0185 自身)
- 本测试文件本身

已知边界:``lca/plugins/transport/webserver/handlers/runs/doctor/`` 的
run 体检路径仍会探测旧 run 目录里的旁路文件(诊断历史产物,只读报告);
其路径拼接不出现 ``model_visible/step_`` 字面模板,不在本守门 pattern 内。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_THIS_TEST_FILE = Path(__file__).resolve().name

# 历史归档 ADR + Note + 文档说明保留
_HISTORICAL_ALLOW_SUBSTRINGS: tuple[str, ...] = (
    "docs/adr/0169-loop-cursor-control.md",
    "docs/adr/0175-prompt-trace-into-model-visible.md",
    "docs/adr/0176-step-tree-deriver-closure-and-model-visible-dedup.md",
    "docs/adr/0185-model-visible-event-bus-alignment.md",
    "docs/notes/implemented/seam/2026-09-03-model-visible-incomplete-projection.md",
    "docs/notes/implemented/seam/2026-09-04-model-visible-bus-alignment.md",
    _THIS_TEST_FILE,
)


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    """Run ripgrep with relative paths; return list of matching lines."""
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                pattern,
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    out: list[str] = []
    for path in root.rglob("*"):
        if path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                rel = path.relative_to(_REPO_ROOT)
                out.append(f"{rel}:{lineno}:{line}")
    return out


class TestIMv3:
    """I-MV-3: 禁止旁路文件 / 旧 capture 类。"""

    def test_no_model_visible_step_dir_in_lca(self) -> None:
        """``lca/`` 下任何 .py 文件不得出现 ``model_visible/step_*`` 路径模板。"""
        lca_root = _REPO_ROOT / "lca"
        if not lca_root.exists():
            pytest.skip("lca/ not found")
        matches = _rg(r"model_visible/step_", lca_root)
        offenders = [
            m for m in matches if not any(allow in m for allow in _HISTORICAL_ALLOW_SUBSTRINGS)
        ]
        assert not offenders, "I-MV-3 违规:lca/ 仍引用 model_visible/step_* 旁路路径\n" + "\n".join(
            offenders[:5]
        )

    def test_no_std_model_visible_capture_in_lca_lca_kernel(self) -> None:
        """``StdModelVisibleCapture`` 在 lca/ + lca_kernel/ 下 = 0。"""
        offenders: list[str] = []
        for root in [_REPO_ROOT / "lca", _REPO_ROOT / "lca_kernel"]:
            if not root.exists():
                continue
            for line in _rg(r"StdModelVisibleCapture", root):
                if any(allow in line for allow in _HISTORICAL_ALLOW_SUBSTRINGS):
                    continue
                offenders.append(line)
        assert not offenders, "I-MV-3 违规:StdModelVisibleCapture 仍被引用\n" + "\n".join(
            offenders[:5]
        )

    def test_no_std_reasoner_prompt_capture_in_lca_lca_kernel(self) -> None:
        """``StdReasonerPromptCapture`` 在 lca/ + lca_kernel/ 下 = 0。"""
        offenders: list[str] = []
        for root in [_REPO_ROOT / "lca", _REPO_ROOT / "lca_kernel"]:
            if not root.exists():
                continue
            for line in _rg(r"StdReasonerPromptCapture", root):
                if any(allow in line for allow in _HISTORICAL_ALLOW_SUBSTRINGS):
                    continue
                offenders.append(line)
        assert not offenders, "I-MV-3 违规:StdReasonerPromptCapture 仍被引用\n" + "\n".join(
            offenders[:5]
        )

    def test_no_model_visible_capture_protocol_in_lca_lca_kernel(self) -> None:
        """``ModelVisibleCapture`` Protocol 在 lca/ + lca_kernel/ 下 = 0(测试自身除外)。"""
        offenders: list[str] = []
        for root in [_REPO_ROOT / "lca", _REPO_ROOT / "lca_kernel"]:
            if not root.exists():
                continue
            for line in _rg(r"\bModelVisibleCapture\b", root):
                if any(allow in line for allow in _HISTORICAL_ALLOW_SUBSTRINGS):
                    continue
                offenders.append(line)
        assert not offenders, "I-MV-3 违规:ModelVisibleCapture Protocol 仍被引用\n" + "\n".join(
            offenders[:5]
        )
