"""route_legacy_patterns 单元测试 —— ADR-0074 历史迁移路由。

脚本聚合 4 个 audit_*.py 的 finding 并按路径前缀路由到 owner PR。
测试用 unittest.mock.patch on the audit scan_* callables, 这是脚本内部实际 import 的对象。
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from unittest import mock

_REPO = str(Path(__file__).resolve().parents[1])
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


@dataclass
class _FakeFinding:
    path: str
    line: int = 1
    col: int = 0
    kind: str = "x"
    message: str = "x"


class TestRouteLegacyPatterns:
    """Behavioural tests for scripts/route_legacy_patterns.py."""

    def test_resolve_owner_picks_longest_prefix(self) -> None:
        from scripts.route_legacy_patterns import _resolve_owner

        assert _resolve_owner("state_writers", "lca/layer1_cognitive/body/foo.py")[0] == "PR-7"
        assert _resolve_owner("state_writers", "lca/layer1_cognitive/memory/foo.py")[0] == "PR-3"
        assert _resolve_owner("state_writers", "lca/layer1_cognitive/brain/foo.py")[0] == "PR-4"
        assert _resolve_owner("state_writers", "totally/unknown/file.py")[0] == "PR-99"

    def test_collect_violations_with_patched_audits(self) -> None:
        """Patch audit scan_* callables in their actual modules."""
        from lca.harness.diagnostics import (
            audit_control_surface,
            audit_direct_commands,
            audit_hook_attach,
            audit_state_writers,
        )
        from scripts import route_legacy_patterns as route

        fake_root = _REPO
        fake_state = [
            _FakeFinding(path=f"{fake_root}/lca/layer1_cognitive/body/a.py"),
            _FakeFinding(path=f"{fake_root}/lca/layer1_cognitive/brain/b.py"),
            _FakeFinding(path=f"{fake_root}/lca/layer2_runtime/c.py"),
        ]
        fake_direct = [_FakeFinding(path=f"{fake_root}/lca/layer1_cognitive/body/d.py")]
        fake_control = {
            "perceive.context": [_FakeFinding(path=f"{fake_root}/lca/plugins/foo.py")],
        }
        fake_hook = [_FakeFinding(path=f"{fake_root}/lca/layer2_runtime/e.py")]

        with (
            mock.patch.object(
                audit_control_surface, "scan_control_surface", return_value=fake_control
            ),
            mock.patch.object(audit_state_writers, "scan_state_writers", return_value=fake_state),
            mock.patch.object(
                audit_direct_commands, "scan_direct_commands", return_value=fake_direct
            ),
            mock.patch.object(audit_hook_attach, "scan_hook_attach", return_value=fake_hook),
        ):
            violations = route.collect_violations()

        owners = sorted({v.owner_pr for v in violations})
        assert "PR-7" in owners
        assert "PR-4" in owners
        assert "PR-2" in owners
        assert len(violations) == 6

    def test_format_markdown_renders_table(self) -> None:
        from scripts.route_legacy_patterns import Violation, _format_markdown

        violations = [
            Violation(
                audit_kind="state_writers",
                v_constraint="V3",
                path="lca/layer1_cognitive/body/x.py",
                line=1,
                col=0,
                kind="direct_attr_assign",
                message="state.x",
                owner_pr="PR-7",
                rationale="Body envelope",
            )
        ]
        md = _format_markdown(violations)
        assert "| Owner PR |" in md
        assert "**PR-7**" in md
        assert "state_writers=1" in md

    def test_main_emits_markdown_when_empty(self) -> None:
        from scripts import route_legacy_patterns as route

        with mock.patch.object(route, "collect_violations", return_value=[]):
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                rc = route.main(["--md"])
            finally:
                sys.stdout = old
        assert rc == 0
        out = buf.getvalue()
        assert "无违规" in out


if __name__ == "__main__":
    unittest.main([__file__, "-v"])
