"""Port of packages/local-file-shell/src/file/expandTilde.ts."""

from __future__ import annotations

from pathlib import Path


def expand_tilde(input_path: str | None, *, home: str | Path | None = None) -> str | None:
    if not input_path:
        return input_path
    home_dir = str(Path(home).expanduser() if home is not None else Path.home())
    if input_path == "~":
        return home_dir
    if input_path.startswith("~/") or input_path.startswith("~\\"):
        return str(Path(home_dir) / input_path[2:])
    return input_path


def resolve_against_cwd(
    input_path: str | None,
    cwd: str | None = None,
    *,
    home: str | Path | None = None,
) -> str | None:
    expanded = expand_tilde(input_path, home=home)
    if not expanded or not cwd:
        return expanded
    path = Path(expanded)
    if path.is_absolute():
        return str(path)
    return str(Path(cwd) / path)
