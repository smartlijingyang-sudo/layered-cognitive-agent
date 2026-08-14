"""Host environment check — same tools the Onlyboxes image advertises."""

from __future__ import annotations

import importlib
import shutil
from collections.abc import Sequence

import structlog

_log = structlog.get_logger(__name__)

HOST_CLI = ("officecli", "pandoc", "ffmpeg", "jq")
HOST_PYTHON = (
    "docx",
    "openpyxl",
    "reportlab",
    "PIL",
    "pandas",
    "numpy",
    "yaml",
    "pypdf",
)


def log_host_toolchain(
    *, cli: Sequence[str] = HOST_CLI, python: Sequence[str] = HOST_PYTHON
) -> None:
    missing_cli = [name for name in cli if shutil.which(name) is None]
    missing_py: list[str] = []
    for name in python:
        try:
            importlib.import_module(name)
        except ImportError:
            missing_py.append(name)
    if missing_cli or missing_py:
        _log.warning(
            "host_toolchain_incomplete",
            missing_cli=missing_cli,
            missing_python=missing_py,
        )
        return
    _log.info("host_toolchain_ok", cli=list(cli), python=list(python))
