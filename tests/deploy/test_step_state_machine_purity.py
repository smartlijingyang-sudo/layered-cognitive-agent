"""INV-05: Step State Machine Purity & Determinism Tests.

Validates that `deriveStepState` in `AssistantStatusDrawer.tsx` is a pure function:
1. Covers all 5 icon states:
   - 'started': '●' (#aaaaaa)
   - 'running' / 'pending': '◐' (#60b1ff)
   - 'error' (exitCode != 0): '✕' (#f4416c)
   - 'file_op' (write/edit/create/patch): '📄' (#cccccc)
   - 'completed' (successful execution or delivery): '✔' (#c4f042)
2. Is strictly pure & deterministic: f(toolName, phase, exitCode, isOutput) -> state.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


def _get_drawer_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantStatusDrawer.tsx"
    )


def _run_derive_step_state_in_node(
    tool_name: str | None = None,
    lifecycle_phase: str | None = None,
    exit_code: int | None = None,
    is_output: bool = False,
) -> dict[str, str]:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    assert "export function deriveStepState" in content or "function deriveStepState" in content, (
        "AssistantStatusDrawer.tsx must export deriveStepState function"
    )

    match = re.search(
        r"(export\s+interface\s+StepStateVisual[\s\S]*?export\s+function\s+deriveStepState[\s\S]*?\n\})",
        content,
    )
    if not match:
        raise ValueError("Could not extract deriveStepState from TSX")

    fn_code = (
        match.group(1)
        .replace("export interface", "interface")
        .replace("export function", "function")
    )

    script = f"""
{fn_code}

