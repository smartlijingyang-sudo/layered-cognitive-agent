"""Contract tests: avatar generation prompt carries user_request verbatim (todo-27 Phase 4).

ADR-0271 C3 requires the user's original request text to be passed through to the
image pipeline and the assembled prompt to be auditable (``prompt_used``). These
tests pin that ``_build_prompt`` places ``user_request`` verbatim at the head of
the prompt and that every candidate of one generation round shares the identical
prompt (one generation decision, not per-candidate drift).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import pytest

from lca.contracts.models.avatar import (
    AvatarState,
    AvatarUpdatedEvent,
    AvatarVariant,
)
from lca.plugins.avatar.service import AvatarService

AvatarSize = Literal["original", "small", "medium", "large"]


class _FakeProvider:
    async def generate_image(
        self, prompt: str, reference_image_bytes: bytes | None = None
    ) -> bytes:
        return b"img-bytes"

    async def create_video(self, image_bytes: bytes) -> str:
        return "task-1"

    async def get_video(self, task_id: str):  # pragma: no cover - unused here
        raise AssertionError


class _FakeStore:
    def __init__(self) -> None:
        self.state = AvatarState(
            assistant_id="asst_1",
            active=None,
            candidates=[],
            updated_at=datetime(2026, 10, 3, tzinfo=UTC),
        )

    def load_state(self, assistant_id: str) -> AvatarState:
        return self.state

    def save_state(self, state: AvatarState) -> None:
        self.state = state

    def write_image(
        self, assistant_id: str, candidate_id: str, size: str, data: bytes
    ) -> AvatarVariant:
        return AvatarVariant(
            size=cast("AvatarSize", size),
            file_path=f"candidates/{candidate_id}/{size}.png",
            url=f"/files/{candidate_id}/{size}.png",
            width=512,
            height=512,
        )

    def publish(self, assistant_id: str, event: AvatarUpdatedEvent) -> None:
        pass


def _service(summarizer=None) -> AvatarService:
    return AvatarService(
        store=_FakeStore(),
        provider=_FakeProvider(),
        summarizer=summarizer or (lambda identity: "traits"),
        publisher=_FakeStore(),
        home_resolver=lambda assistant_id: Path("/nonexistent-avatar-home"),
    )


@pytest.mark.asyncio
async def test_create_prompt_starts_with_user_request_verbatim() -> None:
    svc = _service()
    user_request = "戴红色围巾的卡通狐狸,赛博朋克风,不要改我的措辞"
    candidates = await svc.create("asst_1", user_request)
    assert len(candidates) > 0
    for candidate in candidates:
        assert candidate.prompt.startswith(user_request), candidate.prompt


@pytest.mark.asyncio
async def test_all_candidates_of_one_round_share_identical_prompt() -> None:
    svc = _service()
    candidates = await svc.create("asst_1", "一只宇航员猫")
    prompts = {c.prompt for c in candidates}
    assert len(prompts) == 1


@pytest.mark.asyncio
async def test_prompt_carries_identity_traits_section() -> None:
    svc = _service(summarizer=lambda identity: "brave, curious")
    (candidate,) = (await svc.create("asst_1", "一只猫"))[:1]
    assert "brave, curious" in candidate.prompt


@pytest.mark.asyncio
async def test_prompt_verbatim_even_when_traits_empty() -> None:
    svc = _service(summarizer=lambda identity: "")
    user_request = "极简线条画,白色背景"
    (candidate,) = (await svc.create("asst_1", user_request))[:1]
    assert candidate.prompt.startswith(user_request)


@pytest.mark.asyncio
async def test_edit_prompt_also_carries_user_request_verbatim() -> None:
    svc = _service()
    user_request = "把背景换成夜空,保留原构图"
    result = await svc.edit("asst_1", user_request)
    assert isinstance(result, list)
    for candidate in result:
        assert candidate.prompt.startswith(user_request), candidate.prompt


def test_service_has_zero_hardcoded_figures() -> None:
    """AST 守卫：断言 service.py 绝对不存在任何 _KNOWN_FIGURE_MAP 或写死人物名单。"""
    import ast

    service_path = Path(__file__).resolve().parents[3] / "lca" / "plugins" / "avatar" / "service.py"
    tree = ast.parse(service_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in (
            "_KNOWN_FIGURE_MAP",
            "FIGURE_MAP",
            "KNOWN_FIGURES",
        ):
            pytest.fail(f"Found forbidden hardcoded figure identifier in service.py: {node.id}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "西格蒙德·弗洛伊德" not in node.value, "Found hardcoded figure Freud in service.py"


@pytest.mark.parametrize(
    ("raw_input", "expected_subject"),
    [
        ("我想修改你的形象和头像，改成：爱因斯坦", "爱因斯坦"),
        ("请帮我换成一个赛博朋克猫", "赛博朋克猫"),
        ("把头像改成：鲁迅", "鲁迅"),
        ("我想修改你的形象和头像，改成：弗洛伊德", "弗洛伊德"),
        ("达芬奇", "达芬奇"),
    ],
)
@pytest.mark.asyncio
async def test_create_prompt_generically_expands_arbitrary_figures_and_styles(
    raw_input: str, expected_subject: str
) -> None:
    svc = _service()
    candidates = await svc.create("asst_1", raw_input)
    assert len(candidates) > 0
    prompt = candidates[0].prompt
    assert prompt.startswith(raw_input)
    assert "Visual focus:" in prompt
    assert f"Close-up avatar portrait of {expected_subject}" in prompt


@pytest.mark.asyncio
async def test_create_prompt_with_custom_expander() -> None:
    class _CustomExpander:
        async def expand(self, user_request: str) -> str:
            return f"Custom stylized {user_request}"

    svc = AvatarService(
        store=_FakeStore(),
        provider=_FakeProvider(),
        summarizer=lambda id: "",
        publisher=_FakeStore(),
        home_resolver=lambda id: Path("/nonexistent-avatar-home"),
        expander=_CustomExpander(),
    )
    candidates = await svc.create("asst_1", "极客猫咪")
    assert len(candidates) > 0
    prompt = candidates[0].prompt
    assert "Visual focus: Custom stylized 极客猫咪" in prompt


@pytest.mark.asyncio
async def test_create_prompt_with_explicit_visual_prompt() -> None:
    svc = _service()
    user_request = "换个头像"
    visual_prompt = "Cyberpunk neon fox portrait"
    candidates = await svc.create("asst_1", user_request, visual_prompt=visual_prompt)
    assert len(candidates) > 0
    prompt = candidates[0].prompt
    assert prompt.startswith(user_request)
    assert "Cyberpunk neon fox portrait" in prompt
