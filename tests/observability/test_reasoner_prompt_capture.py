"""ADR-0175: ``StdReasonerPromptCapture`` writes the real brain prompt.

Plus ContextVar binding round-trip test (Reasoner → LLM adapter).
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.cognition.prompt_assembly import (
    PromptTrace,
    SectionTrace,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
    bind_current_reasoner_prompt,
    get_current_reasoner_prompt,
    reset_current_reasoner_prompt,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_capture import (
    StdReasonerPromptCapture,
)


def _trace() -> PromptTrace:
    return PromptTrace(
        template_id="react_prompt",
        variant="react",
        selector_decision_path="profile_default",
        sections=(
            SectionTrace(
                name="role",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=False,
                text_chars=12,
            ),
            SectionTrace(
                name="goal",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=False,
                text_chars=8,
            ),
        ),
        total_chars=20,
        activated_skill_ids=("skill.foo", "skill.bar"),
        tools_count=3,
        available_skills_count=5,
        system_prompt_text="<ROLE>x</ROLE>\n<GOAL>y</GOAL>",
    )


def test_capture_writes_two_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "traces" / "runs" / "rid"
    run_dir.mkdir(parents=True)
    capture = StdReasonerPromptCapture(run_dir=run_dir)
    artifact = capture.capture(step_id="step-001", trace=_trace())

    sp = run_dir / "model_visible" / "step-001" / "system_prompt.json"
    sec = run_dir / "model_visible" / "step-001" / "system_prompt_sections.json"
    assert sp.exists(), "system_prompt.json must be written"
    assert sec.exists(), "system_prompt_sections.json must be written"
    assert artifact.step_id == "step-001"
    assert artifact.system_prompt_path.endswith("system_prompt.json")
    assert artifact.system_prompt_sections_path.endswith("system_prompt_sections.json")
    assert artifact.system_prompt_digest.startswith("sha256:")

    payload = json.loads(sp.read_text(encoding="utf-8"))
    assert payload["step_id"] == "step-001"
    assert payload["template_id"] == "react_prompt"
    assert payload["selector_decision_path"] == "profile_default"
    assert "<ROLE>x</ROLE>" in payload["body"]

    sec_payload = json.loads(sec.read_text(encoding="utf-8"))
    assert sec_payload["activated_skill_ids"] == ["skill.foo", "skill.bar"]
    assert sec_payload["tools_count"] == 3
    assert sec_payload["available_skills_count"] == 5
    assert len(sec_payload["sections"]) == 2
    assert sec_payload["sections"][0]["name"] == "role"


def test_context_var_round_trip() -> None:
    """Reasoner binds, LLM adapter reads, reset clears."""
    from lca.contracts.observability.reasoner_prompt_capture import (
        ReasonerPromptArtifact,
    )

    # Sanity: ReasonerPromptArtifact signature unchanged (it has no body field).
    _ = ReasonerPromptArtifact(
        step_id="x",
        system_prompt_path="a",
        system_prompt_sections_path="b",
        system_prompt_digest="sha256:0",
    )

    token = bind_current_reasoner_prompt(
        type(get_current_reasoner_prompt())  # type: ignore[arg-type]
        if False
        else _make_current_prompt()
    )
    try:
        cp = get_current_reasoner_prompt()
        assert cp is not None
        assert cp.template_id == "react_prompt"
        assert cp.selector_decision_path == "profile_default"
        assert "<ROLE>x</ROLE>" in cp.system_prompt_text
    finally:
        reset_current_reasoner_prompt(token)

    assert get_current_reasoner_prompt() is None


def _make_current_prompt():
    from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
        CurrentReasonerPrompt,
    )

    return CurrentReasonerPrompt(
        step_id="step-001",
        template_id="react_prompt",
        selector_decision_path="profile_default",
        system_prompt_text="<ROLE>x</ROLE>\n<GOAL>y</GOAL>",
    )
