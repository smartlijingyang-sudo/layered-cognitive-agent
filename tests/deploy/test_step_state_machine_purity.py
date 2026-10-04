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

    fn_code = match.group(1).replace("export interface", "interface").replace("export function", "function")

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
        raise RuntimeError(f"Node execution failed (code {proc.returncode}): {proc.stderr}\nScript: {script}")
    return json.loads(proc.stdout)


def test_derive_step_state_exists_in_drawer_tsx() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")
    assert "deriveStepState" in content, "deriveStepState must be defined in AssistantStatusDrawer.tsx"


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
    for tool in ("writeFile", "editFile", "create_assistant_skill", "patch_config", "write_to_file"):
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
