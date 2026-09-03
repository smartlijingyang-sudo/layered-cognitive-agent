"""record 单一入口架构不变量 —— ADR-0183 §3.5 + PR-5。

不变量 I-FW-REC-1: ``build_record()``（lca_kernel/events/spine_runtime.py）是
唯一 record 构造入口。``lca/plugins/events/sinks/*/sink.py`` 内不允许:
- ``_build_event_record`` 等私有 record 构造器定义
- ``Channel(`` / ``Outcome(`` 字面构造 + ``except ValueError`` 静默枚举
  fallback
落盘 sink 必须经 ``build_record(`` 构造 record。

验收基线（ADR-0183 PR-5）:
- rg "_build_event_record" lca/ = 0
- rg "except ValueError" lca/plugins/events/sinks/ = 0

``lca_kernel/events/spine_runtime.py`` docstring 以旧 ``_build_event_record``
名作 SSOT 模块说明,非定义点,不在本不变量扫描范围（lca/）内。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

# 仓库根 = tests/architecture/ 的父父目录
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    """Run ripgrep with relative paths; return list of matching lines.

    Empty list = no matches. Falls back to pathlib walk if rg is missing.
    """
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603  # path is a constant binary
            [  # noqa: S607  # rg binary located via shutil.which()
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
        # rg exit code 1 = no matches; 0 = matches; >1 = error
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    # Fallback: pathlib walk
    compiled = re.compile(pattern)
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                rel = path.relative_to(_REPO_ROOT)
                out.append(f"{rel}:{lineno}:{line}")
    return out


class TestIFwRec1:
    """I-FW-REC-1: build_record() 单一 record 构造入口。"""

    def test_no_private_record_builder_in_lca(self) -> None:
        """PR-5: ``_build_event_record`` 反推构造器在 lca/ 内收口 = 0。"""
        matches = _rg(r"_build_event_record", _REPO_ROOT / "lca")
        assert not matches, (
            "I-FW-REC-1 违规:lca/ 内仍有 _build_event_record 引用;"
            "record 构造必须走 build_record()\n" + "\n".join(matches[:5])
        )

    def test_no_except_value_error_in_event_sinks(self) -> None:
        """PR-5: events sinks 内 ``except ValueError`` 静默枚举 fallback = 0。"""
        sinks_root = _REPO_ROOT / "lca" / "plugins" / "events" / "sinks"
        if not sinks_root.exists():
            pytest.skip("lca/plugins/events/sinks/ not found")
        matches = _rg(r"except ValueError", sinks_root)
        assert not matches, (
            "I-FW-REC-1 违规:events sinks 内仍有 except ValueError 兜底;"
            "枚举解析错误必须上抛或显式记录\n" + "\n".join(matches[:5])
        )

    def test_no_channel_outcome_literal_construction_in_sinks(self) -> None:
        """PR-5: sink 内无 ``Channel(`` / ``Outcome(`` 字面枚举构造。"""
        sinks_root = _REPO_ROOT / "lca" / "plugins" / "events" / "sinks"
        if not sinks_root.exists():
            pytest.skip("lca/plugins/events/sinks/ not found")
        matches = _rg(r"Channel\(|Outcome\(", sinks_root)
        assert not matches, (
            "I-FW-REC-1 违规:sink 内仍有 Channel(/Outcome( 字面构造;"
            "channel/outcome 由 build_record() 透传\n" + "\n".join(matches[:5])
        )

    def test_spine_sinks_use_build_record_single_entry(self) -> None:
        """正向锁定:两个 spine sink 的 record 构造均走 build_record()。"""
        sinks_root = _REPO_ROOT / "lca" / "plugins" / "events" / "sinks"
        if not sinks_root.exists():
            pytest.skip("lca/plugins/events/sinks/ not found")
        matches = _rg(r"build_record\(", sinks_root)
        expected_sinks = (
            "spine_file_sink/sink.py",
            "spine_chain_sink/sink.py",
        )
        for sink_path in expected_sinks:
            assert any(sink_path in m for m in matches), (
                f"I-FW-REC-1 反向断言:{sink_path} 缺少 build_record( 调用;record 构造必须走单一入口"
            )
