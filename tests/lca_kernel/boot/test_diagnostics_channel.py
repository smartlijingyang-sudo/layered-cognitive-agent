"""Pin: boot diagnostics emit through structlog only (RA-070).

``lca_kernel/boot`` is the boot seam; its diagnostics must go through the
single structlog channel. stdlib ``logging`` writes in this package would
split diagnostics across two channels, so this test scans the package
sources and fails on any stdlib logging usage.
"""

from __future__ import annotations

from pathlib import Path

_BOOT_PKG = Path(__file__).resolve().parents[4] / "lca_kernel" / "boot"

_STDLIB_LOGGING_MARKERS = (
    "import logging",
    "from logging import",
    "logging.getLogger",
    "logging.basicConfig",
)


def _boot_sources() -> list[Path]:
    return sorted(p for p in _BOOT_PKG.glob("*.py") if p.name != "__init__.py")


def test_boot_package_uses_structlog_only() -> None:
    offenders: list[str] = []
    for src in _boot_sources():
        text = src.read_text(encoding="utf-8")
        hits = [m for m in _STDLIB_LOGGING_MARKERS if m in text]
        if hits:
            offenders.append(f"{src.name}: {', '.join(hits)}")
    assert not offenders, (
        "boot diagnostics must go through structlog only; "
        f"stdlib logging found in: {offenders}"
    )


def test_boot_modules_bind_a_structlog_logger() -> None:
    """Every boot module that logs binds ``structlog.get_logger``."""
    import ast

    missing: list[str] = []
    for src in _boot_sources():
        text = src.read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get_logger"
        ]
        has_log_calls = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"debug", "info", "warning", "error", "exception", "critical"}
            for n in ast.walk(tree)
        )
        if has_log_calls and not calls:
            missing.append(src.name)
    assert not missing, f"boot modules log without structlog.get_logger: {missing}"
