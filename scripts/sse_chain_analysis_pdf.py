"""Generate the SSE / thinking / tool-card chain analysis PDF (v2)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

OUT = Path("output/sse_thinking_toolcard_chain_analysis.pdf")

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#4a4a4a")
RULE = colors.HexColor("#d0d0d0")
HEAD_BG = colors.HexColor("#1f2937")
HEAD_FG = colors.white
ROW_ALT = colors.HexColor("#f4f5f7")
RED = colors.HexColor("#9b1c1c")
AMBER = colors.HexColor("#92400e")
GREEN = colors.HexColor("#14532d")
PILL_RED = colors.HexColor("#fee2e2")
PILL_AMBER = colors.HexColor("#fef3c7")
PILL_GREEN = colors.HexColor("#dcfce7")
PILL_BLUE = colors.HexColor("#e0e7ff")


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
    s["footer"] = ParagraphStyle(
        "footer",
        parent=base["Normal"],
        fontName="STSong-Light",
        fontSize=8,
        textColor=MUTED,
        alignment=TA_CENTER,
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


def on_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
    canvas.setFont("STSong-Light", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 7 * mm, "LCA | Run Live 链路分析 | run_e12ff4d0e987")
    canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, f"{doc.page}")
    canvas.restoreState()


def build() -> None:
    s = styles()
    story: list = []
    usable = A4[0] - 36 * mm

    story.append(P("INTERNAL ENGINEERING MEMO | 2026-08-13", s["cover_kicker"]))
    story.append(P("SSE / 深度思考 / 工具卡消失：前后端链路系统分析", s["cover_title"]))
    story.append(
        P(
            "样本：traces/runs/run_e12ff4d0e987.jsonl（用户任务：分析《App个人信息保护合规自查表.xlsx》并生成 PDF）。"
            "Doctor 报告 H2/H3 判定 ok；人眼前却看到「思考不按轮切开、上一张工具卡和执行代码被后一轮抹掉」。"
            "本文用这本 Journal 把 hop 走完，区分「管道丢事件」和「状态机覆盖」。",
            s["body"],
        )
    )
    story.append(
        P(
            "<b>结论（先读这一段）</b>：SSE 没有断、Journal 没有缺轮。"
            "三轮 LLM 的 ReasoningDelta、三轮 execute_code 的 ToolStarted/ToolInvoked 都在账本里。"
            "人看到的丢失发生在 <b>JournalTransport -> 单个 StreamingHandler -> 单条 assistant.tools / reasoning</b>："
            "原生组件按「当前这一轮」覆盖写；补丁在下一轮思考到来时还主动 new 一个 Handler，把上一轮 tools 和 thinking 清零。"
            "这和 Run Live 规格 2.5「明确不做多段 Thinking、下一轮替换本轮」一致，但和「思考应穿插在工具调用之间、历史工具卡保留」的产品预期相反。"
            "另外：第三轮 execute_code 的 plugin_state 里 <b>没有 code</b>，沙箱扫描到上次残留的「素数计算报告.pdf」，收尾文本谎称任务完成。",
            s["callout"],
        )
    )

    # 1
    story.append(P("1. 样本 Run 事实", s["h1"]))
    meta = [
        [
            cell("<font color='white'><b>字段</b></font>", s["cell"]),
            cell("<font color='white'><b>值</b></font>", s["cell"]),
            cell("<font color='white'><b>含义</b></font>", s["cell"]),
        ],
        [
            cell("jsonl 文件 / session.run_id", s["cell"]),
            cell("run_e12ff4d0e987", s["cell"]),
            cell("Gateway 开工号，/runs/{id}/live 用这个", s["cell"]),
        ],
        [
            cell("Journal scope.run_id", s["cell"]),
            cell("run_82925d98fb93", s["cell"]),
            cell("CognitiveAgent 自己 new_id('run')，与 session 分裂", s["cell"]),
        ],
        [
            cell("session.trace_id / journal.trace_id", s["cell"]),
            cell("trace_2e5c7e6d79e7 / trace_b30b8edb8bd7", s["cell"]),
            cell("两套观测身份，Langfuse 对不上号", s["cell"]),
        ],
        [
            cell("模型 / 策略", s["cell"]),
            cell("qwen3.7-plus - solo", s["cell"]),
            cell("3 次 LLM，耗时约 313s，tokens 50532 in / 17086 out", s["cell"]),
        ],
        [
            cell("Doctor", s["cell"]),
            cell("broken_hop=null，factory.ok=true", s["cell"]),
            cell("H4/H5 服务端看不见浏览器；空 code 也不算 missing_plugin_state", s["cell"]),
        ],
        [
            cell("seq", s["cell"]),
            cell("1-181 连续，无 gap", s["cell"]),
            cell("不是 LiveTail 丢帧，也不是 Last-Event-ID 错位", s["cell"]),
        ],
    ]
    story.append(table(meta, [48 * mm, 62 * mm, usable - 110 * mm]))
    story.append(P("表 1 - 两套 ID 同时存在。文件名对得上 HTTP，账本对不上文件名。", s["caption"]))

    story.append(P("账本时间线（delta 已折叠）", s["h2"]))
    tl = [
        [
            cell("<font color='white'><b>轮次</b></font>", s["cell_c"]),
            cell("<font color='white'><b>seq</b></font>", s["cell_c"]),
            cell("<font color='white'><b>Journal 事实</b></font>", s["cell"]),
            cell("<font color='white'><b>人眼前实际</b></font>", s["cell"]),
        ],
        [
            cell("L1", s["cell_c"]),
            cell("2-35", s["cell_c"]),
            cell(
                "Reasoning 270 字（读表再出 PDF）-> 可见文本「我来分析这个 Excel 文件...」-> ToolCallStreaming toolu_6e34... -> DecisionMade use_tool",
                s["cell"],
            ),
            cell("Thinking 展开。随后被 L2 覆盖。", s["cell"]),
        ],
        [
            cell("T1", s["cell_c"]),
            cell("36-38", s["cell_c"]),
            cell(
                "execute_code inv_8830... 读 xlsx，code=869 字节，stdout 约 11KB，三张表结构完整。files 已夹带残留「素数计算报告.pdf」",
                s["cell"],
            ),
            cell("工具卡出现。L2 思考一到就被替换。", s["cell"]),
        ],
        [
            cell("L2", s["cell_c"]),
            cell("39-87", s["cell_c"]),
            cell(
                "Reasoning 561 字（已知三张表，准备 reportlab+STSong-Light）。无 StepTextDelta。",
                s["cell"],
            ),
            cell("新 Handler：thinking 只剩本轮，T1 卡从 message.tools 消失。", s["cell"]),
        ],
        [
            cell("T2", s["cell_c"]),
            cell("88-90", s["cell_c"]),
            cell(
                "execute_code inv_0676... 生成 PDF，code=21422 字节。SyntaxError：中文引号打断字符串。",
                s["cell"],
            ),
            cell("只剩这一张卡。L3 到来后再丢。", s["cell"]),
        ],
        [
            cell("L3", s["cell_c"]),
            cell("91-172", s["cell_c"]),
            cell(
                "Reasoning 818 字（step1 语法错，重写 PDF）-> 可见文本「我来根据已读取的 Excel...」-> 再次 use_tool",
                s["cell"],
            ),
            cell("再一次覆盖。历史思考/代码都没了。", s["cell"]),
        ],
        [
            cell("T3", s["cell_c"]),
            cell("173-175", s["cell_c"]),
            cell(
                "execute_code inv_5364... <b>plugin_state 无 code、无 description</b>。stdout 一个换行。files 又是「素数计算报告.pdf」8KB。",
                s["cell"],
            ),
            cell("空代码卡。用户看不到前两段真实代码。", s["cell"]),
        ],
        [
            cell("收尾", s["cell_c"]),
            cell("176-181", s["cell_c"]),
            cell(
                "loop_warning：execute_code 连续 3 次。AgentRunFinished completed。closure 列出两份素数 PDF。",
                s["cell"],
            ),
            cell("任务被标完成，交付物是错的。", s["cell"]),
        ],
    ]
    story.append(
        table(tl, [14 * mm, 18 * mm, (usable - 32 * mm) * 0.58, (usable - 32 * mm) * 0.42])
    )
    story.append(
        P("表 2 - Journal 是步骤轨；UI 是「只留当前轮」。丢失发生在投影之后。", s["caption"])
    )

    # 2
    story.append(P("2. 目标画面 vs 当前契约", s["h1"]))
    story.append(
        P(
            "用户要的是时间线：<b>思考1 -> 工具1（含代码与 stdout）-> 思考2 -> 工具2 -> 思考3 -> 工具3 -> 答案</b>。"
            "每一轮 LLM 单独一块深度思考，块与块之间夹着已经跑完的工具卡，历史不删。",
            s["body"],
        )
    )
    story.append(
        P(
            "Run Live 规格 2.5 写的是另一件事：原生一次 call_llm = 一个 StreamingHandler = <b>一块</b> Thinking；"
            "工具跑完下一轮 LLM <b>覆盖</b>这一块；「明确不做多段 Thinking 手风琴」。"
            "JournalTransport 用 turnHadTool + handleFinish + makeHandler() 把这句规格落成了代码。",
            s["body"],
        )
    )
    story.append(
        P(
            "所以这不是「SSE 实现漏了一帧」，是 <b>规格选了原生单槽，产品要步骤轨</b>。"
            "工具卡消失是规格落地时的连带事故：为了换思考槽，连 tools 数组一起扔掉了。"
            "即便接受「思考只留当前轮」，工具卡也不该丢--账本里它们已经是完成态。",
            s["body"],
        )
    )

    # 3
    story.append(P("3. 五跳链路：每一跳断在哪", s["h1"]))
    hops = [
        [
            cell("<font color='white'><b>Hop</b></font>", s["cell_c"]),
            cell("<font color='white'><b>职责</b></font>", s["cell"]),
            cell("<font color='white'><b>本次证据</b></font>", s["cell"]),
            cell("<font color='white'><b>判定</b></font>", s["cell_c"]),
        ],
        [
            cell("H1 开工", s["cell"]),
            cell("POST /lca-api/runs -> create_run_session", s["cell"]),
            cell("Doctor H1 accepted。返回 run_e12ff4d0e987。", s["cell"]),
            pill("通过", "ok", s["cell"]),
        ],
        [
            cell("H2 记账", s["cell"]),
            cell("record() -> jsonl。唯一真相。", s["cell"]),
            cell(
                "181 事件齐全：ReasoningDeltax124，ToolStarted/Invoked 各 3。空 code 也被写成合法 plugin_state。",
                s["cell"],
            ),
            pill("事实在，语义脏", "warn", s["cell"]),
        ],
        [
            cell("H3 转播", s["cell"]),
            cell("LiveTail.subscribe + stamped_to_sse_frame", s["cell"]),
            cell(
                "last_seq=181=jsonl，evicted=0，无 LiveGap。Live 不过滤 decision channel（SSEJournalProjector 会滤）。",
                s["cell"],
            ),
            pill("管道通", "ok", s["cell"]),
        ],
        [
            cell("H4 翻译", s["cell"]),
            cell("JournalTransport 一张 switch 表", s["cell"]),
            cell(
                "只映射 7 类事件。ToolCallStreaming / ReasoningCompleted / LlmCall* 丢弃。"
                "下一轮 ReasoningDelta 销毁旧 Handler。ToolStarted 只喂当前一个 tool_calls。",
                s["cell"],
            ),
            pill("主断点", "bad", s["cell"]),
        ],
        [
            cell("H5 渲染", s["cell"]),
            cell("StreamingHandler + Thinking + executeCode 卡", s["cell"]),
            cell(
                "thinkingContent 单字符串；onToolCallsUpdate({tools}) 整表替换；"
                "onReasoningStart 新 operation，手风琴内容替换。",
                s["cell"],
            ),
            pill("按单槽工作", "warn", s["cell"]),
        ],
    ]
    story.append(table(hops, [22 * mm, 42 * mm, usable - 82 * mm, 18 * mm]))
    story.append(P("表 3 - 排障四步走完：1 有账 2 有流 3 喂错 4 原生按单槽画。", s["caption"]))

    story.append(P("3.1 后端：账本写对了什么、写脏了什么", s["h2"]))
    story.append(
        P(
            "<b>写对了。</b>深度思考走 ReasoningDelta（REASONING_TEXT_DELTA），不进 response.text。"
            "可见答复走 StepTextDelta，且同时记 decision / answer 两个 channel。"
            "本次可见文本是散文，extractor 把同一段复制进 answer，所以 journal 里成对出现："
            "seq22 decision「我来分析这个 Excel」/ seq23 answer 同样一句。前端 if (channel !== 'answer') skip，"
            "正常情况下 UI 不会双份。Live 路径没有走 SSEJournalProjector 的 decision 过滤，靠 Transport 兜底。"
            "channel 一旦在序列化里丢失，UI 会把同一句话画两遍--这是潜伏缺陷，不是这次主诉。",
            s["body"],
        )
    )
    story.append(
        P(
            "<b>写脏了三处。</b>（1）<b>ID 分裂</b>：gateway 的 run_id_scope 只是 ContextVar；"
            "CognitiveAgent.run 在 get_current_run_scope() 为 None 时无条件 new_id('run') / new_id('trace')。"
            "solo 路径 assemble.build_solo_agent 不 bind RunScope，所以每本 jsonl 的文件名和里面的 scope.run_id 都对不上。"
            "Doctor、Langfuse、人工 jq 会查错文件。（2）<b>调用 ID 两套</b>：模型侧 toolu_* 只出现在被 Transport 忽略的 ToolCallStreaming；"
            "卡片 id 用 invocation_id（inv_*）。同一工具在账本里无法用一个键串起来。"
            "（3）<b>第三轮空代码仍成功</b>：_started_execute_code 只在 args['code'] 非空时写入；"
            "本次 ToolStarted 只有 success/executionEnv/language。空代码仍进沙箱，guest scanner 扫描整个 /mnt/data/outputs，"
            "把历史「素数计算报告.pdf」收成 files。finalize 再 emit 一份 closure。"
            "AgentRunFinished.status=completed，output_text 指向错误交付物。",
            s["body"],
        )
    )

    story.append(P("3.2 前端：覆盖发生的三行代码", s["h2"]))
    story.append(
        Preformatted(
            "case 'ReasoningDelta': {\n"
            "  if (turnHadTool) {\n"
            "    void handler.handleFinish({ type: 'stop' });\n"
            "    handler = makeHandler();   // thinkingContent='', tools=undefined\n"
            "    turnHadTool = false;\n"
            "  }\n"
            "  handler.handleChunk({ text: delta, type: 'reasoning' });\n"
            "}\n"
            "case 'ToolStarted': {\n"
            "  turnHadTool = true;\n"
            "  handler.handleChunk({ tool_calls: [thisCallOnly], type: 'tool_calls' });\n"
            "  // onToolCallsUpdate(transform(thisCallOnly)) -> message.tools = [thisCallOnly]\n"
            "}",
            s["mono"],
        )
    )
    story.append(
        P(
            "图 1 - deploy/lobehub/patches/runtime/journal_transport.py 生成的 JournalTransport.ts。"
            "handleFinish 不把旧 tools 写回；新 Handler 的 onReasoningUpdate 再 dispatch { reasoning: 本轮 }，覆盖字段。",
            s["caption"],
        )
    )
    story.append(
        P(
            "StreamingHandler.handleToolCallsChunk 把 chunk.tool_calls 原样交给 transformToolCalls，"
            "<b>不与 this.tools 合并</b>。原生假设是「模型在同一次 stream 里增量补全同一个 tool_calls 数组」。"
            "LCA 是服务端闭环：每一轮 ToolStarted 是一张新卡。Transport 每次只塞一张，store 就只剩一张。"
            "SandboxOutputDelta / ToolInvoked 用 invocation_id 在 handler.getTools() 里找目标；"
            "Handler 一换，旧卡的 result/state（code、stdout、stderr）从内存蒸发，没有第二条持久化通道。",
            s["body"],
        )
    )
    story.append(
        P(
            "toOutput() 固定 toolCalls: []，只返回最后一个 Handler 的 getTools()。"
            "call_llm_finalizer 靠 lcaClosedLoop 阻止浏览器再跑工具--这是对的。"
            "副作用是：运行时结束时，消息上的工具历史已经残缺，没有任何补偿回放。",
            s["body"],
        )
    )

    # 4
    story.append(P("4. 「SSE 有问题」拆成可证伪命题", s["h1"]))
    claims = [
        [
            cell("<font color='white'><b>观感</b></font>", s["cell"]),
            cell("<font color='white'><b>是否 SSE 丢帧</b></font>", s["cell_c"]),
            cell("<font color='white'><b>真正原因</b></font>", s["cell"]),
        ],
        [
            cell("深度思考没有按每次 LLM 分开", s["cell"]),
            pill("否", "ok", s["cell"]),
            cell(
                "Journal 三轮 ReasoningCompleted 独立。UI 只有一块 Thinking；规格 2.5 要求覆盖而非堆叠。",
                s["cell"],
            ),
        ],
        [
            cell("思考没有穿插在工具调用中", s["cell"]),
            pill("否", "ok", s["cell"]),
            cell(
                "事件顺序本就是 R->T->R->T->R->T。前端把 R 和 T 画进同一个 message 的两个可覆盖字段，时间线塌成「当前槽」。",
                s["cell"],
            ),
        ],
        [
            cell("上一张工具卡消失", s["cell"]),
            pill("否", "ok", s["cell"]),
            cell(
                "ToolStartedx3 都在 jsonl 和 Live 里。Transport 单卡覆盖 + 换 Handler。",
                s["cell"],
            ),
        ],
        [
            cell("执行代码消失", s["cell"]),
            pill("部分后端", "warn", s["cell"]),
            cell(
                "T1/T2 的 code 在 plugin_state 里是完整的，被 UI 覆盖弄丢。T3 后端就没写出 code。",
                s["cell"],
            ),
        ],
        [
            cell("答案文本像复读", s["cell"]),
            pill("潜伏", "warn", s["cell"]),
            cell(
                "decision+answer 成对写入；Live 双发、Transport 滤 channel。滤失败才会双画。",
                s["cell"],
            ),
        ],
        [
            cell("最后交出素数 PDF", s["cell"]),
            pill("否", "ok", s["cell"]),
            cell(
                "共享 outputs 目录 + 空代码仍 harvest。与 SSE 无关。",
                s["cell"],
            ),
        ],
    ]
    story.append(table(claims, [42 * mm, 22 * mm, usable - 64 * mm]))
    story.append(
        P("表 4 - 把「SSE 坏了」拆开以后，管道层全部成立，状态层和产物层不成立。", s["caption"])
    )

    # 5
    story.append(P("5. 根因按机制归类（不打补丁清单）", s["h1"]))
    story.append(P("R1 - 词表在门口翻译对了，状态却只造「当前轮」一份", s["h2"]))
    story.append(
        P(
            "规格 2.3 说「状态只造一次，plugin_state 是 UI 真相」。"
            "这句话对单次 ToolStarted 成立：code/stdout 已经在事件里。"
            "它对 <b>跨轮累积</b> 不成立：没有「本 Run 已完成的工具列表」这个一等状态。"
            "Transport 把每张卡临时塞进 StreamingHandler.tools，Handler 一换，真相只剩 jsonl。"
            "缺的是注册表：run 级 tool card ledger（id -> plugin_state），SSE 只 upsert，UI 只读 ledger。",
            s["body"],
        )
    )
    story.append(P("R2 - 用原生「单次 stream」模拟「多轮服务端闭环」", s["h2"]))
    story.append(
        P(
            "LobeHub 假设：一次 chat/completions stream 里交错出现 reasoning / text / tool_calls，"
            "然后浏览器执行工具，再开下一次 stream。"
            "LCA 是：一次 Run、一条 SSE、多轮 LLM、工具在服务端跑完。"
            "lcaClosedLoop 只关掉了「浏览器再跑工具」，没有换掉「一次 stream = 一块思考 + 一组 tool_calls」。"
            "turnHadTool 换 Handler 是在垃圾前提上打补丁：想要第二块思考，却借用结束上一次 stream 的 API，副作用是清掉 tools。",
            s["body"],
        )
    )
    story.append(P("R3 - 身份有三套，对账只能靠人脑", s["h2"]))
    story.append(
        P(
            "session.run_id != journal.run_id；session.trace_id != journal.trace_id；"
            "tool_call_id(toolu_*) != invocation_id(inv_*)。"
            "Doctor 只比 jsonl.seq 和 tail.last_seq，比不出 scope 分裂，也比不出「三张卡只渲染一张」。"
            "H4/H5 对服务端永久为 null。出了覆盖 bug，doctor.v1 仍打印 ok。",
            s["body"],
        )
    )
    story.append(P("R4 - 产物收获按目录扫描，不按本次调用", s["h2"]))
    story.append(
        P(
            "GUEST_ARTIFACT_SCANNER 列出 /mnt/data/outputs 下全部非隐藏文件。"
            "空 execute_code 也会跑这段扫描。共享会话或未清空的 outputs 会把上一个任务的 PDF 标成这一次的成果。"
            "这是「被绕过的隔离该不该存在」：run_workspace_scope(session.run_id) 在宿主编了号，"
            "guest 输出目录没有按 run 切开。",
            s["body"],
        )
    )

    # 6
    story.append(P("6. 应该改哪一层（按删除测试）", s["h1"]))
    fixes = [
        [
            cell("<font color='white'><b>改动</b></font>", s["cell"]),
            cell("<font color='white'><b>层</b></font>", s["cell_c"]),
            cell("<font color='white'><b>删掉它什么问题答不上</b></font>", s["cell"]),
            cell("<font color='white'><b>不要做的事</b></font>", s["cell"]),
        ],
        [
            cell("产品拍板：步骤轨还是单槽思考", s["cell"]),
            cell("规格", s["cell_c"]),
            cell("人到底该看见几块 Thinking", s["cell"]),
            cell("继续让 2.5 和用户预期各说各话", s["cell"]),
        ],
        [
            cell(
                "Run 级 tool ledger：按 invocation_id upsert plugin_state，dispatch 全量 tools",
                s["cell"],
            ),
            cell("H4", s["cell_c"]),
            cell("历史工具卡和代码为什么还在", s["cell"]),
            cell("在 StreamingHandler 里 if/else 拼上一轮", s["cell"]),
        ],
        [
            cell(
                "若要步骤轨：每轮 LLM 落一条独立 thinking 块（或独立 assistant part），禁止覆盖同一字段",
                s["cell"],
            ),
            cell("H4/H5", s["cell_c"]),
            cell("思考如何夹在工具之间", s["cell"]),
            cell("把多轮塞进同一个 thinkingContent 字符串假装时间线", s["cell"]),
        ],
        [
            cell("CognitiveAgent 继承 gateway RunScope，禁止 solo 再 mint run/trace", s["cell"]),
            cell("H2", s["cell_c"]),
            cell("jsonl 文件名和 scope 为什么是同一个 run", s["cell"]),
            cell("Doctor 里再加一层 id 别名映射", s["cell"]),
        ],
        [
            cell(
                "execute_code 缺 code -> ToolDenied；harvest 只收本次新建/指纹变化文件，outputs 按 run 隔离",
                s["cell"],
            ),
            cell("执行/沙箱", s["cell_c"]),
            cell("空调用为什么不能冒充交付", s["cell"]),
            cell("在 closure 文案里过滤「素数」这种特例", s["cell"]),
        ],
        [
            cell("Live 与 SSEJournalProjector 同一过滤：decision channel 不上插座", s["cell"]),
            cell("H3", s["cell_c"]),
            cell("curl /live 为什么不出现双份可见文本", s["cell"]),
            cell("只在前端多写一个 skip", s["cell"]),
        ],
        [
            cell(
                "Doctor：scope==session；每张 ToolStarted 是否仍能在终态 tools 里找到；空 code 失败",
                s["cell"],
            ),
            cell("诊断", s["cell_c"]),
            cell("H4/H5 这次为什么不是 ok", s["cell"]),
            cell("再加一个只数 seq 的绿灯", s["cell"]),
        ],
    ]
    story.append(
        table(fixes, [48 * mm, 18 * mm, (usable - 66 * mm) * 0.5, (usable - 66 * mm) * 0.5])
    )
    story.append(P("表 5 - 每一行都能回答「删掉它，哪个问题无法回答」。", s["caption"]))

    story.append(P("建议落地顺序", s["h2"]))
    story.append(
        ListFlowable(
            [
                ListItem(
                    P(
                        "先修工具卡累积（R1/H4）。不改规格也能让「代码消失」消失。验收：三张 execute_code 卡同时在，T1 代码与 stdout 仍在。",
                        s["bullet"],
                    )
                ),
                ListItem(
                    P(
                        "再拍思考模型。若要穿插：改规格 2.5，做步骤轨，而不是在 Handler 上叠 tempDisplayContent。",
                        s["bullet"],
                    )
                ),
                ListItem(
                    P(
                        "收口 ID：solo 继承 session RunScope。验收：jq .scope.run_id 等于文件名。",
                        s["bullet"],
                    )
                ),
                ListItem(
                    P(
                        "沙箱隔离 + 空 code 拒绝。验收：本任务不得再冒出「素数计算报告.pdf」。",
                        s["bullet"],
                    )
                ),
            ],
            bulletType="1",
            start="1",
            leftIndent=14,
        )
    )

    # 7
    story.append(P("7. 附录：关键事件摘录", s["h1"]))
    excerpt = [
        [
            cell("<font color='white'><b>事件</b></font>", s["cell"]),
            cell("<font color='white'><b>内容</b></font>", s["cell"]),
        ],
        [
            cell("T1 ToolStarted", s["cell"]),
            cell("code 869 字节；desc=Read Excel file structure and content", s["cell"]),
        ],
        [
            cell("T1 ToolInvoked ok=true", s["cell"]),
            cell("stdout 约 11KB；files 已夹带「素数计算报告.pdf」（污染）", s["cell"]),
        ],
        [
            cell("T2 ToolStarted", s["cell"]),
            cell("code 21422 字节；desc=Generate PDF version of ...", s["cell"]),
        ],
        [
            cell("T2 ToolInvoked ok=false", s["cell"]),
            cell("SyntaxError: invalid syntax（中文引号打断字符串）", s["cell"]),
        ],
        [
            cell("T3 ToolStarted", s["cell"]),
            cell("keys 仅 success / executionEnv / language；无 code", s["cell"]),
        ],
        [
            cell("T3 ToolInvoked ok=true", s["cell"]),
            cell("output 一个换行；files 再次是「素数计算报告.pdf」", s["cell"]),
        ],
        [
            cell("AgentRunFinished", s["cell"]),
            cell("completed；文案称已生成两份素数计算报告.pdf", s["cell"]),
        ],
        [
            cell("RunInsight", s["cell"]),
            cell("助手疑似循环：use_tool(execute_code) 连续 3 次", s["cell"]),
        ],
    ]
    story.append(table(excerpt, [48 * mm, usable - 48 * mm]))
    story.append(
        P(
            "完整账本：traces/runs/run_e12ff4d0e987.jsonl。"
            "对照：jq -c '{seq,event_type}' 该文件；curl -N -H 'Last-Event-ID: 0' /runs/run_e12ff4d0e987/live。"
            "二者事件名必须与 Python 类名相同。本次它们一致；不一致的是 UI 终态。",
            s["caption"],
        )
    )

    story.append(P("涉及文件", s["h2"]))
    files = [
        [
            cell("<font color='white'><b>路径</b></font>", s["cell"]),
            cell("<font color='white'><b>角色</b></font>", s["cell"]),
        ],
        [
            cell("traces/runs/run_e12ff4d0e987.jsonl + .doctor.json", s["cell"]),
            cell("本样本账本与探针", s["cell"]),
        ],
        [
            cell("gateway/runs/{api,live,execute,session}.py", s["cell"]),
            cell("开工、LiveTail、两套 id 的源头", s["cell"]),
        ],
        [
            cell("lca/layer3_agent/cognitive_agent.py", s["cell"]),
            cell("solo 再 mint run_id/trace_id", s["cell"]),
        ],
        [
            cell("lca/layer0_infra/observability/adapters.py", s["cell"]),
            cell("ReasoningDelta / 双 channel StepTextDelta", s["cell"]),
        ],
        [
            cell("lca/layer1_cognitive/body/tool_ui_builders.py", s["cell"]),
            cell("空 code 仍能出 started state", s["cell"]),
        ],
        [
            cell("lca/layer0_infra/sandbox/artifact_scanner.py", s["cell"]),
            cell("整目录 harvest", s["cell"]),
        ],
        [
            cell("deploy/lobehub/patches/runtime/journal_transport.py", s["cell"]),
            cell("覆盖式喂流（主断点）", s["cell"]),
        ],
        [
            cell("lobehub-ui/.../StreamingHandler.ts", s["cell"]),
            cell("单槽 thinking + 整表替换 tools", s["cell"]),
        ],
        [
            cell(
                "docs/superpowers/specs/2026-08-13-run-live-architecture-design.md sec 2.5",
                s["cell"],
            ),
            cell("「明确不做多段 Thinking」", s["cell"]),
        ],
    ]
    story.append(table(files, [usable * 0.58, usable * 0.42]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="SSE / 深度思考 / 工具卡消失：前后端链路系统分析",
        author="LCA engineering",
        subject="run_e12ff4d0e987 chain analysis",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(OUT.resolve())


if __name__ == "__main__":
    build()
