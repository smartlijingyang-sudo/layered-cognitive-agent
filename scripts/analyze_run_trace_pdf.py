"""Generate a chain-analysis PDF for the latest (or specified) run trace."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#4a4a4a")
RULE = colors.HexColor("#d0d0d0")
HEAD_BG = colors.HexColor("#1f2937")
HEAD_FG = colors.white
ROW_ALT = colors.HexColor("#f4f5f7")
PILL_RED = colors.HexColor("#fee2e2")
PILL_AMBER = colors.HexColor("#fef3c7")
PILL_GREEN = colors.HexColor("#dcfce7")


@dataclass
class ToolRound:
    seq_start: int
    tool_name: str
    invocation_id: str = ""
    description: str = ""
    ok: bool | None = None
    error: str = ""
    plane_kind: str = ""


@dataclass
class LlmRound:
    index: int
    seq_start: int
    seq_end: int = 0
    reasoning_preview: str = ""
    tools: list[ToolRound] = field(default_factory=list)


@dataclass
class RunAnalysis:
    run_id: str
    trace_id: str
    jsonl_path: Path
    objective_preview: str
    strategy: str
    scope_run_id: str
    agent_finished_status: str
    agent_finished_error: str
    agent_finished_output: str
    steps: int
    doctor_status: str
    doctor_summary: str
    doctor_broken_hop: str | None
    event_counts: dict[str, int]
    last_seq: int
    llm_rounds: list[LlmRound]
    insights: list[str]
    duration_hint: str = ""


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s: dict[str, ParagraphStyle] = {}
    s["cover_kicker"] = ParagraphStyle(
        "cover_kicker",
        parent=base["Normal"],
        fontName="STSong-Light",
        fontSize=10,
        textColor=colors.HexColor("#6b7280"),
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    s["cover_title"] = ParagraphStyle(
        "cover_title",
        parent=base["Title"],
        fontName="STSong-Light",
        fontSize=20,
        leading=28,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    s["h1"] = ParagraphStyle(
        "h1",
        parent=base["Heading1"],
        fontName="STSong-Light",
        fontSize=14,
        leading=20,
        textColor=INK,
        spaceBefore=16,
        spaceAfter=8,
    )
    s["h2"] = ParagraphStyle(
        "h2",
        parent=base["Heading2"],
        fontName="STSong-Light",
        fontSize=12,
        leading=17,
        textColor=INK,
        spaceBefore=12,
        spaceAfter=6,
    )
    s["body"] = ParagraphStyle(
        "body",
        parent=base["Normal"],
        fontName="STSong-Light",
        fontSize=9.5,
        leading=15,
        textColor=INK,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    s["bullet"] = ParagraphStyle(
        "bullet",
        parent=s["body"],
        leftIndent=12,
        alignment=TA_LEFT,
        spaceAfter=3,
    )
    s["cell"] = ParagraphStyle(
        "cell",
        parent=base["Normal"],
        fontName="STSong-Light",
        fontSize=8,
        leading=12,
        textColor=INK,
    )
    s["cell_c"] = ParagraphStyle(
        "cell_c",
        parent=s["cell"],
        alignment=TA_CENTER,
    )
    s["mono"] = ParagraphStyle(
        "mono",
        parent=base["Code"],
        fontName="Courier",
        fontSize=7.5,
        leading=10.5,
        textColor=INK,
        backColor=colors.HexColor("#f8fafc"),
        borderPadding=4,
        leftIndent=4,
        rightIndent=4,
    )
    s["caption"] = ParagraphStyle(
        "caption",
        parent=base["Normal"],
        fontName="STSong-Light",
        fontSize=8,
        leading=11,
        textColor=MUTED,
        spaceBefore=2,
        spaceAfter=10,
    )
    s["callout"] = ParagraphStyle(
        "callout",
        parent=s["body"],
        backColor=PILL_AMBER,
        borderPadding=8,
        leftIndent=6,
        rightIndent=6,
        spaceBefore=4,
        spaceAfter=10,
    )
    return s


def P(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def cell(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text.replace("\n", "<br/>"), style)


def pill(text: str, kind: str, style: ParagraphStyle) -> Paragraph:
    colors_map = {
        "ok": ("#14532d", "#dcfce7"),
        "bad": ("#9b1c1c", "#fee2e2"),
        "warn": ("#92400e", "#fef3c7"),
        "info": ("#1e3a8a", "#e0e7ff"),
    }
    fg, bg = colors_map[kind]
    return Paragraph(
        f'<font color="{fg}"><b>{text}</b></font>',
        ParagraphStyle(
            f"pill_{kind}_{id(text)}",
            parent=style,
            alignment=TA_CENTER,
            backColor=colors.HexColor(bg),
        ),
    )


def table(rows: list[list], col_widths: list[float], header: bool = True) -> Table:
    grid = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, RULE),
    ]
    if header:
        cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), HEAD_FG),
        ]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                cmds.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))
    grid.setStyle(TableStyle(cmds))
    return grid


def latest_run_jsonl(runs_dir: Path) -> Path:
    candidates = sorted(runs_dir.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no run jsonl under {runs_dir}")
    return candidates[0]


def analyze_run(jsonl_path: Path) -> RunAnalysis:
    counts: Counter[str] = Counter()
    last_seq = 0
    started: dict[str, ToolRound] = {}
    llm_rounds: list[LlmRound] = []
    current: LlmRound | None = None
    llm_index = 0

    objective_preview = ""
    strategy = ""
    scope_run_id = ""
    trace_id = ""
    agent_finished_status = ""
    agent_finished_error = ""
    agent_finished_output = ""
    steps = 0
    insights: list[str] = []
    duration_hint = ""

    for raw in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        event_type = str(record.get("event_type") or "")
        counts[event_type] += 1
        seq = int(record.get("seq") or 0)
        last_seq = max(last_seq, seq)
        event = record.get("event") if isinstance(record.get("event"), dict) else {}
        scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}

        if event_type == "AgentRunStarted":
            objective_preview = str(event.get("objective_preview") or event.get("objective") or "")[:300]
            strategy = str(event.get("strategy_key") or "")
            scope_run_id = str(scope.get("run_id") or "")
            trace_id = str(scope.get("trace_id") or "")

        if event_type == "LlmCallStarted":
            llm_index += 1
            current = LlmRound(index=llm_index, seq_start=seq)

        if event_type == "ReasoningCompleted" and current is not None:
            current.reasoning_preview = str(event.get("content_preview") or "")[:220]

        if event_type == "ToolStarted":
            ps = event.get("plugin_state") if isinstance(event.get("plugin_state"), dict) else {}
            plane = ps.get("plane") if isinstance(ps.get("plane"), dict) else {}
            tr = ToolRound(
                seq_start=seq,
                tool_name=str(event.get("tool_name") or ""),
                invocation_id=str(event.get("invocation_id") or ""),
                description=str(ps.get("description") or ps.get("command") or "")[:120],
                plane_kind=str(plane.get("kind") or ""),
            )
            started[tr.invocation_id] = tr
            if current is not None:
                current.tools.append(tr)

        if event_type == "ToolInvoked":
            inv = str(event.get("invocation_id") or "")
            tr = started.get(inv)
            if tr is not None:
                tr.ok = bool(event.get("ok"))
                tr.error = str(event.get("error") or "")[:200]

        if event_type == "StepCompleted" and current is not None:
            current.seq_end = seq
            llm_rounds.append(current)
            current = None

        if event_type == "AgentRunFinished":
            agent_finished_status = str(event.get("status") or "")
            agent_finished_error = str(event.get("error") or "")
            agent_finished_output = str(event.get("output_text") or "")[:200]
            steps = int(event.get("steps") or 0)

        if event_type == "RunInsight":
            summary = str(event.get("summary") or "")
            if summary:
                insights.append(summary)
            detail = str(event.get("detail") or "")
            if "ms" in detail or "tokens" in summary.lower():
                duration_hint = summary if "ms" in summary else detail

    doctor_path = jsonl_path.with_suffix(".doctor.json")
    doctor_status = ""
    doctor_summary = ""
    doctor_broken_hop = None
    if doctor_path.is_file():
        doctor = json.loads(doctor_path.read_text(encoding="utf-8"))
        doctor_status = str(doctor.get("status") or "")
        doctor_summary = str(doctor.get("summary") or "")
        doctor_broken_hop = doctor.get("broken_hop")

    return RunAnalysis(
        run_id=jsonl_path.stem,
        trace_id=trace_id,
        jsonl_path=jsonl_path,
        objective_preview=objective_preview,
        strategy=strategy,
        scope_run_id=scope_run_id,
        agent_finished_status=agent_finished_status,
        agent_finished_error=agent_finished_error,
        agent_finished_output=agent_finished_output,
        steps=steps,
        doctor_status=doctor_status,
        doctor_summary=doctor_summary,
        doctor_broken_hop=doctor_broken_hop,
        event_counts=dict(counts),
        last_seq=last_seq,
        llm_rounds=llm_rounds,
        insights=insights,
        duration_hint=duration_hint,
    )


def build_pdf(analysis: RunAnalysis, out_path: Path) -> None:
    s = styles()
    story: list = []
    usable = A4[0] - 36 * mm
    id_match = analysis.run_id == analysis.scope_run_id
    journal_failed = analysis.agent_finished_status == "failed"
    doctor_ok = analysis.doctor_summary == "ok"

    story.append(P("INTERNAL ENGINEERING MEMO | 2026-08-14", s["cover_kicker"]))
    story.append(P(f"Run 链路深度分析 — {analysis.run_id}", s["cover_title"]))
    story.append(
        P(
            f"样本：<b>{analysis.jsonl_path}</b>。"
            f"用户任务：{analysis.objective_preview}…"
            f"Journal 终态 <b>{analysis.agent_finished_status or 'unknown'}</b>；"
            f"Doctor 报告 <b>{analysis.doctor_summary or 'n/a'}</b>。"
            "下文按 hop 与 LLM 轮次拆解失败机制。",
            s["body"],
        )
    )

    conclusion = (
        "<b>结论（先读这一段）</b>："
        if journal_failed and doctor_ok
        else "<b>结论</b>："
    )
    if journal_failed and doctor_ok:
        conclusion += (
            "任务<b>实际失败</b>（AgentRunFinished.status=failed，无 output_text），"
            "但 Doctor / session 仍标 <b>ok/completed</b>——gateway execute_run 只要没抛异常就把 success=True，"
            "不读 result.status。这是诊断层假阳性。"
        )
    else:
        conclusion += f"Run 终态 {analysis.agent_finished_status}。"

    machine_tools = any(t.tool_name.startswith("local_") for r in analysis.llm_rounds for t in r.tools)
    sandbox_attempt = any(t.tool_name.endswith("executeCode") for r in analysis.llm_rounds for t in r.tools)
    if machine_tools:
        conclusion += (
            " 本次绑定 <b>machine/device 执行面</b>（local_* 工具），"
            "但 Agent 仍尝试 local_executeCode（sandbox-only）并在宿主机缺 reportlab、pip 离线时陷入 9 轮探测循环。"
        )
    if sandbox_attempt:
        conclusion += " executeCode 在 machine 面被硬拒绝，Agent 改用 writeFile+runCommand 绕行仍因缺依赖失败。"
    story.append(P(conclusion, s["callout"]))

    story.append(P("1. Run 元数据", s["h1"]))
    meta = [
        [
            cell("<font color='white'><b>字段</b></font>", s["cell"]),
            cell("<font color='white'><b>值</b></font>", s["cell"]),
            cell("<font color='white'><b>含义</b></font>", s["cell"]),
        ],
        [cell("jsonl / scope.run_id", s["cell"]), cell(analysis.run_id, s["cell"]), cell("文件名与 scope 一致" if id_match else "ID 分裂", s["cell"])],
        [cell("trace_id", s["cell"]), cell(analysis.trace_id, s["cell"]), cell("观测 trace", s["cell"])],
        [cell("策略", s["cell"]), cell(analysis.strategy, s["cell"]), cell(f"{analysis.steps} steps · seq 1-{analysis.last_seq}", s["cell"])],
        [cell("Journal 终态", s["cell"]), cell(analysis.agent_finished_status, s["cell"]), cell(analysis.agent_finished_error or "error 字段为空", s["cell"])],
        [cell("Doctor", s["cell"]), cell(f"{analysis.doctor_status} / {analysis.doctor_summary}", s["cell"]), cell(f"broken_hop={analysis.doctor_broken_hop}", s["cell"])],
    ]
    if analysis.duration_hint:
        meta.append([cell("耗时/成本", s["cell"]), cell(analysis.duration_hint, s["cell"]), cell("RunInsight", s["cell"])])
    story.append(table(meta, [48 * mm, 62 * mm, usable - 110 * mm]))

    story.append(P("2. LLM 轮次时间线", s["h1"]))
    tl = [
        [
            cell("<font color='white'><b>轮</b></font>", s["cell_c"]),
            cell("<font color='white'><b>seq</b></font>", s["cell_c"]),
            cell("<font color='white'><b>工具调用</b></font>", s["cell"]),
            cell("<font color='white'><b>结果</b></font>", s["cell_c"]),
        ],
    ]
    for rd in analysis.llm_rounds:
        tool_lines = []
        for t in rd.tools:
            status = "?" if t.ok is None else ("ok" if t.ok else "FAIL")
            tool_lines.append(f"{t.tool_name} [{status}] {t.description[:80]}")
        tool_text = "<br/>".join(tool_lines) if tool_lines else "（无工具）"
        any_fail = any(t.ok is False for t in rd.tools)
        tl.append(
            [
                cell(f"L{rd.index}", s["cell_c"]),
                cell(f"{rd.seq_start}-{rd.seq_end}", s["cell_c"]),
                cell(f"{tool_text}<br/><i>{rd.reasoning_preview[:160]}…</i>", s["cell"]),
                pill("失败" if any_fail else "通过", "bad" if any_fail else "ok", s["cell"]),
            ]
        )
    story.append(table(tl, [12 * mm, 18 * mm, usable - 42 * mm, 12 * mm]))

    story.append(P("3. 根因归类", s["h1"]))
    roots = [
        [
            cell("<font color='white'><b>编号</b></font>", s["cell_c"]),
            cell("<font color='white'><b>机制</b></font>", s["cell"]),
            cell("<font color='white'><b>本 Run 证据</b></font>", s["cell"]),
        ],
        [
            cell("R1", s["cell_c"]),
            cell("执行面错配", s["cell"]),
            cell(
                "AUTO/DEVICE 落到 machine 面；prompt 仍描述沙箱 CJK 字体与 reportlab。"
                "local_executeCode 直接 AttributeError: sandbox-only。"
                "宿主机仅有 pandoc/python-docx/lxml，无 reportlab/fpdf/weasyprint。",
                s["cell"],
            ),
        ],
        [
            cell("R2", s["cell_c"]),
            cell("依赖/网络", s["cell"]),
            cell(
                "pip install reportlab → No matching distribution（离线或源不可达）。"
                "writeFile 脚本正确但 runCommand 因 ModuleNotFoundError 失败。",
                s["cell"],
            ),
        ],
        [
            cell("R3", s["cell_c"]),
            cell("步数预算耗尽", s["cell"]),
            cell(
                f"9 次 LLM、{analysis.steps} steps；末轮仍在探测 python3/pip3/npm。"
                "DefaultStopRule BUDGET_EXCEEDED → TaskStatus.FAILED，无 terminal respond。",
                s["cell"],
            ),
        ],
        [
            cell("R4", s["cell_c"]),
            cell("Gateway 状态分裂", s["cell"]),
            cell(
                "Journal AgentRunFinished.status=failed；session.status=completed；Doctor summary=ok。"
                "execute_run 未检查 result.status，Doctor 未读 journal 终态。",
                s["cell"],
            ),
        ],
        [
            cell("R5", s["cell_c"]),
            cell("用户无可见答复", s["cell"]),
            cell(
                "StepTextDelta 全空；output_text 空。"
                "TerminalRespondGate 未触发（末步仍是 producer tool local_runCommand）。",
                s["cell"],
            ),
        ],
    ]
    story.append(table(roots, [12 * mm, 28 * mm, usable - 40 * mm]))

    story.append(P("4. 建议修复（按层）", s["h1"]))
    fixes = [
        [
            cell("<font color='white'><b>层</b></font>", s["cell_c"]),
            cell("<font color='white'><b>改动</b></font>", s["cell"]),
            cell("<font color='white'><b>验收</b></font>", s["cell"]),
        ],
        [
            cell("Gateway", s["cell_c"]),
            cell("execute_run：result.status != COMPLETED → success=False；Doctor 对齐 journal 终态", s["cell"]),
            cell("failed run 不再标 completed/ok", s["cell"]),
        ],
        [
            cell("Plane", s["cell_c"]),
            cell("PDF+executeCode 任务在 machine 无 reportlab 时 fallback sandbox 或前置校验", s["cell"]),
            cell("不再在 device 面尝试 sandbox-only API", s["cell"]),
        ],
        [
            cell("Prompt", s["cell_c"]),
            cell("按 bindings 注入可用工具与依赖清单（machine: pandoc；sandbox: reportlab）", s["cell"]),
            cell("Agent 首步不 activate pdf skill 后走 executeCode", s["cell"]),
        ],
        [
            cell("Runtime", s["cell_c"]),
            cell("budget exceeded 时强制 terminal respond 说明失败原因", s["cell"]),
            cell("用户至少看到「缺 reportlab / 步数用尽」", s["cell"]),
        ],
    ]
    story.append(table(fixes, [18 * mm, usable * 0.55, usable * 0.27]))

    if analysis.insights:
        story.append(P("5. RunInsight", s["h2"]))
        for item in analysis.insights:
            story.append(P(f"• {item}", s["bullet"]))

    story.append(P("附录：事件计数", s["h2"]))
    count_rows = [
        [cell("<font color='white'><b>event_type</b></font>", s["cell"]), cell("<font color='white'><b>count</b></font>", s["cell_c"])],
    ]
    for name, count in sorted(analysis.event_counts.items(), key=lambda x: (-x[1], x[0])):
        count_rows.append([cell(name, s["cell"]), cell(str(count), s["cell_c"])])
    story.append(table(count_rows, [usable * 0.7, usable * 0.3]))

    out_path.parent.mkdir(parents=True, exist_ok=True)

    def on_page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.setFont("STSong-Light", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 7 * mm, f"LCA | Run 链路分析 | {analysis.run_id}")
        canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, f"{doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Run trace analysis — {analysis.run_id}",
        author="LCA engineering",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


def main() -> None:
    runs_dir = Path("traces/runs")
    if len(sys.argv) > 1:
        run_id = sys.argv[1].removesuffix(".jsonl")
        jsonl_path = runs_dir / f"{run_id}.jsonl"
    else:
        jsonl_path = latest_run_jsonl(runs_dir)

    analysis = analyze_run(jsonl_path)
    out = Path("output") / f"run_trace_analysis_{analysis.run_id}.pdf"
    build_pdf(analysis, out)
    print(out.resolve())


if __name__ == "__main__":
    main()
