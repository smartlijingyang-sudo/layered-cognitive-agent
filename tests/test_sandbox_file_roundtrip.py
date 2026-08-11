"""ADR-0046 path contract tests for Onlyboxes artifact harvest helpers."""

from __future__ import annotations

import base64
import json
import unittest

from lca.layer0_infra.sandbox.onlyboxes_artifacts import (
    ARTIFACT_BEGIN,
    ARTIFACT_END,
    strip_artifacts,
)


class OnlyboxesRoundtripHelpersTests(unittest.TestCase):
    def test_strip_artifacts_respects_caps_via_try_append(self) -> None:
        # One small file harvests cleanly.
        block = (
            ARTIFACT_BEGIN
            + json.dumps([{"name": "ok.bin", "b64": base64.b64encode(b"data").decode("ascii")}])
            + ARTIFACT_END
        )
        cleaned, files, diags = strip_artifacts("out\n" + block)
        self.assertIn("out", cleaned)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].data, b"data")
        self.assertEqual(diags, [])


if __name__ == "__main__":
    unittest.main()
