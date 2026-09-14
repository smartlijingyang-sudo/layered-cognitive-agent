"""Regression: ``_extract_stdout_chars_total`` mirrors ``_extract_stdout_head`` key order.

Fix target: ``step.tool_result.record.stdout_chars_total`` was 0 even when the
tool produced large stdout. The cause was ``safe_executor.execute()`` calling
``record_step_tool_result`` without passing ``stdout_chars_total`` (default 0),
so the downstream critic / LLM context could not distinguish "empty result" from
"truncated result, real size unknown". The fix adds a pure helper that reads
the same key order as ``_extract_stdout_head`` and returns the real ``len(value)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.cognition.body.executor.safe_executor import (
    _extract_stdout_chars_total,
)


@dataclass
class _Obs:
    success: bool = True
    payload: dict[str, Any] | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def test_returns_zero_when_observation_is_none() -> None:
    assert _extract_stdout_chars_total(None) == 0


def test_returns_zero_when_payload_is_not_dict() -> None:
    obs = _Obs(payload="not a dict")  # type: ignore[arg-type]
    assert _extract_stdout_chars_total(obs) == 0


def test_returns_zero_when_no_known_key_present() -> None:
    obs = _Obs(payload={"stderr": "boom", "exit_code": 1})
    assert _extract_stdout_chars_total(obs) == 0


def test_returns_full_length_from_output_key() -> None:
    long_text = "x" * 5000
    obs = _Obs(payload={"output": long_text})
    assert _extract_stdout_chars_total(obs) == 5000


def test_falls_back_to_stdout_key_when_output_missing() -> None:
    obs = _Obs(payload={"stdout": "abcde"})
    assert _extract_stdout_chars_total(obs) == 5


def test_falls_back_to_content_key_when_output_and_stdout_missing() -> None:
    obs = _Obs(payload={"content": "hello world"})
    assert _extract_stdout_chars_total(obs) == 11


def test_prefers_output_over_stdout_and_content() -> None:
    obs = _Obs(
        payload={
            "output": "real-output",
            "stdout": "should-be-ignored",
            "content": "should-be-ignored-too",
        }
    )
    assert _extract_stdout_chars_total(obs) == len("real-output")


def test_non_string_value_does_not_count() -> None:
    obs = _Obs(payload={"output": 12345})
    assert _extract_stdout_chars_total(obs) == 0


def test_regression_ls_run_payload_pattern() -> None:
    """Mirror the shape observed in run_3696ef7c83b6: stdout is a multi-line
    string under ``output``. Helper must return > 0 so the spine fact carries
    real length downstream.
    """
    payload = {
        "output": "total 1392\ndrwxrwxr-x  34 lichao lichao   4096 Sep 14 11:15 .\n",
        "exit_code": 0,
    }
    obs = _Obs(success=True, payload=payload)
    assert _extract_stdout_chars_total(obs) > 0
