"""Shared Team-mode catalog for tests and the run_team_mode CLI."""

from __future__ import annotations

from dataclasses import dataclass

from gateway import mode_catalog
from tests.harness.scripted_llm import ScriptedLLMAdapter, multi_delegate, respond

ALL_MODES = mode_catalog.ALL_MODES
MODE_HELP = mode_catalog.MODE_HELP
MODE_HAS_LEAD = mode_catalog.MODE_HAS_LEAD


@dataclass(frozen=True)
class ModeScenario:
    """Human-facing scenario card for a team mode probe."""

    key: str
    title: str
    blurb: str
    cast: tuple[str, ...]
    plan_steps: tuple[str, ...]
    default_objective: str


# Short blurbs for interactive pickers (zh) — 与 gateway.mode_catalog 同步

_SCENARIOS: dict[str, ModeScenario] = {
    "routing": ModeScenario(
        key="routing",
        title="Routing · 主导路由委派",
        blurb="Lead 拆任务并显式 DELEGATE 给成员，再汇总。",
        cast=("Lead（主导 · mandate=routing）", "Alice（成员）", "Bob（成员）"),
        plan_steps=(
            "1. Lead 阅读目标，决定委派谁",
            "2. transport → Alice / Bob 执行子任务",
            "3. Lead 收回结果并给出最终答复",
        ),
        default_objective=(
            "你是项目 Lead。任务：评估「移动端新功能上线」的风险。"
            "必须先分别委派：Alice 做技术风险（一句话），Bob 做业务风险（一句话）；"
            "等他们返回后，你再汇总成 3 条结论。禁止自己直接答完、禁止反问。"
        ),
    ),
    "consult": ModeScenario(
        key="consult",
        title="Consult · 主导咨询后自决",
        blurb="Lead 可咨询成员，最终由 Lead 拍板。",
        cast=("Lead（主导 · mandate=consult）", "Alice（顾问）", "Bob（顾问）"),
        plan_steps=(
            "1. Lead 决定是否咨询成员",
            "2. 可选：调用 Alice / Bob 取意见",
            "3. Lead 自行给出最终决策",
        ),
        default_objective=(
            "你是决策 Lead。问题：我们是否应该本周发布灰度？"
            "请先向 Alice 和 Bob 各征求一句意见，再由你本人给出「发布/暂缓」结论和理由。"
            "禁止只反问用户。"
        ),
    ),
    "board": ModeScenario(
        key="board",
        title="Board · 全员咨询后收口",
        blurb="Lead 组织全员意见后统一收口。",
        cast=("Lead（主导 · mandate=board）", "Alice（成员）", "Bob（成员）"),
        plan_steps=(
            "1. Lead 发起 board 流程",
            "2. 全员（Alice、Bob）给出意见",
            "3. Lead 综合收口输出决议",
        ),
        default_objective=(
            "董事会场景：是否把客服机器人切换到新模型？"
            "请 Alice 给「支持」理由一句，Bob 给「风险」一句；"
            "Lead 综合后给出最终决议（通过/否决）和一句总结。禁止反问。"
        ),
    ),
    "pipeline": ModeScenario(
        key="pipeline",
        title="Pipeline · 顺序接力",
        blurb="Alice → Bob → Carol 依次处理，后一位吃前一位输出。",
        cast=("Alice（第 1 棒）", "Bob（第 2 棒）", "Carol（第 3 棒）"),
        plan_steps=(
            "1. Alice 产出初稿",
            "2. Bob 在 Alice 基础上修订",
            "3. Carol 收口成最终一句话结论",
        ),
        default_objective=(
            "流水线任务：写一条「周末大促」短信文案。"
            "Alice 先写草稿（一句），Bob 改得更有转化力（一句），"
            "Carol 输出最终可发送版本（一句）。每人只做自己那一棒。"
        ),
    ),
    "fan_out": ModeScenario(
        key="fan_out",
        title="Fan-out · 并行再合成",
        blurb="Alice / Bob / Carol 并行处理，再合成一份结果。",
        cast=("Alice", "Bob", "Carol", "（合成步骤）"),
        plan_steps=(
            "1. 并行调用 Alice / Bob / Carol",
            "2. 收集各自输出",
            "3. 合成最终答案",
        ),
        default_objective=(
            "并行调研：关于「远程办公」各给一个观点——"
            "Alice 从效率、Bob 从协作、Carol 从文化；最后合成三条要点。每人一句，禁止反问。"
        ),
    ),
    "peer_relay": ModeScenario(
        key="peer_relay",
        title="Peer Relay · 点对点接力",
        blurb="成员点对点传递，直到有人给出可结束结果。",
        cast=("Alice", "Bob"),
        plan_steps=(
            "1. 从第一位成员开始",
            "2. 点对点 relay 到下一位",
            "3. 得到可结束答复后停止",
        ),
        default_objective=(
            "接力任务：把「用户登录慢」从现象拆到可能原因。"
            "Alice 先写现象与假设（一句），Bob 在其基础上给出最可能原因（一句）。简洁，禁止反问。"
        ),
    ),
    "peer_swarm": ModeScenario(
        key="peer_swarm",
        title="Peer Swarm · 对等多轮",
        blurb="对等成员多轮互动（max_rounds 控制）。",
        cast=("Alice", "Bob"),
        plan_steps=(
            "1. 开启 swarm 多轮",
            "2. 成员轮流发言/回应",
            "3. 达到轮次上限或收敛后结束",
        ),
        default_objective=(
            "两人对等讨论：产品 slogan 候选。"
            "Alice 提一个 slogan，Bob 提改进；各一轮后给出你们共同认可的最终 slogan（一句）。禁止反问。"
        ),
    ),
    "debate": ModeScenario(
        key="debate",
        title="Debate · 多轮辩论",
        blurb="正反方辩论若干轮后收敛。",
        cast=("Alice（一方）", "Bob（另一方）"),
        plan_steps=(
            "1. 开启 debate，设定轮次",
            "2. 双方交替陈述",
            "3. 形成收敛结论或超时结束",
        ),
        default_objective=(
            "辩论题：是否应强制双因素认证。"
            "Alice 支持强制，Bob 反对强制；各陈述一句后给出一个折中建议（一句）。禁止反问。"
        ),
    ),
    "graph": ModeScenario(
        key="graph",
        title="Graph · 执行图",
        blurb="ENTRY → Alice → Bob → EXIT 固定拓扑。",
        cast=("Alice（图节点 n0）", "Bob（图节点 n1）"),
        plan_steps=(
            "1. 从图 ENTRY 进入",
            "2. 依次执行 Alice、Bob 节点",
            "3. 到达 EXIT 结束",
        ),
        default_objective=(
            "图执行任务：生成「每日站会」议程。"
            "Alice 列出 3 个议题关键词，Bob 整理成一句可宣读的议程。禁止反问。"
        ),
    ),
    "solo": ModeScenario(
        key="solo",
        title="Solo · 单 Agent",
        blurb="无 Team，单个 Agent 跑完认知循环。",
        cast=("Solo（唯一角色）",),
        plan_steps=(
            "1. on_start → perceive",
            "2. think（LLM）→ 决策",
            "3. act → reflect → complete",
        ),
        default_objective=(
            "用一句话自我介绍，并说明你理解到的任务是「solo 模式探针」。"
            "直接回答，不要反问，不要超过两句。"
        ),
    ),
}


