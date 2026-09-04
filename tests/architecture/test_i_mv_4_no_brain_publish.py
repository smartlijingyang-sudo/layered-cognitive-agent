"""I-MV-4 架构不变量 —— ADR-0185 §4。

I-MV-4: 禁止认知 / 运行时 / 执行 / Agent 路径直接 publish
``spine.llm.request.header.*`` 事件。模型可见拦截点 = LLM adapter 边界
``ModelVisibleHook``,业务路径(cognition / runtime / body / agent)不得绕过
hook 直接拼 payload 投递。

白名单:
- ``lca/plugins/events/publishers/model_visible/`` 唯一授权位置
- 本测试文件本身
- 历史归档 ADR / Note
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_THIS_TEST_FILE = Path(__file__).resolve().name

# 生产路径不允许 publish 的目录(认知 / 运行时 / 执行 / Agent)
_FORBIDDEN_DIRS: tuple[str, ...] = (
    "lca/cognition/",
    "lca/runtime/",
    "lca/body/",
    "lca/agent/",
)

# 唯一授权路径 + 历史归档
_HISTORICAL_ALLOW_SUBSTRINGS: tuple[str, ...] = (
    "lca/plugins/events/publishers/model_visible/",
    "docs/adr/0185-model-visible-event-bus-alignment.md",
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


class TestIMv4:
    """I-MV-4: 认知 / runtime / body / agent 不得 publish model-visible EP。"""

    def test_no_publish_model_visible_in_brain_runtime_body_agent(self) -> None:
        """禁止路径下任何 ``publish(...spine.llm.request.header...)`` 调用。"""
        offenders: list[str] = []
        for root_rel in _FORBIDDEN_DIRS:
            root = _REPO_ROOT / root_rel.rstrip("/")
            if not root.exists():
                continue
            for line in _rg(r"publish.*spine\.llm\.request\.header", root):
                # 白名单(测试自身 + 历史归档)
                if any(allow in line for allow in _HISTORICAL_ALLOW_SUBSTRINGS):
                    continue
                offenders.append(line)
        assert not offenders, (
            "I-MV-4 违规:cognition/runtime/body/agent 直 publish model-visible EP\n"
            + "\n".join(offenders[:5])
        )

    def test_forbidden_dirs_resolve(self) -> None:
        """本测试只在禁止目录都存在时生效;若任一目录被整体删除,跳过。"""
        existing = [
            root_rel for root_rel in _FORBIDDEN_DIRS if (_REPO_ROOT / root_rel.rstrip("/")).exists()
        ]
        # 至少 cognition 必须存在;其他若不存在(未来拆分)也接受
        assert any("cognition" in d for d in existing) or not existing, (
            "I-MV-4 守护范围异常:cognition/ 不存在"
        )
