from __future__ import annotations

from lca.contracts.models.core.perception import ContextClass, ContextItem, ContextManifest


def test_context_manifest_separates_instruction_from_data() -> None:
    manifest = ContextManifest(
        items=(
            ContextItem(kind="memory", payload="facts", provenance="search"),
            ContextItem(
                kind="workspace_instructions",
                payload="policy",
                provenance="workspace",
                content_class=ContextClass.INSTRUCTION,
            ),
        )
    )

    assert len(manifest.by_class(ContextClass.DATA)) == 1
    assert len(manifest.by_class(ContextClass.INSTRUCTION)) == 1