const res = deriveStepState(
    {json.dumps(tool_name)},
    {json.dumps(lifecycle_phase)},
    {json.dumps(exit_code)},
    {json.dumps(is_output)}
);
process.stdout.write(JSON.stringify(res));
"""
    node_bin = shutil.which("node") or "node"
    proc = subprocess.run(  # noqa: S603
        [node_bin, "--experimental-strip-types", "-e", script],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Node execution failed (code {proc.returncode}): {proc.stderr}\nScript: {script}"
        )
    return json.loads(proc.stdout)


def test_derive_step_state_exists_in_drawer_tsx() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")
    assert "deriveStepState" in content, (
        "deriveStepState must be defined in AssistantStatusDrawer.tsx"
    )


def test_derive_step_state_started_phase() -> None:
    res = _run_derive_step_state_in_node(lifecycle_phase="started")
    assert res["iconType"] == "started"
    assert res["iconSymbol"] == "●"
    assert res["color"] == "#aaaaaa"


def test_derive_step_state_running_phase() -> None:
    res = _run_derive_step_state_in_node(tool_name="bash", lifecycle_phase="running")
    assert res["iconType"] == "running"
    assert res["iconSymbol"] == "◐"
    assert res["color"] == "#60b1ff"

    res_pending = _run_derive_step_state_in_node(lifecycle_phase="pending")
    assert res_pending["iconType"] == "running"
    assert res_pending["iconSymbol"] == "◐"


def test_derive_step_state_error_on_nonzero_exit_code() -> None:
    for code in (1, 2, 127, 255):
        res = _run_derive_step_state_in_node(tool_name="bash", exit_code=code)
        assert res["iconType"] == "error", f"Failed for exit_code={code}"
        assert res["iconSymbol"] == "✕"
        assert res["color"] == "#f4416c"


def test_derive_step_state_file_operations() -> None:
    for tool in (
        "writeFile",
        "editFile",
        "create_assistant_skill",
        "patch_config",
        "write_to_file",
    ):
        res = _run_derive_step_state_in_node(tool_name=tool, exit_code=0)
        assert res["iconType"] == "file_op", f"Expected file_op for {tool}, got {res}"
        assert res["iconSymbol"] == "📄"
        assert res["color"] == "#cccccc"


def test_derive_step_state_completed_actions() -> None:
    for tool in ("bash", "readFile", "tool_search", "grepContent", "composioConnect"):
        res = _run_derive_step_state_in_node(tool_name=tool, exit_code=0)
        assert res["iconType"] == "completed", f"Expected completed for {tool}, got {res}"
        assert res["iconSymbol"] == "✔"
        assert res["color"] == "#c4f042"


def test_derive_step_state_output_delivery() -> None:
    res = _run_derive_step_state_in_node(is_output=True)
    assert res["iconType"] == "completed"
    assert res["iconSymbol"] == "✔"
    assert res["color"] == "#c4f042"


def test_derive_step_state_determinism_purity() -> None:
    """Repeated calls with identical parameters return identical outputs."""
    first = _run_derive_step_state_in_node(tool_name="writeFile", exit_code=0)
    for _ in range(5):
        assert _run_derive_step_state_in_node(tool_name="writeFile", exit_code=0) == first


def test_derive_step_state_undefined_exit_code_never_error() -> None:
    """exit_code=None must NEVER yield error iconType."""
    res_started = _run_derive_step_state_in_node(lifecycle_phase="started", exit_code=None)
    assert res_started["iconType"] == "started"

    res_tool = _run_derive_step_state_in_node(tool_name="bash", exit_code=None)
    assert res_tool["iconType"] == "completed"

    res_output = _run_derive_step_state_in_node(is_output=True, exit_code=None)
    assert res_output["iconType"] == "completed"


def test_drawer_tsx_verdict_banner_strict_type_guard() -> None:
    """Verifies AssistantStatusDrawer.tsx never compares bare `exit_code !== 0` without typeof check.

    In JavaScript `undefined !== 0` evaluates to true, causing normal started and delivery
    steps to falsely render as '✕ 执行异常'.
    """
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    bare_matches = re.findall(
        r"(?<!typeof activeSubStep\.exit_code === 'number' && )activeSubStep\.exit_code\s*!==\s*0",
        content,
    )
    assert not bare_matches, (
        f"Found bare `activeSubStep.exit_code !== 0` without typeof guard: {bare_matches}! "
        "Must use `typeof activeSubStep.exit_code === 'number' && activeSubStep.exit_code !== 0`."
    )
    assert "typeof activeSubStep.exit_code === 'number' && activeSubStep.exit_code !== 0" in content


def test_modal_step_item_preserves_thinking_and_tool_call_telemetry() -> None:
    """INV-MODAL-01: ModalStepItem interface and step assembly must preserve engineering telemetry.

    Specifically:
    1. ModalStepItem must declare optional thinking, tool_call, tool_result blocks.
    2. runDetail.steps mapping must forward thinking (th), tool_call (tc), and tool_result (tr)
       into each step item without dropping them.
    """
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 1. Interface definition check
    assert "thinking?:" in content, "ModalStepItem must declare thinking telemetry block"
    assert "tool_call?:" in content, "ModalStepItem must declare tool_call telemetry block"
    assert "tool_result?:" in content, "ModalStepItem must declare tool_result telemetry block"

    # 2. Assembly check
    assert "thinking: th" in content, "subSteps assembly must preserve thinking object"
    assert "tool_call: tc" in content, "subSteps assembly must preserve tool_call object"
    assert "tool_result: tr" in content, "subSteps assembly must preserve tool_result object"


def test_modal_zero_mock_contract_no_fake_tokens() -> None:
    """INV-MODAL-03: Zero mock numbers in token metrics or latencies.

    All displayed telemetry must be strictly conditional on backend presence,
    never falling back to fabricated constants like 1024, 2048, 500ms, or fake model names.
    """
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    assert not re.search(r"prompt_tokens\s*\|\|\s*\d+", content), "Found fabricated prompt_tokens fallback!"
    assert not re.search(r"completion_tokens\s*\|\|\s*\d+", content), "Found fabricated completion_tokens fallback!"
    assert not re.search(r"model\s*\|\|\s*['\"]gpt-['\"]", content), "Found fabricated model name fallback!"
