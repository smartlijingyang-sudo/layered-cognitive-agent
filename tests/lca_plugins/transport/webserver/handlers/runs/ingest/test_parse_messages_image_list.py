"""Regression tests for the LobeHub → LCA ``parse_messages`` contract.

Covers the bug fixed in the attachment-hydration PR: ``executeGatewayRun``
on the LobeHub side only forwarded ``lastUser.content`` to ``POST /runs``,
dropping the top-level ``imageList`` / ``fileList`` fields. ``parse_messages``
must still surface the refs from the trailing user message so that
``prepare_run_from_messages`` hydrates them into the prompt.
"""

from __future__ import annotations

from typing import Any

from lca.plugins.transport.webserver.handlers.runs.ingest.ingress.ingress import (
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
