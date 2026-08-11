"""Guest scripts for shell and background command operations."""

from __future__ import annotations

import json

from lca.layer0_infra.computer.guest.preamble import wrap_guest_body


def build_background_start_script(*, command: str, command_id: str) -> str:
    body = f"""
command = {json.dumps(command)}
command_id = {json.dumps(command_id)}
_o.makedirs(_BG_DIR, exist_ok=True)
out_path = _P(_BG_DIR) / f"{{command_id}}.stdout"
err_path = _P(_BG_DIR) / f"{{command_id}}.stderr"
meta_path = _P(_BG_DIR) / f"{{command_id}}.json"
with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
    proc = _sp.Popen(command, shell=True, stdout=out_f, stderr=err_f, cwd=_ROOT)
meta_path.write_text(_j.dumps({{"commandId": command_id, "pid": proc.pid, "running": True}}))
result = {{
    "success": True,
    "commandId": command_id,
    "isBackground": True,
    "running": True,
    "stdout": "",
    "stderr": "",
    "output": f"Background command started: {{command_id}}",
}}
"""
    return wrap_guest_body(body)


def build_background_poll_script(*, command_id: str) -> str:
    body = f"""
command_id = {json.dumps(command_id)}
meta_path = _P(_BG_DIR) / f"{{command_id}}.json"
out_path = _P(_BG_DIR) / f"{{command_id}}.stdout"
err_path = _P(_BG_DIR) / f"{{command_id}}.stderr"
if not meta_path.is_file():
    result = {{"success": False, "error": f"unknown commandId: {{command_id}}"}}
else:
    meta = _j.loads(meta_path.read_text())
    pid = meta.get("pid")
    running = False
    if pid:
        try:
            _o.kill(pid, 0)
            running = True
        except OSError:
            running = False
    stdout = out_path.read_text(encoding="utf-8", errors="replace") if out_path.is_file() else ""
    stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
    meta["running"] = running
    meta_path.write_text(_j.dumps(meta))
    result = {{
        "success": True,
        "commandId": command_id,
        "running": running,
        "stdout": stdout,
        "stderr": stderr,
        "output": stdout,
    }}
"""
    return wrap_guest_body(body)


def build_background_kill_script(*, command_id: str) -> str:
    body = f"""
command_id = {json.dumps(command_id)}
meta_path = _P(_BG_DIR) / f"{{command_id}}.json"
if not meta_path.is_file():
    result = {{"success": False, "error": f"unknown commandId: {{command_id}}", "commandId": command_id}}
else:
    meta = _j.loads(meta_path.read_text())
    pid = meta.get("pid")
    ok = False
    if pid:
        try:
            _o.kill(pid, 9)
            ok = True
        except OSError as exc:
            meta["error"] = str(exc)
    meta["running"] = False
    meta_path.write_text(_j.dumps(meta))
    result = {{"success": ok, "commandId": command_id}}
"""
    return wrap_guest_body(body)


def build_shell_script(*, command: str) -> str:
    """Sync shell via subprocess in guest (fallback when terminalExec unavailable)."""
    body = f"""
command = {json.dumps(command)}
proc = _sp.run(command, shell=True, cwd=_ROOT, capture_output=True, text=True)
stdout = proc.stdout or ""
stderr = proc.stderr or ""
if stdout:
    print(stdout, end="" if stdout.endswith("\\n") else "\\n", flush=True)
if stderr:
    print(stderr, end="" if stderr.endswith("\\n") else "\\n", file=_sys.stderr, flush=True)
result = {{
    "success": proc.returncode == 0,
    "exitCode": proc.returncode,
    "stdout": stdout,
    "stderr": stderr,
    "output": stdout or stderr,
    "isBackground": False,
    "command": command,
}}
if proc.returncode != 0:
    result["error"] = stderr.strip() or f"exit {{proc.returncode}}"
"""
    return wrap_guest_body(body)
