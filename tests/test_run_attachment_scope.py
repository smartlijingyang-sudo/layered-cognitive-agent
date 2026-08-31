"""Regression: ``run_attachment_scope`` must treat a bare string as one id.

The previous signature accepted only ``Sequence[str]``; when callers passed a
single :class:`str` (e.g. ``run_attachment_scope(aid)``), ``list(attachment_ids)``
iterated character-by-character, producing ``['f','i','l','e',...]`` instead
of ``['file_xxx']``. That silently injected garbage into FileStore lookups and
crashed the system-role renderer with an "unknown attachment_id='f'" error.

This test pins the contract: a single string is wrapped in a one-tuple, not
split into characters.
"""

from __future__ import annotations

from lca.infrastructure.tools.run_attachment_scope import (
    get_current_run_attachment_ids,
    run_attachment_scope,
)


def test_bare_string_is_treated_as_one_id() -> None:
    with run_attachment_scope("file_abc_123"):
        assert get_current_run_attachment_ids() == ("file_abc_123",)


def test_list_of_strings_still_works() -> None:
    with run_attachment_scope(["file_a", "file_b"]):
        assert get_current_run_attachment_ids() == ("file_a", "file_b")


def test_tuple_of_strings_still_works() -> None:
    with run_attachment_scope(("file_x", "file_y")):
        assert get_current_run_attachment_ids() == ("file_x", "file_y")
