"""Tests for ``scripts/check_no_silent_swallow.py`` (ADR-2026-09-03).

These tests pin the contract:

- Pure silence (``except: pass`` / bare docstring body / ``return None``
  on broad handler) → flagged.
- Narrow ``except`` returning a domain sentinel → NOT flagged.
- ``# WHY: ...`` / ``# INTENTIONAL: ...`` comments → NOT flagged.
- ``emit_exception_caught`` / ``raise`` → NOT flagged.
- Files in ``_ALLOWLIST_FILES`` (K6 fail-loud) → NOT flagged.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.check_no_silent_swallow import (
    _ALLOWLIST_FILES,
    _WHY_COMMENT_RE,
    _body_contains_allowed,
    _check_file,
    _is_broad_handler,
    _is_destructively_silent,
    _returns_domain_sentinel,
)

# ── unit tests for AST helpers ─────────────────────────────────────────


def test_broad_handler_detection() -> None:
    assert _is_broad_handler("Exception") is True
    assert _is_broad_handler("BaseException") is True
    assert _is_broad_handler("(Exception,)") is True
    assert _is_broad_handler("(BaseException,)") is True
    assert _is_broad_handler("KeyError") is False
    assert _is_broad_handler("(OSError, ValueError)") is False
    assert _is_broad_handler("httpx.HTTPError") is False


def test_destructively_silent_pass() -> None:
    src = "try:\n    pass\nexcept Exception:\n    pass\n"
    tree = ast.parse(src)
    handler = tree.body[0].handlers[0]
    assert _is_destructively_silent(handler.body) is True


def test_destructively_silent_docstring_only() -> None:
    src = 'try:\n    pass\nexcept Exception:\n    """why we swallow"""\n'
    tree = ast.parse(src)
    handler = tree.body[0].handlers[0]
    assert _is_destructively_silent(handler.body) is True


def test_destructively_silent_bare_return() -> None:
    src = "try:\n    pass\nexcept Exception:\n    return\n"
    tree = ast.parse(src)
    handler = tree.body[0].handlers[0]
    assert _is_destructively_silent(handler.body) is True


def test_destructively_silent_return_none() -> None:
    src = "try:\n    pass\nexcept Exception:\n    return None\n"
    tree = ast.parse(src)
    handler = tree.body[0].handlers[0]
    assert _is_destructively_silent(handler.body) is True


def test_not_silent_log_and_return_sentinel() -> None:
    src = (
        "try:\n    pass\n"
        "except Exception as exc:\n"
        "    log.error(str(exc))\n"
        "    return _fail_observation(str(exc))\n"
    )
    tree = ast.parse(src)
    handler = tree.body[0].handlers[0]
    assert _is_destructively_silent(handler.body) is False
    assert _returns_domain_sentinel(handler.body) is True


def test_body_contains_allowed_emit() -> None:
    src = (
        "try:\n    pass\n"
        "except Exception:\n"
        "    emit_exception_caught(record)\n"
    )
    tree = ast.parse(src)
    handler = tree.body[0].handlers[0]
    allowed, summary = _body_contains_allowed(handler.body)
    assert allowed is True
    assert "emit_exception_caught" in summary


def test_body_contains_allowed_raise() -> None:
    src = "try:\n    pass\nexcept Exception:\n    raise\n"
    tree = ast.parse(src)
    handler = tree.body[0].handlers[0]
    allowed, summary = _body_contains_allowed(handler.body)
    assert allowed is True
    assert summary == "raise"


def test_why_comment_regex() -> None:
    assert _WHY_COMMENT_RE.search("except Exception:  # WHY: missing file")
    assert _WHY_COMMENT_RE.search("# INTENTIONAL: defensive recovery")
    assert _WHY_COMMENT_RE.search("# intentional: defensive recovery")
    assert not _WHY_COMMENT_RE.search("# random comment")


# ── K6 allowlist exemption ──────────────────────────────────────────────


def test_k6_lifecycle_is_allowlisted() -> None:
    """The K6 fail-loud path itself is exempt — its hooks ARE the SSOT."""
    assert "lca_kernel/lifecycle.py" in _ALLOWLIST_FILES


# ── end-to-end on synthetic files ───────────────────────────────────────


def _write_and_check(tmp_path: Path, source: str) -> list:
    """Write source to tmp_path/lca_kernel/foo.py and run ``_check_file``."""
    pkg = tmp_path / "lca_kernel"
    pkg.mkdir()
    f = pkg / "foo.py"
    f.write_text(source)
    return _check_file(f)


def test_e2e_flags_broad_silence(tmp_path: Path) -> None:
    """``except Exception: pass`` on broad handler → finding."""
    src = "try:\n    x = 1\nexcept Exception:\n    pass\n"
    # Note: _check_file uses ``_ROOT`` to build ``rel``; we need to patch.
    from scripts import check_no_silent_swallow

    real_root = check_no_silent_swallow._ROOT
    check_no_silent_swallow._ROOT = tmp_path
    try:
        findings = _write_and_check(tmp_path, src)
    finally:
        check_no_silent_swallow._ROOT = real_root
    assert len(findings) == 1
    assert findings[0].handler == "Exception"
    assert findings[0].body_summary == "pass"


def test_e2e_skips_narrow_return(tmp_path: Path) -> None:
    """``except KeyError: return None`` → no finding (narrow + sentinel)."""
    src = "try:\n    x = d['k']\nexcept KeyError:\n    return None\n"
    from scripts import check_no_silent_swallow

    real_root = check_no_silent_swallow._ROOT
    check_no_silent_swallow._ROOT = tmp_path
    try:
        findings = _write_and_check(tmp_path, src)
    finally:
        check_no_silent_swallow._ROOT = real_root
    assert findings == []


def test_e2e_skips_with_why_comment(tmp_path: Path) -> None:
    """``except: pass`` with ``# INTENTIONAL:`` → no finding."""
    src = (
        "try:\n    pass\n"
        "except Exception:\n"
        "    pass  # INTENTIONAL: defensive no-op\n"
    )
    from scripts import check_no_silent_swallow

    real_root = check_no_silent_swallow._ROOT
    check_no_silent_swallow._ROOT = tmp_path
    try:
        findings = _write_and_check(tmp_path, src)
    finally:
        check_no_silent_swallow._ROOT = real_root
    assert findings == []


def test_e2e_skips_with_emit(tmp_path: Path) -> None:
    """``except: emit_exception_caught(...)`` → no finding (SSOT path)."""
    src = (
        "try:\n    pass\n"
        "except Exception:\n"
        "    emit_exception_caught(record)\n"
    )
    from scripts import check_no_silent_swallow

    real_root = check_no_silent_swallow._ROOT
    check_no_silent_swallow._ROOT = tmp_path
    try:
        findings = _write_and_check(tmp_path, src)
    finally:
        check_no_silent_swallow._ROOT = real_root
    assert findings == []
