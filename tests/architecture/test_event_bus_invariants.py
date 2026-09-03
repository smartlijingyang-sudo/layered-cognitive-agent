"""EventBus 架构不变量 —— ADR-0183 §4。

不变量（ADR-0183 §4):
- I-FW-BUS-1: producer 唯一入口 = EventBus.publish；reducer / cursor / runtime_loop
  禁直写 spine / 直调 sink。
- I-FW-BUS-2: consumer 唯一入口 = EventBus.subscribe(*, failure=...)；不允许在
  EventBus 框架外调 .subscribe( / .register_sink( (manifest.py 内部走
  EventMechanism 除外)。
- I-FW-BUS-4: 业务不订阅 event.bus.dispatch.*。
- I-FW-SSOT-1: <run_id>.spine.jsonl 唯一 SSOT；events.jsonl legacy reader 必须
  迁到 SpineReader；SpineSink 唯一写。

守护范围（PR-1+PR-2+PR-4 已落地的部分）:
- I-FW-BUS-1 sink 直调部分: spine_chain_sink. / spine_file_sink.write 收口 = 0
- I-FW-BUS-4: profile/bundle consumer_rules 不订阅 event.bus.dispatch.*
- I-FW-SSOT-1 writer: open(events.jsonl, "w") 收口 = 0
- I-FW-SSOT-1 reader: 旧 events.jsonl legacy reader 路径 = 0(允许 lca_kernel/events/ +
  archive/ + 文档/注释引用)
- I-FW-SSOT-1 sink 唯一: lca_kernel/events/sinks/ 唯一 .write( = spine_sink

待后续 PR 收口(本测试在 docstring 内注明债务范围,不在断言里硬性 fail):
- PR-8 reducer: 16 处 coord.emit_phase 兼容路径删除
- PR-9 cursor: loop_cursor 直写 spine 收口
- PR-10 runtime_loop: emit_exception_caught 4 键裸 dict → EnvelopeEmitter
- PR-12 trace_id + 自观察: 业务不订阅 event.bus.dispatch.* 由 Pipeline 装载保证
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

# 仓库根 = tests/architecture/ 的父父目录
_REPO_ROOT = Path(__file__).resolve().parents[2]

# 测试文件自身路径(白名单:测试自身不在守范围内)
_THIS_TEST_FILE = Path(__file__).resolve()


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
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".yaml", ".yml"}:
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


def _is_excluded(line: str, exclude_substrings: tuple[str, ...]) -> bool:
    """A match line is excluded if its file path contains any exclude substring."""
    path_part = line.split(":", 1)[0]
    return any(sub in path_part for sub in exclude_substrings)


# ── I-FW-BUS-1 ──────────────────────────────────────────────────────────


class TestIFwBus1:
    """I-FW-BUS-1: producer 唯一入口 = EventBus.publish。

    当前守护范围:
    - sink 直调部分(spine_chain_sink. / spine_file_sink.write): PR-1+2+4 已收口
    - cursor 直写部分(loop_cursor._spine.append): 待 PR-9 收口,本测试标 xfail
      说明债务范围
    """

    def test_i_fw_bus_1_no_direct_spine_append_in_runtime(self) -> None:
        """PR-1+2+4:reducer/cursor/runtime_loop 不允许直写 spine。

        债务：lca/infrastructure/observability/loop_cursor/ 仍直写 _spine
        (4 处),等 PR-9 收口。本断言目前以「非 loop_cursor 路径 = 0」为
        收口基线,loop_cursor 路径用 xfail 标记已知债。
        """
        runtime_root = _REPO_ROOT / "lca" / "runtime"
        if not runtime_root.exists():
            pytest.skip("lca/runtime/ not found")
        # cursor / cognition / runtime 三个目录,排除 loop_cursor(PR-9 收口债)
        search_roots = [
            _REPO_ROOT / "lca" / "runtime",
            _REPO_ROOT / "lca" / "cognition",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"_spine\.append\(|event_spine\.append\(", root):
                matches.append(line)
        # PR-9 debt:lca/infrastructure/observability/loop_cursor/ 仍直写
        # 4 处,本测试不守护该路径,只守护 lca/runtime/ + lca/cognition/
        assert not matches, "I-FW-BUS-1 违规:reducer/cognition 仍直写 spine.append\n" + "\n".join(
            matches[:5]
        )

    def test_i_fw_bus_1_loop_cursor_debt_xfail(self) -> None:
        """债务标记:PR-9 待 lca/infrastructure/observability/loop_cursor/
        直写收口后,本 xfail 改回 strict 断言。

        当前 4 处:`loop_cursor/std.py:2、loop_cursor/bind.py:1、
        loop_cursor/in_memory.py:2`。等待 PR-9 (cursor 收口)。
        """
        loop_cursor = _REPO_ROOT / "lca" / "infrastructure" / "observability" / "loop_cursor"
        if not loop_cursor.exists():
            pytest.skip("loop_cursor path not found")
        matches = _rg(r"_spine\.append\(|event_spine\.append\(", loop_cursor)
        # 仅记录债务范围,不 fail
        if matches:
            pytest.xfail(
                f"PR-9 收口债:loop_cursor/ 仍 {len(matches)} 处直写 spine.append;"
                f"等 PR-9 收口后改 strict 断言"
            )

    def test_i_fw_bus_1_no_direct_sink_call_in_runtime(self) -> None:
        """PR-1+2+4:生产路径不直调 sink(spine_chain_sink./spine_file_sink.write)。"""
        search_roots = [
            _REPO_ROOT / "lca" / "runtime",
            _REPO_ROOT / "lca" / "cognition",
            _REPO_ROOT / "lca" / "agent",
            _REPO_ROOT / "lca" / "application",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"spine_chain_sink\.(?!Sink\b)|spine_file_sink\.write\(", root):
                matches.append(line)
        assert not matches, "I-FW-BUS-1 违规:生产路径直调 sink\n" + "\n".join(matches[:5])


# ── I-FW-BUS-2 ──────────────────────────────────────────────────────────


class TestIFwBus2:
    """I-FW-BUS-2: consumer 唯一入口 = EventBus.subscribe(*, failure=...)。

    当前守护范围:除白名单外,生产路径不应有 .subscribe( / .register_sink(
    调用。白名单:EventMechanism 框架内(lca_kernel/events/)、
    manifest.py 内部走 EventMechanism、journal/spine/session 的非事件框架
    subscribe(tail.subscribe 等)已知债(待 PR-9 收口)。
    """

    # 框架内 + manifest.py 内部 + 测试自身的合法位置
    _ALLOW_PATH_SUBSTRINGS: tuple[str, ...] = (
        "lca_kernel/events/",  # EventMechanism / EventBus 框架本体
        "lca/plugins/events/",  # 业务方 plugin manifest 内部走 EventMechanism
        "archive/",  # 归档
        str(_THIS_TEST_FILE.name),  # 本测试文件
    )

    # 已知债位置:loop_cursor/event_spine、live_tail、session.tail 等
    # 这些 .subscribe( 是 spine/live_tail/session 的非事件框架订阅方法,
    # 不是 EventMechanism.subscribe。等 PR-9 收口后从白名单移除。
    _KNOWN_DEBT_PATH_SUBSTRINGS: tuple[str, ...] = (
        "lca/infrastructure/observability/loop_cursor/",  # event_spine.subscribe
        "lca/infrastructure/observability/journal/stream/live_tail.py",  # tail.subscribe
        "lca/infrastructure/observability/spine/derivers/live_tail.py",  # self._tail.subscribe
        "lca/harness/agent/activation.py",  # store.subscribe (projection 订阅)
        "lca/plugins/transport/webserver/handlers/runs/terminal/registry_queries.py",  # session.tail.subscribe
        "lca/plugins/transport/webserver/handlers/runs/session/builder.py",  # event_spine.subscribe
    )

    def test_i_fw_bus_2_subscribe_outside_framework_blocked(self) -> None:
        """I-FW-BUS-2:除白名单外,生产路径不应有 .subscribe( / .register_sink(。"""
        search_roots = [
            _REPO_ROOT / "lca",
            _REPO_ROOT / "lca_kernel",
        ]
        all_matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"\.subscribe\(|\.register_sink\(", root):
                # 应用两层白名单
                if _is_excluded(line, self._ALLOW_PATH_SUBSTRINGS):
                    continue
                if _is_excluded(line, self._KNOWN_DEBT_PATH_SUBSTRINGS):
                    continue
                all_matches.append(line)
        # 测试文件自身不在守范围
        filtered = [m for m in all_matches if not _is_excluded(m, (str(_THIS_TEST_FILE.name),))]
        # tests/ 目录下的 .subscribe( 是测试 fixture 调用机制,不算违规
        # 但仍要排除 tests/audit_hook_attach.py 内的 fixture 字符串
        # (它在 _write_py 内写磁盘,会被 rg 抓到)
        # 已通过 _KNOWN_DEBT 不覆盖 tests/ 目录;这里单独再排除 tests/
        filtered = [
            m for m in filtered if not m.startswith("tests/") and "tests/" not in m.split(":", 1)[0]
        ]
        assert not filtered, (
            "I-FW-BUS-2 违规:框架外 .subscribe( / .register_sink( 调用\n" + "\n".join(filtered[:5])
        )


# ── I-FW-BUS-4 ──────────────────────────────────────────────────────────


class TestIFwBus4:
    """I-FW-BUS-4: 业务不订阅 event.bus.dispatch.*。"""

    def test_i_fw_bus_4_no_business_subscribe_dispatch_event(self) -> None:
        """Pipeline consumer_rules / subscribers / pipeline 段不订阅 event.bus.dispatch.*。"""
        # profile/bundle yaml 路径
        search_roots = [
            _REPO_ROOT / "lca" / "profiles",
            _REPO_ROOT / "lca" / "bundles",
            _REPO_ROOT / "profiles",
            _REPO_ROOT / "bundles",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            # 只看 yaml 文件
            if _have_ripgrep():
                result = subprocess.run(  # noqa: S603  # path is a constant binary
                    [  # noqa: S607  # rg binary located via shutil.which()
                        "rg",
                        "--line-number",
                        "--no-heading",
                        "--glob",
                        "*.yaml",
                        "--glob",
                        "*.yml",
                        r"event\.bus\.dispatch\.",
                        str(root),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode not in (0, 1):
                    continue
                for line in result.stdout.splitlines():
                    matches.append(line)
            else:
                for path in root.rglob("*.yaml"):
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    for lineno, line in enumerate(text.splitlines(), start=1):
                        if "event.bus.dispatch." in line:
                            rel = path.relative_to(_REPO_ROOT)
                            matches.append(f"{rel}:{lineno}:{line}")
        assert not matches, "I-FW-BUS-4 违规:业务订阅 event.bus.dispatch.*\n" + "\n".join(
            matches[:5]
        )


# ── I-FW-SSOT-1 ─────────────────────────────────────────────────────────


class TestIFwSsot1:
    """I-FW-SSOT-1: <run_id>.spine.jsonl 唯一 SSOT。"""

    # 文档/注释/兼容引用白名单
    _DOC_ALLOW_SUBSTRINGS: tuple[str, ...] = (
        "lca_kernel/events/",  # SSOT reader / sinks 自身
        "archive/",  # 归档
        str(_THIS_TEST_FILE.name),  # 本测试文件
        "tests/fixtures/",  # 测试 fixture
    )

    def test_i_fw_ssot_1_no_legacy_events_jsonl_writer(self) -> None:
        """events.jsonl legacy writer = 0(open(events.jsonl, "w") 模式)。"""
        search_roots = [
            _REPO_ROOT / "lca",
            _REPO_ROOT / "lca_kernel",
        ]
        matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            # 匹配 open(...)..., "w" 形式包含 events.jsonl
            for line in _rg(r'open\([^)]*events\.jsonl[^)]*["\']\s*,\s*["\']w["\']', root):
                # 应用白名单
                if _is_excluded(line, self._DOC_ALLOW_SUBSTRINGS):
                    continue
                matches.append(line)
        assert not matches, "I-FW-SSOT-1 违规:events.jsonl writer 仍在生产路径\n" + "\n".join(
            matches[:5]
        )

    def test_i_fw_ssot_1_no_legacy_events_jsonl_reader_in_production(self) -> None:
        """I-FW-SSOT-1:events.jsonl legacy reader 必须迁到 SpineReader。

        当前债务:生产路径 ~20 处硬编码 events.jsonl(在 lca/contracts/、
        lca/plugins/、lca/runtime/ 等)。本测试标 xfail 说明债务范围,
        待 PR-4 后续 sweep 收口。
        """
        search_roots = [
            _REPO_ROOT / "lca",
            _REPO_ROOT / "lca_kernel",
            _REPO_ROOT / "profiles",
            _REPO_ROOT / "bundles",
        ]
        all_matches: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for line in _rg(r"events\.jsonl", root):
                if _is_excluded(line, self._DOC_ALLOW_SUBSTRINGS):
                    continue
                all_matches.append(line)
        if all_matches:
            pytest.xfail(
                f"PR-4 收口债:events.jsonl legacy reader 仍 {len(all_matches)} 处"
                f"(非 SSOT 路径);等 follow-up sweep 收口后改 strict"
            )

    def test_i_fw_ssot_1_spine_jsonl_writer_is_single(self) -> None:
        """lca_kernel/events/sinks/ 唯一写 .write( = spine_sink。"""
        sinks_dir = _REPO_ROOT / "lca_kernel" / "events" / "sinks"
        if not sinks_dir.exists():
            pytest.skip("lca_kernel/events/sinks/ not found")
        write_matches = _rg(r"\.write\(", sinks_dir)
        # 必须全部在 spine_sink.py(框架内唯一 SSOT 写者)
        offenders = [m for m in write_matches if "spine_sink.py" not in m]
        assert not offenders, (
            "I-FW-SSOT-1 违规:lca_kernel/events/sinks/ 内 spine_sink 之外"
            "还有 .write( 调用\n" + "\n".join(offenders[:5])
        )
        # 且 spine_sink.py 内必须有至少一处 .write(
        assert any("spine_sink.py" in m for m in write_matches), (
            "I-FW-SSOT-1 反向断言:lca_kernel/events/sinks/spine_sink.py "
            "缺少 .write( 调用(SpineSink.append 落盘实现异常)"
        )
