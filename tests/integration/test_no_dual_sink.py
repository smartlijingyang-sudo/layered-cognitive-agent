"""ADR-0169 PR-2 / S2 — L10 + L11 双写防御测试。

L10:同一 run 不存在两个 sink 写同一物理文件(spine 是唯一入口)。
L11:业务层不 emit LlmCallCompleted / LlmCallStarted(只看 ADR-0167 D11 业务层)。
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.observability.spine.sinks.routing_file_sink import (
    RunRoutingFileSink,
)


def test_routing_sink_per_run_creates_unique_sink(tmp_path: Path) -> None:
    """L10:RunRoutingFileSink 同 run 多次 _sink_for 返回同 sink 实例。"""
    sink = RunRoutingFileSink(
        boot_path=tmp_path / "boot-events.jsonl",
        runs_root=tmp_path / "runs",
    )
    a = sink._sink_for("run_x")
    b = sink._sink_for("run_x")
    assert a is b, "L10 violation:同一 run_id 应复用同一 FileSink"
    sink.close()


def test_routing_sink_different_runs_get_different_sinks(tmp_path: Path) -> None:
    """L10:不同 run_id 各自一个 FileSink 实例。"""
    sink = RunRoutingFileSink(
        boot_path=tmp_path / "boot-events.jsonl",
        runs_root=tmp_path / "runs",
    )
    a = sink._sink_for("run_1")
    b = sink._sink_for("run_2")
    assert a is not b
    # 子目录布局:每个 run 单独目录
    assert (tmp_path / "runs" / "run_1" / "events.jsonl").exists()
    assert (tmp_path / "runs" / "run_2" / "events.jsonl").exists()
    sink.close()


def test_routing_sink_spine_filename_uses_suffix(tmp_path: Path) -> None:
    """L10 + D9:`spine_filename=True` 时 per-run 文件名 = ``<run_id>.spine.jsonl``。"""
    sink = RunRoutingFileSink(
        boot_path=tmp_path / "boot-events.jsonl",
        runs_root=tmp_path / "runs",
        spine_filename=True,
    )
    s = sink._sink_for("run_y")
    assert s.path.name == "run_y.spine.jsonl"
    sink.close()


def test_business_layer_no_llm_call_completed() -> None:
    """L11:business 层(cognition/body/runtime/agent)不 emit LlmCallCompleted。

    只检测实际 emit 调用模式:``LlmCallCompleted(...)`` / ``LlmCallStarted(...)``
    作为构造调用或 ``record/emit/send`` 的实参;docstring 提及字符串不计。
    """
    import re

    repo_root = Path(__file__).resolve().parents[2]
    business_dirs = [
        repo_root / "lca" / "cognition",
        repo_root / "lca" / "body",
        repo_root / "lca" / "runtime",
        repo_root / "lca" / "agent",
    ]
    # 匹配 ``LlmCallCompleted(`` 或 ``LlmCallStarted(`` 作为实参/构造调用
    emit_pattern = re.compile(r"\bLlmCall(?:Completed|Started)\s*\(")
    bad_lines: list[str] = []
    for d in business_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for ln_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # docstring 行(以 " 开头的描述)允许提及
                if stripped.startswith('"') or stripped.startswith("'"):
                    continue
                if emit_pattern.search(line):
                    bad_lines.append(f"{py.relative_to(repo_root)}:{ln_no}: {line.strip()}")
    assert not bad_lines, (
        "L11 violation: business 层禁止 emit LlmCallCompleted/Started:\n"
        + "\n".join(f"  {b}" for b in bad_lines)
    )
