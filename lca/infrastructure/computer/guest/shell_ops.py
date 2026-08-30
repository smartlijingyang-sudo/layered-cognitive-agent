"""Static guest scripts for shell and background commands — params arrive as JSON."""

from __future__ import annotations

from lca.infrastructure.computer.guest.json_script import compose_json_script
from lca.infrastructure.computer.guest.preamble import SCRIPT_PRELUDE

BACKGROUND_START_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    command = args.get("command") or ""
    command_id = args.get("commandId") or ""
    os.makedirs(BG_DIR, exist_ok=True)
    out_path = Path(BG_DIR) / f"{command_id}.stdout"
    err_path = Path(BG_DIR) / f"{command_id}.stderr"
    meta_path = Path(BG_DIR) / f"{command_id}.json"
    with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
        proc = subprocess.Popen(command, shell=True, stdout=out_f, stderr=err_f, cwd=ROOT)
    meta_path.write_text(json.dumps({"commandId": command_id, "pid": proc.pid, "running": True}))
    emit({
        "success": True,
        "commandId": command_id,
        "isBackground": True,
        "running": True,
        "stdout": "",
        "stderr": "",
        "output": f"Background command started: {command_id}",
    })
"""
)

BACKGROUND_POLL_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    command_id = args.get("commandId") or ""
    meta_path = Path(BG_DIR) / f"{command_id}.json"
    out_path = Path(BG_DIR) / f"{command_id}.stdout"
    err_path = Path(BG_DIR) / f"{command_id}.stderr"
    if not meta_path.is_file():
        emit({"success": False, "error": f"unknown commandId: {command_id}"})
        return
    meta = json.loads(meta_path.read_text())
    pid = meta.get("pid")
    running = False
    if pid:
        try:
            os.kill(pid, 0)
            running = True
        except OSError:
            running = False
    stdout = out_path.read_text(encoding="utf-8", errors="replace") if out_path.is_file() else ""
    stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
    meta["running"] = running
    meta_path.write_text(json.dumps(meta))
    emit({
        "success": True,
        "commandId": command_id,
        "running": running,
        "stdout": stdout,
        "stderr": stderr,
        "output": stdout,
    })
"""
)

BACKGROUND_KILL_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    command_id = args.get("commandId") or ""
    meta_path = Path(BG_DIR) / f"{command_id}.json"
    if not meta_path.is_file():
        emit({"success": False, "error": f"unknown commandId: {command_id}", "commandId": command_id})
        return
    meta = json.loads(meta_path.read_text())
    pid = meta.get("pid")
    ok = False
    if pid:
        try:
            os.kill(pid, 9)
            ok = True
        except OSError as exc:
            meta["error"] = str(exc)
    meta["running"] = False
    meta_path.write_text(json.dumps(meta))
    emit({"success": ok, "commandId": command_id})
"""
)

SHELL_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    command = args.get("command") or ""
    proc = subprocess.run(command, shell=True, cwd=ROOT, capture_output=True, text=True)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if stdout:
        print(stdout, end="" if stdout.endswith("\\n") else "\\n", flush=True)
    if stderr:
        print(stderr, end="" if stderr.endswith("\\n") else "\\n", file=sys.stderr, flush=True)
    result = {
        "success": proc.returncode == 0,
        "exitCode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "output": stdout or stderr,
        "isBackground": False,
        "command": command,
    }
    if proc.returncode != 0:
        result["error"] = stderr.strip() or f"exit {proc.returncode}"
    emit(result)
"""
)


def build_background_start_script(*, command: str, command_id: str) -> str:
    return compose_json_script(
        BACKGROUND_START_SCRIPT, {"command": command, "commandId": command_id}
    )


def build_background_poll_script(*, command_id: str) -> str:
    return compose_json_script(BACKGROUND_POLL_SCRIPT, {"commandId": command_id})


def build_background_kill_script(*, command_id: str) -> str:
    return compose_json_script(BACKGROUND_KILL_SCRIPT, {"commandId": command_id})


def build_shell_script(*, command: str) -> str:
    return compose_json_script(SHELL_SCRIPT, {"command": command})
