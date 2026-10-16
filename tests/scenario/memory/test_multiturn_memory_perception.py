"""下一轮提示词里，模型实际能看见的用户记忆和自我记忆。

写侧走生产捕获（``record_task_episode`` 与 ``record_turn_trail``），提升走
``run_dream``。读侧走提示词分段，不走假提取器。身份和偏好从 CONTEXT 拆到
``USER_PROFILE``，工具情景留在 CONTEXT。这是多轮之间不重放原文时，模型能
感知到的全部记忆。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.cognition.memory.daytime import record_task_episode, record_turn_trail
from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.dream import run_dream
from lca.infrastructure.tools.assistant.memory_tools import MemorySearchTool
from lca.plugins.assistant.profile.profile import render_user_profile
from lca.plugins.prompts.sections.context import ContextSection, UserProfileSection
from lca.plugins.prompts.sections.role import RoleSection

_T0 = 1_700_000_000_000
_ROLE = RoleProfile(
    role="小架",
    goal="架构顾问",
    backstory="系统架构专家",
    tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
)


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "asst"
    for sub in ("people", "groups", "episodes"):
        (home / "memory" / sub).mkdir(parents=True)
    return home


def _speak(home: Path, text: str, *, trace: str, now_ms: int) -> None:
    state = AgentState(trace_id=trace, task=text, budget=Budget())
    runtime = {"assistant_home_path": str(home)}
    record_task_episode(runtime, state, now_ms=now_ms)
    record_turn_trail(runtime, state, now_ms=now_ms)


def _dream(home: Path, now_ms: int) -> None:
    """``parse_trail`` 用本次 dream 的时钟给流水行盖戳，所以它晚于捕获时刻。"""

    def backfill(assistant_id: str, records: list) -> None:
        del assistant_id
        (home / "USER.md").write_text(render_user_profile(records), encoding="utf-8")

    run_dream(home, now_ms=now_ms, backfill=backfill, render=render_user_profile)


async def _prompt(home: Path, ask: str) -> tuple[str, str, str]:
    records = await AssistantMemory(home).retrieve(query=ask)
    manifest = None
    if records:
        manifest = ContextManifest(
            items=(
                ContextItem(
                    kind="memory",
                    payload=list(records),
                    provenance="memory.retrieve",
                ),
            )
        )
    kwargs = {
        "role_profile": _ROLE,
        "task": ask,
        "awareness": None,
        "manifest": manifest,
        "tools": (),
        "activated_skills": (),
    }
    profile = UserProfileSection().render(**kwargs)
    context = ContextSection().render(**kwargs)
    role = RoleSection().render(role_profile=_ROLE, tools=())
    return profile.text, context.text, role.text


async def _search(home: Path, query: str) -> list[str]:
    observed = await MemorySearchTool(memory=AssistantMemory(home)).execute(
        {"query": query, "limit": 10}
    )
    rows = (observed.payload or {}).get("records") or []
    return [str(row.get("content") or "") for row in rows]


async def _act(home: Path, *, task: str, tool: str, output: str, trace: str) -> None:
    state = AgentState(trace_id=trace, task=task, step=1, budget=Budget())
    observation = Observation(
        observation_id=f"obs_{trace}",
        success=True,
        payload={"tool": tool, "output": output},
    )
    reflection = Reflection(
        reflection_id=f"refl_{trace}",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={},
    )
    await AssistantMemory(home).update(state, observation, reflection)


@pytest.mark.asyncio
async def test_explicit_name_stays_out_of_the_prompt_until_dream(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "我叫李超", trace="t1", now_ms=_T0)

    profile, _context, role = await _prompt(home, "他是谁")

    assert profile == ""
    assert role == "ROLE: 小架"
    assert all("李超" not in hit for hit in await _search(home, "他是谁"))
    assert any("我叫李超" in hit for hit in await _search(home, "李超"))


@pytest.mark.asyncio
async def test_promoted_name_is_in_the_profile_for_an_unrelated_question(
    tmp_path: Path,
) -> None:
    home = _home(tmp_path)
    _speak(home, "我叫李超", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)

    profile, context, role = await _prompt(home, "他是谁")

    assert profile == "USER_PROFILE: 身份：用户身份：李超"
    assert "李超" not in context
    assert role == "ROLE: 小架"


@pytest.mark.asyncio
async def test_role_and_corrected_name_both_survive_as_user_not_self(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "我是架构师", trace="t1", now_ms=_T0)
    _speak(home, "我叫李超", trace="t2", now_ms=_T0 + 60_000)
    _speak(home, "我叫王明", trace="t3", now_ms=_T0 + 120_000)
    _dream(home, _T0 + 3_600_000)

    profile, _context, role = await _prompt(home, "介绍一下我")

    assert "用户身份：架构师" in profile
    assert "用户身份：王明" in profile
    assert "李超" not in profile
    assert role == "ROLE: 小架"


@pytest.mark.asyncio
async def test_assistant_name_in_the_same_sentence_is_not_the_users(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "你叫小架，我叫李超", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(home, "我们分别是谁")

    assert profile == "USER_PROFILE: 身份：用户身份：李超"
    assert "小架" not in profile


@pytest.mark.asyncio
async def test_second_name_in_the_same_sentence_is_dropped(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "我叫李超，叫我老李", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(home, "我叫什么")

    assert "李超" in profile
    assert "老李" not in profile


@pytest.mark.asyncio
async def test_negated_role_never_becomes_the_user_profile(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "我是不是架构师", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(home, "我是做什么的")

    assert "架构师" not in profile
    assert "不是" not in profile


@pytest.mark.asyncio
async def test_negated_style_keeps_its_polarity_in_the_profile(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "记住不要啰嗦", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(home, "你该怎么回复")

    assert "不要" in profile
    assert "用户偏好：啰嗦" not in profile


@pytest.mark.asyncio
async def test_two_phrasings_of_one_style_enter_the_profile(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "别那么啰嗦", trace="t1", now_ms=_T0)
    _speak(home, "别再啰嗦", trace="t2", now_ms=_T0 + 60_000)
    _dream(home, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(home, "随便聊聊")

    assert "啰嗦" in profile


@pytest.mark.asyncio
async def test_tool_action_is_self_context_and_not_a_user_fact(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "我叫李超", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)
    await _act(
        home,
        task="检查仓库",
        tool="run_command",
        output="git status: clean",
        trace="t2",
    )

    profile, context, _role = await _prompt(home, "你刚才做了什么")

    assert profile == "USER_PROFILE: 身份：用户身份：李超"
    assert "run_command" in context
    assert "李超" not in context
    assert "run_command" not in profile


@pytest.mark.asyncio
async def test_another_home_cannot_see_this_users_name(tmp_path: Path) -> None:
    mine = _home(tmp_path)
    other = _home(tmp_path / "other")
    _speak(mine, "我叫李超", trace="t1", now_ms=_T0)
    _dream(mine, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(other, "他是谁")

    assert profile == ""
    assert all("李超" not in hit for hit in await _search(other, "李超"))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "流水的 source_trace_id 是内容摘要。同一句说两遍只算一次观察，"
        "到不了 recurrence 2，隐式偏好进不了画像。"
    ),
)
@pytest.mark.asyncio
async def test_repeating_one_sentence_twice_puts_it_in_the_profile(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "别那么啰嗦", trace="t1", now_ms=_T0)
    _speak(home, "别那么啰嗦", trace="t2", now_ms=_T0 + 60_000)
    _dream(home, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(home, "随便聊聊")

    assert "啰嗦" in profile


@pytest.mark.xfail(
    strict=True,
    reason="闭合模板和流水都没有遗忘。第二次 dream 不会退役已经提升的姓名。",
)
@pytest.mark.asyncio
async def test_forget_utterance_removes_the_name_from_the_next_prompt(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "我叫李超", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)
    _speak(home, "忘掉我的名字", trace="t2", now_ms=_T0 + 60_000)
    _dream(home, _T0 + 7_200_000)

    profile, _context, _role = await _prompt(home, "我叫什么")

    assert "李超" not in profile


@pytest.mark.xfail(
    strict=True,
    reason="身份模板只认「我是」和「我叫」。英文自我介绍不会提升进画像。",
)
@pytest.mark.asyncio
async def test_english_name_is_in_the_profile_after_dream(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "My name is Lee", trace="t1", now_ms=_T0)
    _dream(home, _T0 + 3_600_000)

    profile, _context, _role = await _prompt(home, "他是谁")

    assert "Lee" in profile


@pytest.mark.xfail(
    strict=True,
    reason=(
        "AssistantMemory.update 不保存回复正文。没有工具调用时只写一条 step 摘要到 working，"
        "而注入不读 working。下一轮提示词看不到自己说过的话。"
    ),
)
@pytest.mark.asyncio
async def test_previous_reply_is_in_the_next_prompt(tmp_path: Path) -> None:
    home = _home(tmp_path)
    state = AgentState(trace_id="t1", task="写周报", step=1, budget=Budget())
    observation = Observation(
        observation_id="obs_reply",
        success=True,
        payload={"text": "周报已经写好了，共三节。"},
    )
    reflection = Reflection(
        reflection_id="refl_reply",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={},
    )
    await AssistantMemory(home).update(state, observation, reflection)

    profile, context, _role = await _prompt(home, "你刚才说了什么")

    assert "周报已经写好了" in f"{profile}\n{context}"


@pytest.mark.xfail(
    strict=True,
    reason="检索式是每个汉字的 OR。问句里的「我」会把其他含「我」的流水行一起带回。",
)
@pytest.mark.asyncio
async def test_recall_question_does_not_drag_in_an_unrelated_line(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _speak(home, "我叫李超", trace="t1", now_ms=_T0)
    _speak(home, "我喜欢猫", trace="t2", now_ms=_T0 + 60_000)

    hits = await _search(home, "你还记得我吗")

    assert all("猫" not in hit for hit in hits)
