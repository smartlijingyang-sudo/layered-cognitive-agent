"""DSH runtime that delegates execution to the machine plane.

Phase 2 (preferred): daemon runs SDK in-process; notifications stream over
device WebSocket via ``StreamingDshRuntime`` (``gateway/device_gateway``).

Legacy batch path (``runCommand`` + ``events.jsonl`` replay) remains as fallback
when the device hub is unavailable.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import structlog

from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.protocols import DshRuntime
from lca.infrastructure.comparison.dsh_driver.driver import DshTurnSpec
from lca.infrastructure.comparison.dsh_driver.models import DshNotification, DshTurnResult
from lca.infrastructure.comparison.dsh_driver.settings import DshSettings
from lca.infrastructure.computer.machine import MachineTransport

_log = structlog.get_logger(__name__)

_REL_DIR = ".lca/dsh"
_RUNNER_NAME = "runner.py"
_CONFIG_NAME = "config.json"
_EVENTS_NAME = "events.jsonl"

_DSH_TIMEOUT_S = 600

_RUNNER_SCRIPT = '''\
"""DSH runner — executes one turn on the machine side.

Invoked by MachineDshRuntime via runCommand.  Reads config from the path
passed as argv[1], runs the DSH SDK, writes notifications to a JSONL
file, and prints the final result as JSON to stdout.
"""

import json
import sys
import traceback


def main() -> None:
    config_path = sys.argv[1]
    with open(config_path) as f:
        config = json.load(f)

    events_path = config.pop("events_path")
    prompt = config.pop("prompt")
    session_id = config.pop("session_id")

    try:
        from deepseek_harness import DeepSeekHarness
    except ImportError:
        result = {"error": "deepseek-harness-sdk is not installed in this environment"}
        print(json.dumps(result))
        sys.exit(1)

    with open(events_path, "w") as ef:

        def on_notification(raw: object) -> None:
            method = getattr(raw, "method", None)
            payload = getattr(raw, "payload", None)
            if not isinstance(method, str):
                return
            body = payload if isinstance(payload, dict) else {}
            ef.write(json.dumps({"method": method, "payload": body}, ensure_ascii=False) + "\\n")
            ef.flush()

        try:
            with DeepSeekHarness(**config) as harness:
                result = harness.run(
                    prompt, session_id=session_id, on_notification=on_notification
                )
            out = {
                "session_id": result.session_id,
                "final_response": result.final_response or "",
                "finish_reason": result.finish_reason,
            }
        except Exception:
            out = {"error": traceback.format_exc(), "finish_reason": "failed"}

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
'''


class MachineDshRuntime(DshRuntime):
    """Execute DSH turns on the machine plane via the sidecar transport.

    Lifecycle per turn: write runner + config → runCommand → readFile events.
    The SDK runs as sandbox-user, same trust boundary as the CLI.
    """

    def __init__(
        self,
        transport: MachineTransport,
        machine: PlaneRef,
        settings: DshSettings,
    ) -> None:
        self._transport = transport
        self._machine = machine
        self._settings = settings

    def run_turn(
        self,
        spec: DshTurnSpec,
        on_event: Callable[[DshNotification], None],
    ) -> DshTurnResult:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._run_turn_async(spec, on_event))
        finally:
            loop.close()

    async def _run_turn_async(
        self,
        spec: DshTurnSpec,
        on_event: Callable[[DshNotification], None],
    ) -> DshTurnResult:
        root = self._machine.root.rstrip("/")
        rel_dir = _REL_DIR
        runner_path = f"{root}/{rel_dir}/{_RUNNER_NAME}"
        config_path = f"{root}/{rel_dir}/{_CONFIG_NAME}"
        events_path = f"{root}/{rel_dir}/{_EVENTS_NAME}"

        config = self._build_config(spec, events_path)
        files: dict[str, bytes | str] = {
            f"{rel_dir}/{_RUNNER_NAME}": _RUNNER_SCRIPT,
            f"{rel_dir}/{_CONFIG_NAME}": json.dumps(config, ensure_ascii=False),
        }

        await self._transport.write_files(files, base_dir=self._machine.root)

        cmd = f"python3 {runner_path} {config_path}"
        op_result = await self._transport.computer_op(
            "runCommand",
            {"command": cmd, "cwd": self._machine.root, "timeout_s": _DSH_TIMEOUT_S},
            timeout_s=_DSH_TIMEOUT_S,
        )

        stdout = _extract_content(op_result)
        if not _op_success(op_result):
            error = _extract_error(op_result) or stdout or "DSH runner failed"
            _log.warning("dsh_runner_failed", error=error)
            on_event(DshNotification(method="session.error", payload={"error": error}))
            return DshTurnResult(session_id=spec.session_id, finish_reason="failed")

        events = await self._read_events(events_path)
        for notification in events:
            on_event(notification)

        return _parse_result(stdout, spec.session_id)

    def _build_config(self, spec: DshTurnSpec, events_path: str) -> dict[str, Any]:
        cfg = self._settings
        config: dict[str, Any] = {
            "provider": cfg.provider,
            "model": cfg.resolved_model(),
            "cwd": spec.cwd,
            "session_root": spec.session_root,
            "request_timeout_seconds": cfg.request_timeout_seconds,
            "prompt": spec.prompt,
            "session_id": spec.session_id,
            "events_path": events_path,
        }
        if spec.harness_env:
            config["env"] = dict(spec.harness_env)
        max_tokens = cfg.resolved_max_tokens()
        if max_tokens is not None:
            config["max_tokens"] = max_tokens
        cordis = cfg.resolved_cordis()
        if cordis is not None:
            config["cordis"] = cordis
        api_key = cfg.resolved_api_key()
        if api_key:
            config["api_key"] = api_key
        base_url = cfg.resolved_base_url()
        if base_url:
            config["base_url"] = base_url
        return config

    async def _read_events(self, events_path: str) -> list[DshNotification]:
        try:
            result = await self._transport.computer_op(
                "readFile", {"path": events_path}, timeout_s=30
            )
        except Exception:
            _log.warning("dsh_events_read_failed", path=events_path, exc_info=True)
            return []
        content = _extract_content(result)
        if not content:
            return []
        notifications: list[DshNotification] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                notifications.append(
                    DshNotification(method=data["method"], payload=data.get("payload", {}))
                )
            except (json.JSONDecodeError, KeyError):
                _log.warning("dsh_event_parse_failed", line=line[:200])
        return notifications


def _op_success(result: dict[str, Any]) -> bool:
    return bool(result.get("success", False))


def _extract_content(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, str):
        return content
    output = result.get("output")
    if isinstance(output, str):
        return output
    return ""


def _extract_error(result: dict[str, Any]) -> str:
    err = result.get("error")
    return str(err) if err else ""


def _parse_result(stdout: str, fallback_session_id: str) -> DshTurnResult:
    try:
        data = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return DshTurnResult(
            session_id=fallback_session_id,
            final_response=stdout.strip(),
            finish_reason="completed" if stdout.strip() else "failed",
        )
    if "error" in data:
        return DshTurnResult(
            session_id=data.get("session_id", fallback_session_id),
            finish_reason="failed",
        )
    return DshTurnResult(
        session_id=data.get("session_id", fallback_session_id),
        final_response=data.get("final_response", ""),
        finish_reason=data.get("finish_reason"),
    )
