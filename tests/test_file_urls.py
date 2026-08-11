"""Tests for LobeHub file URL absolutization in SSE projection."""

from __future__ import annotations

import unittest

from gateway.lobehub_bridge.file_urls import absolutize_file_part, absolutize_file_parts


class TestFileUrls(unittest.TestCase):
    def test_absolutize_relative_url(self) -> None:
        part = absolutize_file_part(
            {"name": "a.pdf", "url": "/files/file_abc", "mimeType": "application/pdf"},
            base="http://127.0.0.1:8765",
        )
        self.assertEqual(part["url"], "http://127.0.0.1:8765/files/file_abc")

    def test_absolutize_parts_list(self) -> None:
        parts = absolutize_file_parts(
            ({"name": "a.pdf", "url": "/files/x"},),
            base="http://example.com",
        )
        self.assertEqual(parts[0]["url"], "http://example.com/files/x")


if __name__ == "__main__":
    unittest.main()
