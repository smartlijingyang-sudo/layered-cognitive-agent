"""Root cause analysis PDF: sandbox mount/data + DSH SSE issues."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT = "output/bug_root_cause_analysis.pdf"

# -- styles ------------------------------------------------------------------

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "CNTitle",
    parent=styles["Title"],
    fontSize=20,
    leading=26,
    spaceAfter=6,
)

subtitle_style = ParagraphStyle(
    "CNSubtitle",
    parent=styles["Normal"],
    fontSize=11,
    textColor=colors.grey,
    spaceAfter=18,
)

h1 = ParagraphStyle("CNH1", parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=8)
h2 = ParagraphStyle("CNH2", parent=styles["Heading2"], fontSize=13, leading=16, spaceAfter=6)
h3 = ParagraphStyle("CNH3", parent=styles["Heading3"], fontSize=11, leading=14, spaceAfter=4)

body = ParagraphStyle(
    "CNBody",
    parent=styles["Normal"],
    fontSize=10,
    leading=14,
    spaceAfter=6,
)

code_style = ParagraphStyle(
    "CNCode",
    parent=styles["Code"],
    fontSize=8,
    leading=10,
    leftIndent=12,
    spaceAfter=6,
    backColor=colors.Color(0.96, 0.96, 0.96),
)

red_body = ParagraphStyle(
    "CNRedBody",
    parent=body,
    textColor=colors.Color(0.7, 0.1, 0.1),
)

green_body = ParagraphStyle(
    "CNGreenBody",
    parent=body,
    textColor=colors.Color(0.1, 0.45, 0.1),
)

# -- helpers -----------------------------------------------------------------


def bullet(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(t, body), bulletColor=colors.darkblue) for t in items],
        bulletType="bullet",
        start="•",
    )


def code_block(text: str) -> Paragraph:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(escaped, code_style)


def key_table(rows: list[list[str]], col_widths=(55 * mm, 110 * mm)) -> Table:
    """Two-column key-value table."""
    data = []
    for k, v in rows:
        data.append([Paragraph(f"<b>{k}</b>", body), Paragraph(v, body)])
    t = Table(data, colWidths=col_widths, repeatRows=0)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.85, 0.85, 0.85)),
                ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.95, 0.98)),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def flow_table(headers: list[str], rows: list[list[str]], col_widths=None) -> Table:
    data = [[Paragraph(f"<b>{h}</b>", body) for h in headers]]
    for row in rows:
        data.append([Paragraph(c, body) for c in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.85, 0.85, 0.85)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.88, 0.92, 0.98)),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


# -- build story -------------------------------------------------------------

story = []

# Title page
story.append(Paragraph("LCA  recurrent bug 根因分析报告", title_style))
story.append(Paragraph("沙箱 mount/data 文件缺失 + DSH 模式 SSE 事件丢失", subtitle_style))
story.append(Paragraph("日期：2026-08-15 &nbsp;&nbsp;|&nbsp;&nbsp; 分析人：Grok Build", body))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
story.append(Spacer(1, 12))

# ── Executive summary ──
story.append(Paragraph("Executive Summary", h1))
story.append(
    Paragraph(
        "本报告定位了两个反复出现的问题的根本原因，并给出了修复建议。"
        "两个问题均已在 trace 日志中找到确凿证据。",
        body,
    )
)
story.append(Spacer(1, 6))

exec_rows = [
    ["问题", "根因一句话", "严重度", "影响"],
    [
        "沙箱文件找不到",
        "前端上传的相对 URL 被 ingest 管道静默丢弃",
        "P0",
        "用户上传文件后 Agent 无法读取",
    ],
    [
        "DSH 无 SSE 渲染",
        "DSH 线程中 contextvar 丢失，journal 事件未进入 LiveTail",
        "P0",
        "前端选择 DSH 后无任何流式输出",
    ],
]
story.append(flow_table(exec_rows[0], exec_rows[1:], col_widths=(30 * mm, 60 * mm, 15 * mm, 60 * mm)))
story.append(Spacer(1, 18))

# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 1 — Sandbox mount/data
# ═══════════════════════════════════════════════════════════════════════════

story.append(Paragraph("问题一：沙箱 mount/data 文件找不到", h1))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
story.append(Spacer(1, 8))

story.append(Paragraph("现象", h2))
story.append(
    Paragraph(
        "用户通过 LobeHub 前端上传文件后发起 Run。Agent 在沙箱中尝试读取 "
        "<font face='Courier'>/mnt/data/xxx.doc</font> 时报 "
        "<font color='red'><b>No such file or directory</b></font>。"
        "该问题多次复现，涉及不同文件类型。",
        body,
    )
)

story.append(Paragraph("证据（trace 日志）", h2))
story.append(
    Paragraph(
        "以 <font face='Courier'>run_8dcf03d6a59c</font> 为例："
        "用户上传 <b>优信会议记录.doc</b>，LobeHub 消息体中包含：",
        body,
    )
)
story.append(
    code_block(
        '<file id="file_96e727496e24" name="优信会议记录.doc"\n'
        '      size="11264" url="/files/file_96e727496e24"></file>'
    )
)
story.append(
    Paragraph(
        "注意 URL 是 <b>相对路径</b> <font face='Courier'>/files/file_96e727496e24</font>，"
        "没有 scheme 也没有 hostname。",
        body,
    )
)
story.append(
    Paragraph(
        "随后 trace 显示：seq 44 读文件 → No such file；seq 62 listFiles → missing；"
        "seq 130 Agent 尝试 curl → connection refused；seq 411 Agent 放弃。",
        body,
    )
)

story.append(Paragraph("根因链", h2))
story.append(
    Paragraph(
        "<b>根因：</b>前端生成的文件 URL 是相对路径，但 ingest 管道要求绝对 URL。"
        "不匹配时被 <b>静默丢弃</b>，不产生 attachment_id，沙箱挂载为空。",
        red_body,
    )
)

story.append(Spacer(1, 4))
chain_rows = [
    ("1. 前端 URL", 'LobeHub 生成 url="/files/file_96e727496e24"（相对路径）'),
    ("2. ingress.py:370", "_file_ref_from_attrs() 原样存储相对 URL"),
    ("3. ingress.py:459", "prepare_run_from_messages() → ingest_file_refs()"),
    ("4. ingest.py:192", "assert_ingest_url_allowed() → urlparse 得到空 scheme/hostname"),
    ("5. ingest.py:462", "IngestUrlPolicyError 被 except 捕获 → skipped.append()，静默跳过"),
    ("6. execute.py:216", "run_attachment_scope(()) → 空 tuple，无文件可挂载"),
    ("7. runtime_mount.py:44", "load_mount_files() 遍历空 ID → 返回 {}"),
    ("8. runtime.py:118", "ensure_ready() 以零文件状态报告 ready"),
    ("9. 结果", "Agent 看到 files_info 中的文件名，但沙箱里找不到 → No such file"),
]
story.append(key_table(chain_rows))
story.append(Spacer(1, 8))

story.append(Paragraph("关键代码", h3))
story.append(Paragraph("ingest.py — URL 策略检查（第 192-199 行）：", body))
story.append(
    code_block(
        "parsed = urlparse(url.strip())      # '/files/file_xxx' → scheme='', host=''\n"
        "scheme = (parsed.scheme or '').lower()\n"
        "if scheme not in _ALLOWED_SCHEMES:  # {'http', 'https'}\n"
        "    raise IngestUrlPolicyError(...)  # ← 在此抛出\n"
        "host = (parsed.hostname or '').strip().lower()\n"
        "if not host:\n"
        "    raise IngestUrlPolicyError('URL missing hostname')  # ← 也会在此失败"
    )
)
story.append(Paragraph("ingest.py — 静默吞掉异常（第 462-464 行）：", body))
story.append(
    code_block(
        "except IngestUrlPolicyError as exc:\n"
        "    _log.warning('lobehub_file_ingest_blocked', ...)\n"
        "    skipped.append(ref.name)   # ← 文件被跳过，无 attachment_id\n"
        "    continue"
    )
)

story.append(Paragraph("次要因素：容器镜像不匹配", h2))
story.append(
    Paragraph(
        "部分 trace（如 <font face='Courier'>run_de2219458dad</font>）显示所有命令报 "
        "<font face='Courier'>cd: can't cd to /mnt/data</font>。"
        "原因是 Onlyboxes worker 使用了上游默认镜像（WORKDIR /workspace），"
        "而非本地构建的 <font face='Courier'>onlyboxes-terminal-local:lca</font> 镜像"
        "（该镜像包含 <font face='Courier'>/mnt/data</font>）。"
        "需在 worker 上设置环境变量 "
        "<font face='Courier'>WORKER_TERMINAL_EXEC_DOCKER_IMAGE=onlyboxes-terminal-local:lca</font>。",
        body,
    )
)

story.append(Paragraph("修复建议", h2))
story.append(
    bullet(
        [
            "<b>解析相对 URL：</b>在 ingress.py 构造 FileRef 时，"
            "对 <font face='Courier'>url.startswith('/')</font> 的 URL 拼接 LobeHub base URL"
            "（从 <font face='Courier'>LCA_LOBEHUB_BASE_URL</font> 或请求 host 获取）。",
            "<b>失败要响亮：</b>ingest.py 捕获 IngestUrlPolicyError 后，"
            "应写入 journal 事件通知前端「文件 X 无法下载」，而非静默跳过。",
            "<b>Pre-flight 检查：</b>在 bind_sandbox_runtime() 之前，"
            "校验 session.attachment_ids 是否覆盖了用户消息中的文件引用。"
            "若有遗漏，向 Run 写入 warning 事件。",
            "<b>Worker 镜像校验：</b>确保 Onlyboxes worker 使用正确的本地镜像，"
            "并在 health check 中加入 smoke-guest-layout.sh。",
        ]
    )
)

story.append(Spacer(1, 18))

# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 2 — DSH SSE
# ═══════════════════════════════════════════════════════════════════════════

story.append(Paragraph("问题二：DSH 模式无 SSE 事件渲染", h1))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
story.append(Spacer(1, 8))

story.append(Paragraph("现象", h2))
story.append(
    Paragraph(
        "前端选择 DSH 模式发起 Run 后，SSE 流没有任何事件到达前端。"
        "页面停留在空白状态，直到 Run 结束。该问题多次复现。",
        body,
    )
)

story.append(Paragraph("证据（trace 日志）", h2))
story.append(
    Paragraph(
        "所有 DSH Run 的 <b>主 journal (.jsonl) 均为 0 字节</b>，"
        "而 DSH 归档 (.dsh.jsonl) 包含完整事件流：",
        body,
    )
)

evidence_rows = [
    ("Run ID", "主 journal (.jsonl)", "DSH 归档 (.dsh.jsonl)", "Doctor 诊断"),
    (
        "run_fa3336bf13e7",
        "<b>0 bytes</b>",
        "97,286 bytes",
        'H2 broken: "jsonl empty or missing"',
    ),
    (
        "run_5b90c835644f",
        "<b>0 bytes</b>",
        "79,384 bytes",
        "（同模式）",
    ),
]
story.append(flow_table(evidence_rows[0], evidence_rows[1:], col_widths=(38 * mm, 30 * mm, 40 * mm, 57 * mm)))
story.append(Spacer(1, 4))
story.append(
    Paragraph(
        "此外还有 <b>13 个其他 Run 的 .jsonl 也为 0 字节</b>，均属于同一根因。",
        body,
    )
)

story.append(Paragraph("根因分析", h2))
story.append(
    Paragraph(
        "<b>根因：</b>DSH 执行在独立线程 + 独立 event loop 中运行，"
        "contextvar <font face='Courier'>_hub_var</font> 在跨线程/跨 loop 传播时丢失，"
        "导致 <font face='Courier'>record()</font> 静默 no-op。",
        red_body,
    )
)
story.append(Spacer(1, 4))

story.append(Paragraph("调用链与 contextvar 丢失点：", body))
story.append(
    code_block(
        "execute_run()                          # 主 event loop\n"
        "  with bind(hub):                      # _hub_var.set(hub)  ← 设置 contextvar\n"
        "    await execute_dsh_session(session) # 仍在主 loop\n"
        "      await run_dsh_machine_turn(...)  # 仍在主 loop\n"
        "        await asyncio.to_thread(       # 复制 context 到线程 ✓\n"
        "          driver.run, spec)\n"
        "          ↓ 进入线程\n"
        "          driver.run(spec):\n"
        "            self._runtime.run_turn(spec, on_event)\n"
        "              loop = asyncio.new_event_loop()  # ← 新建 event loop\n"
        "              loop.run_until_complete(         # ← 创建 Task，复制当前 context\n"
        "                self._run_turn_async(spec, on_event))\n"
        "                ↓ _run_turn_async 中：\n"
        "                events = await self._read_events(events_path)\n"
        "                for notification in events:\n"
        "                  on_event(notification)  # → projector.feed() → sink.emit()\n"
        "                    → record(event)       # → _hub_var.get() → ???\n"
        ""
    )
)

story.append(
    Paragraph(
        "理论上 <font face='Courier'>asyncio.to_thread</font> 会复制 context，"
        "新 loop 的 Task 也会继承。但实际证据（.jsonl 全空）表明 "
        "<font face='Courier'>_hub_var.get()</font> 返回了 None。"
        "可能原因：",
        body,
    )
)
story.append(
    bullet(
        [
            "<font face='Courier'>asyncio.new_event_loop()</font> 创建后未 "
            "<font face='Courier'>set_event_loop()</font>，导致 run_until_complete "
            "的 context 复制行为不确定",
            "线程池中 context 复制在不同 Python 版本（3.12/3.14）表现不一致",
            "FacadeJournalSink 依赖 ambient contextvar，而 DSH 的线程模型天然不安全",
        ]
    )
)

story.append(Paragraph("对比：正常 Agent/Team 模式", h3))
story.append(
    Paragraph(
        "正常模式下，Agent/Team 的 <font face='Courier'>run()</font> 在主 event loop 中执行，"
        "所有 journal 事件通过 <font face='Courier'>bind(hub)</font> 的 context 发射。"
        "LiveTail 作为 hub 的 reader 实时收到事件，推送到 SSE 流。"
        "DSH 模式打破了这个假设——执行发生在远程 machine + 本地线程中。",
        body,
    )
)

story.append(Paragraph("对比：DSH 归档 vs 主 journal", h3))
story.append(
    bullet(
        [
            "<b>DSH 归档 (.dsh.jsonl)：</b>由 <font face='Courier'>JsonlEventArchive</font> "
            "直接写入，不依赖 contextvar → 数据完整",
            "<b>主 journal (.jsonl)：</b>由 <font face='Courier'>JsonlJournalProjector</font> "
            "写入，需经过 <font face='Courier'>record()</font> → "
            "<font face='Courier'>_hub_var.get()</font> → hub.journal → projector → 文件",
            "归档有数据但 journal 为空 → 断点在 <font face='Courier'>record()</font>",
        ]
    )
)

story.append(Paragraph("修复建议", h2))
story.append(
    bullet(
        [
            "<b>显式传递 hub（推荐）：</b>将 hub 或 tail 显式传入 "
            "MachineDshRuntime 和 DshJournalProjector，不依赖 contextvar。"
            "execute_dsh_session() 已持有 session.tail，可直接传给 projector。",
            "<b>修复 event loop 创建：</b>在 run_turn() 中添加 "
            "asyncio.set_event_loop(loop)，确保 context 正确传播。"
            "但这只是兜底，显式传递更可靠。",
            "<b>添加诊断断言：</b>在 FacadeJournalSink.emit() 中检查 "
            "_hub_var.get() 是否为 None，若是则 structlog.error 而非静默返回。",
            "<b>集成测试：</b>添加 DSH 模式的 E2E 测试，验证 .jsonl 非空且包含 "
            "AgentRunStarted + StepTextDelta + AgentRunFinished 事件序列。",
        ]
    )
)

story.append(Spacer(1, 18))

# ═══════════════════════════════════════════════════════════════════════════
# Architecture diagram
# ═══════════════════════════════════════════════════════════════════════════

story.append(Paragraph("附录：事件流架构图", h1))
story.append(Spacer(1, 6))

story.append(Paragraph("正常模式（Agent/Team）— 事件流完整", h2))
story.append(
    code_block(
        "  Agent/Team.run()  ──record()──▶  hub.journal.record()\n"
        "       │                                │\n"
        "       │ (主 event loop)                 ├──▶ LiveTail ──▶ SSE ──▶ 前端 ✓\n"
        "       │                                ├──▶ JsonlProjector ──▶ .jsonl ✓\n"
        "       │                                └──▶ Langfuse exporter\n"
        "  bind(hub) contextvar ✓"
    )
)

story.append(Spacer(1, 6))
story.append(Paragraph("DSH 模式 — 事件流断裂", h2))
story.append(
    code_block(
        "  MachineDshRuntime.run_turn()  ──on_event──▶  projector.feed()\n"
        "       │                                           │\n"
        "       │ (新线程 + 新 event loop)                    ├──▶ archive.append() ✓ (.dsh.jsonl)\n"
        "       │                                           │\n"
        "       │  record() ── _hub_var.get() ── None ──▶  └──▶ sink.emit() → record() → None ✗\n"
        "       │                                                    │\n"
        "       │                                          LiveTail 收不到 ✗\n"
        "       │                                          .jsonl 空 ✗\n"
        "       │                                          SSE 无事件 ✗"
    )
)

story.append(Spacer(1, 6))
story.append(Paragraph("沙箱文件挂载 — URL 解析断裂", h2))
story.append(
    code_block(
        "  LobeHub 前端  ──url='/files/file_xxx'──▶  ingress.py\n"
        "       │                                        │\n"
        "       │ (相对 URL)                              ├──▶ _file_ref_from_attrs() → FileRef(url=相对)\n"
        "       │                                        │\n"
        "       │                                        └──▶ ingest.py: assert_ingest_url_allowed()\n"
        "       │                                              │\n"
        "       │                                         scheme='' → IngestUrlPolicyError\n"
        "       │                                              │\n"
        "       │                                         except → skipped.append() → 静默丢弃 ✗\n"
        "       │                                              │\n"
        "       │                                    attachment_ids = () → 沙箱挂载为空 ✗"
    )
)

# -- build pdf ---------------------------------------------------------------

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=20 * mm,
    rightMargin=20 * mm,
    topMargin=20 * mm,
    bottomMargin=20 * mm,
    title="LCA Bug Root Cause Analysis",
    author="Grok Build",
)
doc.build(story)
print(f"PDF written to {OUTPUT}")
