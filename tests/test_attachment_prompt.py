"""Attachment prompt SSOT — staging paths must match agent instructions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.attachment import (
    FileStoreAttachmentIdentity,
    format_machine_uploaded_files_prompt,
    format_sandbox_uploaded_files_prompt,
    reset_attachment_settings_for_tests,
    sandbox_attachment_path,
)
from lca.infrastructure.attachment.layout import AttachmentLayout
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.plane.resolve import PlaneBindings
from lca.infrastructure.plane.scope import plane_bindings_scope
from lca.infrastructure.sandbox.surface import skill_preamble
from lca.infrastructure.tools.run_attachment_scope import run_attachment_scope
from lca.infrastructure.tools.run_finalizer import run_id_scope


class TestAttachmentPrompt(unittest.TestCase):
    def setUp(self) -> None:
        reset_attachment_settings_for_tests()
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(root=Path(self._tmp.name))
        self.identity = FileStoreAttachmentIdentity(self.store)
        self.addCleanup(self._tmp.cleanup)

    def test_machine_prompt_lists_same_path_as_stage_payload(self) -> None:
        meta = self.store.put(
            data=b"pptx", name="deck.pptx", mime_type="application/vnd.ms-powerpoint"
        )
        run_id = "run_abc"
        payload = self.identity.stage_payload(run_id, (meta.attachment_id,))
        staged_rel = next(iter(payload))
        prompt = format_machine_uploaded_files_prompt(
            "/home/sandbox-user",
            run_id,
            (meta.attachment_id,),
            self.store,
        )
        layout = AttachmentLayout()
        staged_abs = layout.absolute_file("/home/sandbox-user", run_id, "deck.pptx")
        self.assertIn(staged_abs, prompt)
        self.assertTrue(staged_rel.endswith("deck.pptx"))
        self.assertIn("staged copies", prompt)

    def test_sandbox_prompt_matches_guest_attachment_path(self) -> None:
        meta = self.store.put(data=b"hello", name="data.csv", mime_type="text/csv")
        prompt = format_sandbox_uploaded_files_prompt(self.store, (meta.attachment_id,))
        self.assertIn(sandbox_attachment_path("data.csv"), prompt)
        self.assertIn("pre-loaded and ready to use", prompt)

    def test_skill_preamble_injects_staged_paths_when_scoped(self) -> None:
        meta = self.store.put(
            data=b"pptx", name="deck.pptx", mime_type="application/vnd.ms-powerpoint"
        )
        plane = PlaneRef(
            id="dev-1",
            label="box",
            kind=PlaneKind.MACHINE,
            root="/home/sandbox-user",
            outputs_dir="/home/sandbox-user/outputs",
        )
        with (
            plane_bindings_scope(PlaneBindings(primary=plane)),
            run_id_scope("run_skill"),
            run_attachment_scope([meta.attachment_id]),
        ):
            preamble = skill_preamble(self.store)
        self.assertIn("/home/sandbox-user/.lca/inbox/run_skill/deck.pptx", preamble)
        self.assertIn("exact paths", preamble)


if __name__ == "__main__":
    unittest.main()
