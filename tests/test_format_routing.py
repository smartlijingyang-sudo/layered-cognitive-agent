"""Tests for MIME/format → skill routing (ADR-0051 Phase 2 / ADR-0054)."""

from __future__ import annotations

from lca.layer0_infra.skills.bundled import OFFICECLI_SKILL_ID
from lca.layer0_infra.skills.format_routing import (
    enrich_inspect_profile,
    format_suggested_skills_prompt,
    skills_for_filename,
    suggested_skills_from_profile,
)


class TestFormatRouting:
    def test_pdf_filename_maps_to_pdf_skill(self) -> None:
        assert "anthropics-skills-pdf" in skills_for_filename("report.pdf")

    def test_doc_maps_to_officecli_first(self) -> None:
        skills = skills_for_filename("legacy.doc")
        assert skills[0] == OFFICECLI_SKILL_ID
        assert "anthropics-skills-docx" in skills

    def test_xlsx_maps_to_officecli(self) -> None:
        skills = skills_for_filename("data.xlsx")
        assert skills[0] == OFFICECLI_SKILL_ID

    def test_pptx_maps_to_officecli(self) -> None:
        skills = skills_for_filename("deck.pptx")
        assert skills[0] == OFFICECLI_SKILL_ID
        assert "anthropics-skills-pptx" in skills

    def test_enrich_inspect_profile_adds_suggested_skills(self) -> None:
        profile = {
            "profiles": {
                "a.pdf": {"type": "pdf", "mime": "application/pdf"},
            }
        }
        enriched = enrich_inspect_profile(profile)
        entry = enriched["profiles"]["a.pdf"]
        assert "anthropics-skills-pdf" in entry["suggested_skills"]

    def test_suggested_skills_prompt_lists_officecli_for_docx(self) -> None:
        profile = enrich_inspect_profile(
            {
                "profiles": {
                    "x.docx": {
                        "type": "docx",
                        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    }
                }
            }
        )
        prompt = format_suggested_skills_prompt(profile)
        assert OFFICECLI_SKILL_ID in prompt
        assert suggested_skills_from_profile(profile)[0] == OFFICECLI_SKILL_ID
