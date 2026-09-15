"""The driver-debug scans skip only the failures they can actually justify.

`find_stderr_for_run` globs candidate kernel stderr files and `_build_factory_index`
rglobs `lca/plugins/**/*.py`; both used to wrap the read in `except Exception`, so a
defect in the scanning code itself was reported to the operator as "no stderr found
for this run" or as a plugin that simply provides nothing.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest

from lca.infrastructure.cli.commands.runs import driver_debug

RUN = "run_scan"


def _read_text_only_for(real: object) -> object:
    def _read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "raise-runtime-error.py":
            raise RuntimeError("defect in the scanner, not a missing file")
        return pathlib.Path.read_text(self, encoding="utf-8")  # type: ignore[arg-type]

    return _read_text


def test_stderr_scan_skips_unreadable_candidate_and_keeps_looking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    unreadable = tmp_path / "rotated.log"
    unreadable.mkdir()  # reading a directory is IsADirectoryError, an OSError
    match = tmp_path / "live.log"
    match.write_text(
        f"runtime_lifecycle journal_sequence=None lifecycle_event=started run_id={RUN}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(driver_debug.glob, "glob", lambda _pattern: [str(unreadable), str(match)])

    assert driver_debug.find_stderr_for_run(RUN) == match


def test_stderr_scan_propagates_a_non_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "boom.log"
    bad.write_text("nothing useful", encoding="utf-8")
    monkeypatch.setattr(driver_debug.glob, "glob", lambda _pattern: [str(bad)])

    def _read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise RuntimeError("defect in the scanner, not a missing file")

    monkeypatch.setattr(Path, "read_text", _read_text)

    with pytest.raises(RuntimeError, match="defect in the scanner"):
        driver_debug.find_stderr_for_run(RUN)


def test_factory_index_skips_non_utf8_plugin_and_keeps_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    plugins = tmp_path / "lca" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "good.py").write_text(
        '@plugin(id="x", provides=(\n    "region::factory_a",\n))\nasync def setup(ctx, cfg): ...\n',
        encoding="utf-8",
    )
    (plugins / "binary.py").write_bytes(b"\xff\xfe\x00 not utf-8 at all")

    registry = driver_debug._build_factory_index()

    assert registry.get("region::factory_a") == ["good"]


def test_factory_index_propagates_an_unexpected_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    plugins = tmp_path / "lca" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "raise-runtime-error.py").write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(Path, "read_text", _read_text_only_for(None))

    with pytest.raises(RuntimeError, match="defect in the scanner"):
        driver_debug._build_factory_index()
