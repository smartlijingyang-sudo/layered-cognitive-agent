"""Observation payload readers for convergence fold (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.constants import MIN_SUBSTANTIVE_STDOUT_CHARS
from lca.contracts.atoms.semantic.cli_diagnostic import is_cli_diagnostic_output
from lca.contracts.models.core.execution.decision import Observation

_STDOUT_KEYS = ("output", "stdout", "content", "text")
_FILE_KEYS = ("files_created", "files")


def payload_stdout(payload: object | None, *, limit: int = 4000) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in _STDOUT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:limit]
    return ""


def _file_names(value: object | None) -> tuple[str, ...]:
    """Normalize harvested file entries to names.

    The sandbox harvest carries A2A file metadata dicts (``name`` / ``url`` /
    ``mimeType``; see ``infrastructure/tools/sandbox/observation.py``), while
    writeFile-shaped producers carry plain name strings. Stringifying a dict
    entry would surface its repr as a filename.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    names: list[str] = []
    for item in value:
        name = str(item.get("name") or "") if isinstance(item, dict) else str(item or "")
        if name:
            names.append(name)
    return tuple(names)


def payload_files_created(payload: object | None) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    for key in _FILE_KEYS:
        names = _file_names(payload.get(key))
        if names:
            return names
    return ()


def observation_files_created(observation: Observation | None) -> tuple[str, ...]:
    if observation is None:
        return ()
    extra = observation.extra if isinstance(observation.extra, dict) else {}
    for key in _FILE_KEYS:
        names = _file_names(extra.get(key))
        if names:
            return names
    return payload_files_created(observation.payload)


def merge_files_created(
    payload: object | None,
    *,
    files_created: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if files_created:
        return files_created
    return payload_files_created(payload)


def is_substantive_stdout(text: str | list[str] | tuple[str, ...] | None) -> bool:
    """Return True iff ``text`` carries content worth surfacing as a delivery.

    Accepts str (the stdout-shaped historical case) and list/tuple of str
    (read-shaped tools such as ``listFiles`` return a list of entries
    directly).  A non-empty list with at least one non-blank entry counts;
    an empty list does not (it conveys "no items", which the model still
    needs to surface as a final response).
    """
    if text is None:
        return False
    if isinstance(text, (list, tuple)):
        return any(
            isinstance(item, str) and item.strip() and not is_cli_diagnostic_output(item.strip())
            for item in text
        )
    if not isinstance(text, str):
        return False
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
    del task
    if merge_files_created(payload, files_created=files_created):
        return True
    # Direct list/tuple payload (read-shaped tools) — bypass payload_stdout
    # which only knows the dict-wrapped stdout keys.
    if isinstance(payload, (list, tuple)):
        return is_substantive_stdout(payload)
    return is_substantive_stdout(payload_stdout(payload))


__all__ = [
    "is_substantive_stdout",
    "merge_files_created",
    "observation_files_created",
    "payload_files_created",
    "payload_stdout",
    "turn_has_delivery_signal",
]