def get_scenario(mode: str) -> ModeScenario:
    if mode not in _SCENARIOS:
        raise KeyError(f"unknown mode {mode!r}")
    return _SCENARIOS[mode]


def default_objective(mode: str) -> str:
    return get_scenario(mode).default_objective


def format_scenario_card(
    mode: str,
    *,
    track: str,
    objective: str | None = None,
    max_rounds: int | None = None,
) -> str:
    """Banner printed before a run — what scenario, who, planned steps."""
    sc = get_scenario(mode)
    obj = objective if objective is not None else sc.default_objective
    lines = [
        "╔" + "═" * 58 + "╗",
        f"║ 场景  {sc.title:<50} ║",
        f"║ 模式  {mode:<12}  track={track:<10}              ║",
        "╟" + "─" * 58 + "╢",
        f"║ 说明  {sc.blurb}",
        "║ 角色",
    ]
    for c in sc.cast:
        lines.append(f"║   · {c}")
    lines.append("║ 计划步骤（预期）")
    for step in sc.plan_steps:
        lines.append(f"║   {step}")
    if max_rounds is not None and mode in ("debate", "peer_swarm"):
        lines.append(f"║ 轮次  max_rounds={max_rounds}")
    lines.append("╟" + "─" * 58 + "╢")
    lines.append("║ 任务目标")
    # wrap objective for readability
    wrapped = _wrap_text(obj, width=54)
    for w in wrapped:
        lines.append(f"║   {w}")
    lines.append("╚" + "═" * 58 + "╝")
    return "\n".join(lines)


def _wrap_text(text: str, *, width: int) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return [""]
    rows: list[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur = f"{cur} {w}"
        else:
            rows.append(cur)
            cur = w
    rows.append(cur)
    return rows


def scripted_llm_for_mode(mode: str) -> ScriptedLLMAdapter:
    """Deterministic LLM scripts matching tests/harness/runner role names."""
    if mode in ("routing", "consult", "board"):
        return ScriptedLLMAdapter(
            {
                "Lead": [
                    multi_delegate([("Alice", "analyze"), ("Bob", "review")]),
                    respond("lead final"),
                ],
                "Alice": [respond("alice view")],
                "Bob": [respond("bob view")],
            },
            default_respond=True,
        )
    if mode == "solo":
        return ScriptedLLMAdapter({"Solo": [respond("solo done")]}, default_respond=True)
    return ScriptedLLMAdapter(
        {
            "Alice": [respond("from Alice")],
            "Bob": [respond("from Bob")],
            "Carol": [respond("from Carol")],
        },
        default_respond=True,
    )
