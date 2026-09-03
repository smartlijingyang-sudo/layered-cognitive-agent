"""Observation SSOT 注册表(PR-1)单测。

覆盖根 note ``docs/notes/proposed/seam/2026-09-03-observation-ssot-registry.md``
acceptance criteria #1-#3。
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pytest

from lca.contracts.observability.run_locator import RunLocator
from lca.contracts.observability.ssot import (
    EXCEPTIONS_FILE_TEMPLATE,
    FAILURE_RUN_STATUSES,
    LEGACY_EVENTS_NAME,
    SUCCESS_RUN_STATUSES,
    TERMINAL_EXECUTION_OUTCOMES,
    TERMINAL_RUN_STATUSES,
    ExecutionOutcome,
    RunLifecycleStatus,
    exceptions_filename_for_run,
    find_spine_file,
    is_failure_run_status,
    is_success_run_status,
    is_terminal_outcome,
    is_terminal_run_status,
    provider_schema,
    spine_filename_for_run,
    to_jsonable,
)
from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)

# ─── 段 1:spine file SSOT ────────────────────────────────────────────────


class TestSpineFile:
    """acceptance #2:find_spine_file 4 case 覆盖。"""

    def test_spine_filename_for_run(self) -> None:
        assert spine_filename_for_run("run_abc") == "run_abc.spine.jsonl"

    def test_exceptions_filename_for_run(self) -> None:
        assert exceptions_filename_for_run("run_abc") == "run_abc.exceptions.jsonl"
        assert EXCEPTIONS_FILE_TEMPLATE == "{run_id}.exceptions.jsonl"

    def test_find_spine_file_spine_exists(self, tmp_path: Path) -> None:
        run_id = "run_aaa"
        spine = tmp_path / spine_filename_for_run(run_id)
        spine.write_text("event-1\n")
        result = find_spine_file(tmp_path, run_id)
        assert result == spine
        assert result.exists()

    def test_find_spine_file_legacy_fallback(self, tmp_path: Path) -> None:
        run_id = "run_bbb"
        legacy = tmp_path / LEGACY_EVENTS_NAME
        legacy.write_text("legacy-event\n")
        result = find_spine_file(tmp_path, run_id)
        assert result == legacy

    def test_find_spine_file_both_exist_prefers_spine(self, tmp_path: Path) -> None:
        run_id = "run_ccc"
        spine = tmp_path / spine_filename_for_run(run_id)
        legacy = tmp_path / LEGACY_EVENTS_NAME
        spine.write_text("new-event\n")
        legacy.write_text("old-event\n")
        result = find_spine_file(tmp_path, run_id)
        assert result == spine

    def test_find_spine_file_neither_returns_spine_path(self, tmp_path: Path) -> None:
        run_id = "run_ddd"
        result = find_spine_file(tmp_path, run_id)
        # 不存在 → 返回 spine 命名路径(由 caller 决定是否 raise)
        assert result == tmp_path / spine_filename_for_run(run_id)
        assert not result.exists()

    def test_filesystem_run_locator_events_path_delegates(self, tmp_path: Path) -> None:
        """RunLocator.events_path 必须委托 find_spine_file(等价行为)。"""
        locator = FilesystemRunLocator(tmp_path)
        run_id = "run_eee"
        spine = locator.events_path(run_id)
        assert spine.name == spine_filename_for_run(run_id)
        assert spine.parent == locator.run_dir(run_id)

    def test_filesystem_run_locator_new_methods(self, tmp_path: Path) -> None:
        """PR-1 新增 3 个方法:kernel_log_path / exceptions_path / profile_snapshot_path。"""
        locator = FilesystemRunLocator(tmp_path)
        run_id = "run_fff"
        run_dir = locator.run_dir(run_id)
        assert locator.kernel_log_path(run_id) == run_dir / "kernel.log"
        assert locator.exceptions_path(run_id) == run_dir / "run_fff.exceptions.jsonl"
        assert locator.profile_snapshot_path(run_id) == run_dir / "profile_snapshot.json"

    def test_run_locator_protocol_compatible(self, tmp_path: Path) -> None:
        """RunLocatorExtended 新方法必须满足 RunLocator 结构。"""
        locator = FilesystemRunLocator(tmp_path)
        # 现有 RunLocator 检查(向后兼容)
        assert isinstance(locator, RunLocator)


# ─── 段 2:Run terminal status SSOT ──────────────────────────────────────


class TestRunLifecycleStatus:
    """acceptance #3:is_terminal / is_success / is_failure 全集覆盖。"""

    def test_terminal_set_members(self) -> None:
        assert (
            frozenset(
                {
                    RunLifecycleStatus.COMPLETED,
                    RunLifecycleStatus.FAILED,
                    RunLifecycleStatus.CANCELED,
                }
            )
            == TERMINAL_RUN_STATUSES
        )

    def test_success_set_members(self) -> None:
        assert frozenset({RunLifecycleStatus.COMPLETED}) == SUCCESS_RUN_STATUSES

    def test_failure_set_members(self) -> None:
        assert (
            frozenset({RunLifecycleStatus.FAILED, RunLifecycleStatus.CANCELED})
            == FAILURE_RUN_STATUSES
        )

    @pytest.mark.parametrize(
        ("status", "expected_terminal", "expected_success", "expected_failure"),
        [
            (RunLifecycleStatus.PENDING, False, False, False),
            (RunLifecycleStatus.RUNNING, False, False, False),
            (RunLifecycleStatus.WAITING_INPUT, False, False, False),
            (RunLifecycleStatus.COMPLETED, True, True, False),
            (RunLifecycleStatus.FAILED, True, False, True),
            (RunLifecycleStatus.CANCELED, True, False, True),
        ],
    )
    def test_predicates_all_values(
        self,
        status: RunLifecycleStatus,
        expected_terminal: bool,
        expected_success: bool,
        expected_failure: bool,
    ) -> None:
        assert is_terminal_run_status(status) is expected_terminal
        assert is_success_run_status(status) is expected_success
        assert is_failure_run_status(status) is expected_failure

    @pytest.mark.parametrize(
        ("raw_status", "expected"),
        [
            ("completed", True),
            ("failed", True),
            ("canceled", True),
            ("running", False),
            ("pending", False),
            ("waiting_input", False),
        ],
    )
    def test_predicates_accept_strings(self, raw_status: str, expected: bool) -> None:
        assert is_terminal_run_status(raw_status) is expected
        assert is_success_run_status(raw_status) is (raw_status == "completed")
        assert is_failure_run_status(raw_status) is (raw_status in {"failed", "canceled"})

    def test_predicate_rejects_unknown_value(self) -> None:
        with pytest.raises(ValueError):
            is_terminal_run_status("garbage")


