"""状态机单 enum 不变量 —— ADR-0183 I-FW-SSOT-2(PR-11)。

守护:

- I-FW-SSOT-2: ``RunLifecycleStatus`` 是状态机唯一 enum;
  lca/ 内不允许再出现独立的 ``class RunStatus`` / ``class JournalRunStatus``
  enum 定义,遗留名字只能是别名。
- 别名对象同一性: 仍在窗口内的 ``RunStatus``(webserver session)与
  ``JournalRunStatus`` 均为 ``RunLifecycleStatus`` 同一对象;journal reducer 的同名
  别名已随其 delete-when 条件成立而删除。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _rg(pattern: str, root: Path) -> list[str]:
    """Run ripgrep with relative paths; return matching lines (empty = none)."""
    if not root.exists():
        return []
    if shutil.which("rg") is None:
        return []
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
    if result.returncode == 1:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


class TestIFwSsot2:
    """I-FW-SSOT-2: RunLifecycleStatus 是状态机唯一 enum。"""

    def test_no_parallel_status_enum_class(self) -> None:
        """lca/ 内 ``class RunStatus`` / ``class JournalRunStatus`` 定义 = 0。"""
        offenders = _rg(r"^\s*class\s+(RunStatus|JournalRunStatus)\b", _REPO_ROOT / "lca")
        assert not offenders, (
            "I-FW-SSOT-2 违规:仍存在平行状态机 enum 定义,"
            "应改为 RunLifecycleStatus 别名\n" + "\n".join(offenders[:5])
        )

    def test_legacy_names_are_aliases(self) -> None:
        """仍在迁移窗口内的遗留名字必须是别名,不能是平行 enum。

        journal reducer 的 ``RunStatus`` 别名已删除:它的两个条件
        (``RunStatus.`` 生产引用归零、全部改走 ``RunLifecycleStatus``)都成立后,
        连 journal / observability 两个 barrel 的再导出一起撤掉了。
        这里守住剩下的那一个 —— webserver session 的 ``RunStatus``,它仍被
        transport 测试使用,所以必须是同一对象而不是第二个 enum。
        """
        from lca.contracts.observability.registry.status import RunLifecycleStatus
        from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
            RunStatus,
        )

        assert RunStatus is RunLifecycleStatus
