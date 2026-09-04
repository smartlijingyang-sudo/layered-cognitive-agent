"""Session 事件 SSOT 架构不变量 —— ADR-0186 §4（PR-3i 骨架）。

不变量（ADR-0186 §4）:

- I-SESSION-1: SessionProtocol / Session.append 是事件生产公开入口。
- I-SESSION-2: fold 模块纯函数，无文件系统 I/O / print / logging / datetime.now。
- I-SESSION-3: cognition / runtime / agent 禁直写 spine 落盘 API。
- I-SESSION-4: 持久化以 SessionObserver 形态存在；spine.jsonl 物理写方唯一。
- I-SESSION-5: deriver 走 fold；禁止新挂 EventSpine._subscribers 派生主路径。

PR-3i 只挂锁：未落地项 ``xfail(strict=False)``，reason 写明翻正 PR。
delete-when:N/A（长期回归锁；xfail 在对应 PR 收口时翻正）。
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FOLD_MODULE = _REPO_ROOT / "lca_kernel" / "events" / "fold.py"
_SESSION_MODULE = _REPO_ROOT / "lca_kernel" / "events" / "session.py"


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    """Run ripgrep; empty list = no matches."""
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


# ── I-SESSION-1 ─────────────────────────────────────────────────────────


class TestISession1:
    """I-SESSION-1: SessionProtocol 存在；append 为公开生产入口。"""

    @pytest.mark.xfail(
        strict=False,
        reason="ADR-0186 PR-3a: lca_kernel/events/session.py SessionProtocol 未落地",
        condition=not _SESSION_MODULE.exists(),
    )
    def test_i_session_1_session_protocol_exists(self) -> None:
        """SessionProtocol / SessionObserver / SessionEvent 可从 session 模块导入。"""
        assert _SESSION_MODULE.exists(), "lca_kernel/events/session.py missing"
        from lca_kernel.events.session import (
            SessionEvent,
            SessionObserver,
            SessionProtocol,
        )

        assert SessionProtocol is not None
        assert SessionObserver is not None
        assert SessionEvent is not None


# ── I-SESSION-2 ─────────────────────────────────────────────────────────


class TestISession2:
    """I-SESSION-2: fold 模块无 I/O / 副作用。"""

    def test_i_session_2_fold_no_io(self) -> None:
        """fold.py 不得 open / pathlib.Path / read|write / print / logging / datetime.now。"""
        if not _FOLD_MODULE.exists():
            pytest.skip("lca_kernel/events/fold.py not found")
        source = _FOLD_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert "open(" not in source, "I-SESSION-2: fold.py must not call open()"

        for pattern in (
            ".read(",
            ".read_text(",
            ".read_bytes(",
            ".write(",
            ".write_text(",
            ".write_bytes(",
        ):
            assert pattern not in source, f"I-SESSION-2: fold.py must not contain {pattern!r}"

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
                names = [alias.name for alias in node.names]
                assert "Path" not in names, "I-SESSION-2: fold.py must not import pathlib.Path"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "pathlib", "I-SESSION-2: fold.py must not import pathlib"
                    assert alias.name != "logging", "I-SESSION-2: fold.py must not import logging"
            if isinstance(node, ast.ImportFrom) and node.module == "logging":
                pytest.fail("I-SESSION-2: fold.py must not import from logging")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "print", "I-SESSION-2: fold.py must not call print()"
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"datetime", "dt"}
                and node.func.attr == "now"
            ):
                pytest.fail("I-SESSION-2: fold.py must not call datetime.now()")


# ── I-SESSION-3 ─────────────────────────────────────────────────────────


class TestISession3:
    """I-SESSION-3: 业务层禁直写 spine 落盘 API。"""

    def test_i_session_3_no_business_direct_spine_write(self) -> None:
        """cognition / runtime / agent 不得 event_spine.append / spine_port_append。

        承接 ADR-0183 I-FW-BUS-1 业务侧；Session.append 收口后本断言保持。
        """
        matches: list[str] = []
        for sub in ("cognition", "runtime", "agent"):
            root = _REPO_ROOT / "lca" / sub
            if not root.exists():
                continue
            matches.extend(_rg(r"event_spine\.append\(", root))
            matches.extend(_rg(r"spine_port_append\(", root))
        assert not matches, "I-SESSION-3 违规:业务层仍直写 spine\n" + "\n".join(matches[:8])


# ── I-SESSION-4 ─────────────────────────────────────────────────────────


class TestISession4:
    """I-SESSION-4: 持久化是 SessionObserver；禁止平行 PersistenceWorker 主路径。"""

    @pytest.mark.xfail(
        strict=False,
        reason="ADR-0186 PR-3e/3f: PersistenceObserver + JsonlSessionPersistence 未收口",
    )
    def test_i_session_4_persistence_is_observer(self) -> None:
        """生产路径应暴露 PersistenceObserver / JsonlSessionPersistence，而非 PersistenceWorker 主写。"""
        persistence = _REPO_ROOT / "lca_kernel" / "events" / "persistence.py"
        assert persistence.exists(), "persistence.py missing"

        text = persistence.read_text(encoding="utf-8")
        has_observer = "PersistenceObserver" in text or "class PersistenceObserver" in text
        worker_hits = _rg(r"\bPersistenceWorker\b", _REPO_ROOT / "lca")
        worker_hits += _rg(r"\bPersistenceWorker\b", _REPO_ROOT / "lca_kernel" / "events")
        # 翻正条件:Observer 类型存在，且 PersistenceWorker 生产引用清零（测试/COMPAT 除外）
        assert has_observer, "PersistenceObserver type not defined"
        production = [
            line
            for line in worker_hits
            if "/tests/" not in line.split(":", 1)[0]
            and "COMPAT" not in line
            and "delete-when" not in line
        ]
        assert not production, "I-SESSION-4: PersistenceWorker 仍在生产路径\n" + "\n".join(
            production[:8]
        )


# ── I-SESSION-5 ─────────────────────────────────────────────────────────


class TestISession5:
    """I-SESSION-5: deriver 走 fold，不新挂 EventSpine._subscribers 派生主路径。"""

    @pytest.mark.xfail(
        strict=False,
        reason="ADR-0186 PR-3g: deriver fold 切流未完成；EventSpine.subscribe 派生仍在",
    )
    def test_i_session_5_deriver_uses_fold(self) -> None:
        """observability deriver / spine derivers 不得依赖 EventSpine.subscribe 作为派生主路径。"""
        search_roots = [
            _REPO_ROOT / "lca" / "infrastructure" / "observability" / "spine" / "derivers",
            _REPO_ROOT / "lca" / "plugins" / "observability",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            matches.extend(_rg(r"\.subscribe\(", root))
            matches.extend(_rg(r"_subscribers", root))
        assert not matches, "I-SESSION-5 违规:deriver 仍挂 in-memory subscribe\n" + "\n".join(
            matches[:8]
        )