# ─── 段 3:ExecutionOutcome enum ─────────────────────────────────────────


class TestExecutionOutcome:
    """acceptance #4:ExecutionOutcome 6 值 + is_terminal_outcome。"""

    def test_terminal_outcomes(self) -> None:
        assert (
            frozenset(
                {
                    ExecutionOutcome.COMPLETED,
                    ExecutionOutcome.PAUSED,
                    ExecutionOutcome.FAILED,
                    ExecutionOutcome.EFFECT_UNCERTAIN,
                    ExecutionOutcome.STOPPED,
                }
            )
            == TERMINAL_EXECUTION_OUTCOMES
        )

    @pytest.mark.parametrize(
        ("outcome", "expected"),
        [
            (ExecutionOutcome.IN_PROGRESS, False),
            (ExecutionOutcome.COMPLETED, True),
            (ExecutionOutcome.PAUSED, True),
            (ExecutionOutcome.FAILED, True),
            (ExecutionOutcome.EFFECT_UNCERTAIN, True),
            (ExecutionOutcome.STOPPED, True),
        ],
    )
    def test_is_terminal_outcome(self, outcome: ExecutionOutcome, expected: bool) -> None:
        assert is_terminal_outcome(outcome) is expected

    def test_is_terminal_outcome_accepts_strings(self) -> None:
        assert is_terminal_outcome("completed") is True
        assert is_terminal_outcome("in_progress") is False


# ─── 段 4:to_jsonable 单一来源 ───────────────────────────────────────────


class TestToJsonable:
    """to_jsonable 单一 SSOT,合并 _capture_io + journal/step/projector 两份。"""

    def test_primitives_passthrough(self) -> None:
        assert to_jsonable(None) is None
        assert to_jsonable("hi") == "hi"
        assert to_jsonable(42) == 42
        assert to_jsonable(True) is True
        assert to_jsonable(3.14) == 3.14

    def test_dict_recursion(self) -> None:
        assert to_jsonable({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}

    def test_list_recursion(self) -> None:
        assert to_jsonable([1, "two", {"three": 3}]) == [1, "two", {"three": 3}]

    def test_dataclass_asdict(self) -> None:
        import dataclasses

        @dataclasses.dataclass
        class Point:
            x: int
            y: int

        result = to_jsonable(Point(3, 4))
        assert result == {"x": 3, "y": 4}

    def test_repr_fallback_for_arbitrary_object(self) -> None:
        class NoDict:
            __slots__ = ("a",)

            def __init__(self) -> None:
                self.a = 1

        result = to_jsonable(NoDict())
        # __slots__ 类可能落到 repr 兜底或失败 → 返回字符串
        assert isinstance(result, (str, dict))

    def test_provider_schema_priority(self) -> None:
        """provider_schema 比 dataclass / __dict__ 优先(to_jsonable 优先级 0)。"""

        class Tool:
            def __init__(self) -> None:
                self.name = "ignored"

            def __provider_schema__(self) -> dict:
                return {"type": "function", "name": "special"}

        result = to_jsonable(Tool())
        assert result == {"type": "function", "name": "special"}

    def test_provider_schema_returns_dict_only(self) -> None:
        class Tool:
            def __provider_schema__(self) -> str:
                return "not a dict"

        result = to_jsonable(Tool())
        # provider_schema 返回非 Mapping → 降级到 __dict__ / dataclass
        assert result != "not a dict"


class TestProviderSchema:
    """provider_schema 工具方法单测。"""

    def test_no_methods_returns_none(self) -> None:
        assert provider_schema(object()) is None

    def test_dict_method_wins(self) -> None:
        class T:
            def __provider_schema__(self) -> dict:
                return {"k": "v"}

        assert provider_schema(T()) == {"k": "v"}

    def test_openai_schema_method(self) -> None:
        class T:
            def openai_schema(self) -> dict:
                return {"k": "openai"}

        assert provider_schema(T()) == {"k": "openai"}

    def test_non_dict_return_ignored(self) -> None:
        class T:
            def __provider_schema__(self) -> str:
                return "garbage"

        assert provider_schema(T()) is None


# ─── JSON round-trip 集成测试 ────────────────────────────────────────────


class TestJsonRoundTrip:
    """to_jsonable 输出必须可 json.dumps 不抛 TypeError。"""

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "str",
            42,
            3.14,
            True,
            [],
            {},
            {"k": [1, 2, 3]},
            [None, "a", 1, {"nested": "b"}],
        ],
    )
    def test_json_dumps_no_typeerror(self, value: object) -> None:
        jsonable = to_jsonable(value)
        # 不抛 TypeError 即通过
        _json.dumps(jsonable)
