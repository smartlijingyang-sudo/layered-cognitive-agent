"""Wire contract tests for ``collect_file_refs``.

Regression target: LobeHub UI attaches files via ``imageList`` / ``fileList`` /
``files`` fields on the user-message dict. The LCA ingress was silently
dropping them when the LobeHub transport translated ``UIChatMessage`` to
OpenAI-shaped ``messages`` without copying those fields across. This test
locks the parsing contract so any future wire-shape change has to be made
explicit.
"""

from __future__ import annotations

from typing import Any

from lca.plugins.transport.webserver.handlers.runs.api.file_reference_parsing import (
    collect_file_refs,
)


def _by_source(refs):
    return {ref.source for ref in refs}


def test_string_only_message_has_no_refs():
    msgs = [{"role": "user", "content": "分析下"}]
    assert collect_file_refs(msgs) == [], (
        "Bare text must not invent file references — guards against silent hydration."
    )


def test_imagelist_top_level_field_yields_image_ref():
    msgs = [{
        "role": "user",
        "content": "分析下",
        "imageList": [{"id": "image-file", "url": "https://s3/img.png"}],
    }]
    refs = collect_file_refs(msgs)
    assert len(refs) == 1
    assert refs[0].source == "imageList"
    assert refs[0].url == "https://s3/img.png"


def test_filelist_top_level_field_yields_file_ref():
    msgs = [{
        "role": "user",
        "content": "分析下",
        "fileList": [{
            "id": "file-id-1",
            "name": "report.pdf",
            "url": "https://s3/report.pdf",
            "mime_type": "application/pdf",
        }],
    }]
    refs = collect_file_refs(msgs)
    assert len(refs) == 1
    assert refs[0].source == "files"
    assert refs[0].name == "report.pdf"
    assert refs[0].mime_type == "application/pdf"


def test_legacy_files_field_still_supported():
    # Pre-2024 LobeHub shape — keep the deprecation path alive while it exists.
    msgs = [{
        "role": "user",
        "content": "分析下",
        "files": [{
            "id": "file-id-1",
            "name": "notes.txt",
            "url": "https://s3/notes.txt",
        }],
    }]
    refs = collect_file_refs(msgs)
    assert len(refs) == 1
    assert refs[0].name == "notes.txt"


def test_openai_multimodal_image_url_yields_image_ref():
    msgs = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "分析下"},
            {"type": "image_url", "image_url": {"url": "https://s3/foo.png"}},
        ],
    }]
    refs = collect_file_refs(msgs)
    assert len(refs) == 1
    assert refs[0].source == "image_url"


def test_mixed_fields_are_merged_and_deduplicated():
    msgs = [{
        "role": "user",
        "content": "分析下",
        "imageList": [{"id": "img-1", "url": "https://s3/a.png"}],
        "fileList": [{"id": "file-1", "name": "a.txt", "url": "https://s3/a.txt"}],
    }]
    refs = collect_file_refs(msgs)
    assert len(refs) == 2
    assert _by_source(refs) == {"imageList", "files"}


def test_collect_file_refs_passes_through_prior_turn_refs():
    """``collect_file_refs`` does NOT scope to the last user message — that
    filtering is owned by ``parse_messages``. This test documents the
    division of labour so the next reader does not assume parsing is
    silently happening here.
    """
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "first", "imageList": [{"id": "x", "url": "https://s3/x"}]},
        {"role": "assistant", "content": "ack"},
        {"role": "user", "content": "分析下"},
    ]
    refs = collect_file_refs(msgs)
    assert len(refs) == 1
    assert refs[0].url == "https://s3/x"
