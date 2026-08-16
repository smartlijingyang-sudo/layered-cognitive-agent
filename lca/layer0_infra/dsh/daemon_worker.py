"""Run one DSH turn in-process; emit NDJSON on stdout for lca-cli relay."""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from lca.layer0_infra.dsh.driver import DshTurnSpec
from lca.layer0_infra.dsh.models import DshNotification, DshTurnResult
from lca.layer0_infra.dsh.runtime import DshUnavailableError, SdkDshRuntime
from lca.layer0_infra.dsh.wire import (
    WORKER_KIND_ERROR,
    WORKER_KIND_FINISHED,
    WORKER_KIND_NOTIFICATION,
)


def _emit(line: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(line, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _spec_from_config(config: dict[str, Any]) -> DshTurnSpec:
    harness_env = config.get("harness_env")
    env = dict(harness_env) if isinstance(harness_env, dict) else None
    return DshTurnSpec(
        prompt=str(config.get("prompt") or ""),
        session_id=str(config.get("session_id") or ""),
        cwd=str(config.get("cwd") or ""),
        session_root=str(config.get("session_root") or ""),
        harness_env=env,
    )


def _runtime_from_config(config: dict[str, Any]) -> SdkDshRuntime:
    return SdkDshRuntime(turn_config=config)


def run_turn_config(config: dict[str, Any]) -> DshTurnResult:
    spec = _spec_from_config(config)
    runtime = _runtime_from_config(config)

    def on_event(notification: DshNotification) -> None:
        _emit(
            {
                "kind": WORKER_KIND_NOTIFICATION,
                "method": notification.method,
                "payload": notification.payload,
            }
        )

    return runtime.run_turn(spec, on_event)


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit({"kind": WORKER_KIND_ERROR, "message": f"invalid config JSON: {exc}"})
        sys.exit(1)
    if not isinstance(config, dict):
        _emit({"kind": WORKER_KIND_ERROR, "message": "config must be a JSON object"})
        sys.exit(1)
    try:
        result = run_turn_config(config)
    except DshUnavailableError as exc:
        _emit({"kind": WORKER_KIND_ERROR, "message": str(exc)})
        sys.exit(1)
    except Exception:
        _emit({"kind": WORKER_KIND_ERROR, "message": traceback.format_exc()})
        sys.exit(1)
    _emit(
        {
            "kind": WORKER_KIND_FINISHED,
            "session_id": result.session_id,
            "final_response": result.final_response,
            "finish_reason": result.finish_reason,
        }
    )


if __name__ == "__main__":
    main()
