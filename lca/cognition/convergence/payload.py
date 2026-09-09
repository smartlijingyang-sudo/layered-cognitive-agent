"""Observation payload readers for convergence fold (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.constants import MIN_SUBSTANTIVE_STDOUT_CHARS
from lca.cognition.convergence.task_class import task_requires_synthesis
from lca.contracts.atoms.semantic.cli_diagnostic import is_cli_diagnostic_output
from lca.contracts.models.core.execution.decision import Observation

_STDOUT_KEYS = ("output", "stdout", "content", "text")


def payload_stdout(payload: object | None, *, limit: int = 4000) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in _STDOUT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:limit]
    return ""


def payload_files_created(payload: object | None) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    for key in ("files_created", "files"):
        value = payload.get(key)
        if isinstance(value, (list, tuple)):
            return tuple(str(item) for item in value if str(item))
    return ()


def observation_files_created(observation: Observation | None) -> tuple[str, ...]:
    if observation is None:
        return ()
    extra = observation.extra if isinstance(observation.extra, dict) else {}
    files = extra.get("files_created")
    if isinstance(files, (list, tuple)):
        from_extra = tuple(str(item) for item in files if str(item))
        if from_extra:
            return from_extra
    return payload_files_created(observation.payload)


def merge_files_created(
    payload: object | None,
    *,
    files_created: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if files_created:
        return files_created
    return payload_files_created(payload)


def is_substantive_stdout(text: str) -> bool:
    stripped = text.strip()
    if not stripped or is_cli_diagnostic_output(stripped):
        return False
    if len(stripped) < MIN_SUBSTANTIVE_STDOUT_CHARS:
        return False
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    return not (len(lines) == 1 and lines[0].startswith(("import ", "from ")))


def turn_has_delivery_signal(
    payload: object | None,
    *,
    files_created: tuple[str, ...] = (),
    task: str = "",
) -> bool:
    if merge_files_created(payload, files_created=files_created):
        return True
    if task_requires_synthesis(task):
        return False
    return is_substantive_stdout(payload_stdout(payload))


__all__ = [
    "is_substantive_stdout",
    "merge_files_created",
    "observation_files_created",
    "payload_files_created",
    "payload_stdout",
    "turn_has_delivery_signal",
]
