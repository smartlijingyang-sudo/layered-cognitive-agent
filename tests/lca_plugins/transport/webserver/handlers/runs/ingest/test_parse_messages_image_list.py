"""Regression tests for the LobeHub → LCA ``parse_messages`` contract.

Covers the bug fixed in the attachment-hydration PR: ``executeGatewayRun``
on the LobeHub side only forwarded ``lastUser.content`` to ``POST /runs``,
dropping the top-level ``imageList`` / ``fileList`` fields. ``parse_messages``
must still surface the refs from the trailing user message so that
``prepare_run_from_messages`` hydrates them into the prompt.
"""

from __future__ import annotations

from typing import Any

from lca.plugins.transport.webserver.handlers.runs.ingest import (
    parse_messages,
)


def test_string_only_message_produces_no_file_refs():
    parsed = parse_messages([{"role": "user", "content": "分析下"}])
    assert parsed.user_text == "分析下"
    assert parsed.file_refs == ()


def test_top_level_imagelist_is_extracted_from_last_user_message():
    msgs = [{
        "role": "user",
        "content": "分析下",
        "imageList": [{"id": "img-1", "url": "https://s3/img.png"}],
    }]
    parsed = parse_messages(msgs)
    assert parsed.file_refs
    assert parsed.file_refs[0].source == "imageList"


def test_top_level_filelist_is_extracted_from_last_user_message():
    msgs = [{
        "role": "user",
        "content": "分析下",
        "fileList": [{
            "id": "file-1",
            "name": "report.pdf",
            "url": "https://s3/report.pdf",
        }],
    }]
    parsed = parse_messages(msgs)
    assert parsed.file_refs
    assert parsed.file_refs[0].source == "files"


def test_prior_turn_imagelist_is_dropped():
    """Only the trailing user message contributes attachments — prior-turn
    imageList must NOT bleed into the current run's hydration, otherwise
    every fresh turn would re-attach history.
    """
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "first",
         "imageList": [{"id": "old", "url": "https://s3/old.png"}]},
        {"role": "assistant", "content": "ack"},
        {"role": "user", "content": "分析下"},
    ]
    parsed = parse_messages(msgs)
    assert parsed.file_refs == ()


def test_image_only_message_does_not_fall_back_to_previous_text():
    """An image-only trailing user message (empty content, imageList present)
    is the current turn: ``parse_messages`` must NOT reach back into history
    and reuse the previous user text as the run task, otherwise the model
    re-answers an old question instead of handling the upload.
    """
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "你存在哪里了 文件内容是什么"},
        {"role": "assistant", "content": "查到了"},
        {"role": "user", "content": "",
         "imageList": [{"id": "img-1", "url": "https://s3/photo.jpg"}]},
    ]
    parsed = parse_messages(msgs)
    assert parsed.user_text == ""
    assert len(parsed.file_refs) == 1
    assert parsed.file_refs[0].source == "imageList"


def test_imagelist_without_mime_type_has_empty_mime():
    """LobeHub ``imageList`` items carry no MIME type. The parser must not
    fabricate ``image/png``: a JPEG upload would then fail magic-bytes
    validation and be silently dropped.
    """
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "",
         "imageList": [{"id": "img-1", "url": "https://s3/photo.jpg"}]},
    ]
    parsed = parse_messages(msgs)
    assert parsed.file_refs[0].mime_type == ""
