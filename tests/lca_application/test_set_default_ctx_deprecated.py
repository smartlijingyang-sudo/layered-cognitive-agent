"""ADR-0115 决定 7: ``set_default_ctx`` is **deprecated**; retire 2027-02-28.

The legacy call must still work during the deprecation window but must
emit a :class:`DeprecationWarning` so existing apps surface the upcoming
removal. The new path is to call ``lca_kernel.run_kernel()`` explicitly
and pass the returned ctx as ``scope=`` to ``Agent`` / ``Team``.
"""

from __future__ import annotations

import re
import warnings

from lca.application import default_context as dc


def test_set_default_ctx_emits_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dc.set_default_ctx(None)

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations, "set_default_ctx must emit a DeprecationWarning"
    msg = str(deprecations[0].message)
    assert "set_default_ctx" in msg
    assert "deprecated" in msg.lower()
    assert "2027-02-28" in msg, f"retire date missing from message: {msg!r}"


def test_module_load_emits_deprecation_notice() -> None:
    """Importing the module surfaces the deprecation once for any app load."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import importlib

        importlib.reload(dc)

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any(
        "set_default_ctx" in str(w.message) and "2027-02-28" in str(w.message) for w in deprecations
    ), f"module reload should surface deprecation; got: {[str(w.message) for w in deprecations]}"


def test_set_default_ctx_is_not_exported_via_default_context_star() -> None:
    """Star-imports cannot accidentally bring ``set_default_ctx`` in."""
    from lca.application import default_context as dc_module

    exported = set(getattr(dc_module, "__all__", ()))
    assert "set_default_ctx" not in exported, (
        "set_default_ctx must not be exported via __all__ to prevent "
        "star-imports from spreading the deprecated symbol"
    )


def test_set_default_ctx_still_assigns_ctx_to_holder() -> None:
    """During the deprecation window, set_default_ctx still works as before."""
    sentinel = object()
    try:
        previous = dc.holder.ctx
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            dc.set_default_ctx(sentinel)  # type: ignore[arg-type]
        assert dc.holder.ctx is sentinel
    finally:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            if previous is None:
                # Clear; the next set will be allowed.
                dc.holder.ctx = None
            else:
                # Restore prior — note: set_default_ctx raises if there's
                # already a different ctx bound; reset via holder instead.
                dc.holder.ctx = previous
                dc.holder.booting = False
                dc.holder.boot_complete.set()


def test_application_api_no_longer_exports_set_default_ctx() -> None:
    """``lca.application.api.__all__`` must not include set_default_ctx."""
    import lca.application.api as api

    assert "set_default_ctx" not in api.__all__


def test_application_api_no_longer_imports_set_default_ctx_directly() -> None:
    """``lca.application.api`` must not import set_default_ctx as a symbol."""
    import lca.application.api as api

    assert not hasattr(api, "set_default_ctx"), (
        "set_default_ctx should not be re-exported from lca.application.api"
    )


def test_docstring_records_retire_date() -> None:
    """Module docstring documents the deprecation window."""
    doc = dc.__doc__ or ""
    assert "2027-02-28" in doc, f"retire date missing from module docstring: {doc!r}"
    assert re.search(r"ADR-?0115", doc)
