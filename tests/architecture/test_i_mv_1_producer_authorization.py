r"""I-MV-1 架构不变量 —— ADR-0185 §4。

I-MV-1: ``ModelVisiblePublisher`` 是 ``spine.llm.request.header`` 与
``spine.llm.request.header.assistant`` 两类 spine event 的唯一授权 producer。
生产路径必须通过 EventBus.publish(..., producer=ModelVisiblePublisher) 投递,
不允许任何业务方在 ``lca/`` 树下绕过 EventBus 直接 publish 这两类 category。

守护方式:``rg "publish.*spine\.llm\.request\.header" lca/`` 命中行必须仅落在
``lca/plugins/events/publishers/model_visible/`` 路径下,且全部通过
``EventBus.publish`` 入口(由 I-FW-BUS-1 守护)。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_THIS_TEST_FILE = Path(__file__).resolve().name
# model_visible publisher + hook(同一 plugin 体系,hook 在 publisher setup 时挂到 LLM adapter 链)
_ALLOWED_PATH_SUBSTRINGS: tuple[str, ...] = (
    "lca/plugins/events/publishers/model_visible/",
    "lca/plugins/events/hooks/model_visible/",
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
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                rel = path.relative_to(_REPO_ROOT)
                out.append(f"{rel}:{lineno}:{line}")
    return out


class TestIMv1:
    """I-MV-1: ModelVisiblePublisher 唯一授权 producer。"""

    def test_publish_call_only_in_publisher_plugin(self) -> None:
        """``bus.publish(...spine.llm.request.header...)`` 仅命中 publisher plugin。"""
        lca_root = _REPO_ROOT / "lca"
        if not lca_root.exists():
            pytest.skip("lca/ not found")
        matches = _rg(r"publish.*spine\.llm\.request\.header", lca_root)
        # 测试自身不在守范围
        filtered = [m for m in matches if _THIS_TEST_FILE not in m.split(":", 1)[0]]
        # 全部匹配必须落在 publisher + hook plugin 目录
        offenders = [
            m for m in filtered if not any(allow in m for allow in _ALLOWED_PATH_SUBSTRINGS)
        ]
        assert not offenders, (
            "I-MV-1 违规:spine.llm.request.header publish 调用不在 publisher / hook plugin 内\n"
            + "\n".join(offenders[:5])
        )

    def test_publisher_marker_only_authorized_class(self) -> None:
        """yaml 鉴权矩阵 + ownership 声明只把 ModelVisiblePublisher 标为授权 producer。"""
        publisher = _REPO_ROOT / "lca" / "plugins" / "events" / "publishers" / "model_visible"
        if not publisher.exists():
            pytest.skip("publisher plugin not found")
        marker_files = list(publisher.rglob("*.py"))
        assert marker_files, "publisher plugin directory has no .py files"
        marker_text = "\n".join(p.read_text(encoding="utf-8") for p in marker_files)
        assert "ModelVisiblePublisher" in marker_text
        assert "spine.llm.request.header" in marker_text
        assert "spine.llm.request.header.assistant" in marker_text
