---
name: officecli
description: "Create/read/edit/validate .docx .xlsx .pptx via preinstalled officecli in sandbox (run_command + --json). Prefer over python-docx/openpyxl for Office construction. Not for PDF or pure pandas analysis."
version: 1.0.0
---

# officecli（LCA 沙箱）

AI 友好的 Word / Excel / PowerPoint CLI。**二进制已预装在 terminal 镜像**，
通过 `run_command` 调用。不要 `curl install`、不要 `pip install`、不要在宿主执行。

## 硬约束（LCA）

| 规则 | 说明 |
|------|------|
| 执行面 | 只用 `run_command`（或激活后 `run_skill_script`） |
| 工作区 | 附件在 `/mnt/data/<文件名>`；交付物写 **`/mnt/data/outputs/`** |
| 下载 | 写在 outputs 下的新/变更文件会在 **`run_command` 结束后自动 harvest** 到前端下载卡；一般**不必**再 `export_file` |
| 输出 | **一律加 `--json`**（除 `help` / `view outline` 调试） |
| 安装 | **禁止** `curl …/install.sh`；若 `officecli --version` 失败 → 报镜像缺包，勿自装 |
| 更新 | 环境已设 `OFFICECLI_SKIP_UPDATE=1`；勿开 auto-update |
| PDF | 不用 officecli；用 `anthropics-skills-pdf` / reportlab |
| 数据分析 | 纯表计算用 pandas；officecli 负责 **xlsx 文件结构/公式/透视/图表** |

```bash
# 产物目录
mkdir -p /mnt/data/outputs
officecli create /mnt/data/outputs/report.pptx --json
```

## 策略：L1 → L2 → L3

1. **L1 读**：`view`（outline / text / issues / stats）
2. **L2 DOM**：`get` / `query` / `set` / `add` / `remove` / `batch`
3. **L3 raw**：仅当 L2 不够时 `raw` / `raw-set`

不确定属性名时 **先 help，再猜**：

```bash
officecli help pptx set shape --json
officecli help docx paragraph --json
officecli help xlsx pivottable --json
```

## 快速路径

### PowerPoint

```bash
officecli create /mnt/data/outputs/deck.pptx --json
officecli add /mnt/data/outputs/deck.pptx / --type slide --prop title="Q4 Report" --prop background=1A1A2E --json
officecli add /mnt/data/outputs/deck.pptx '/slide[1]' --type shape \
  --prop text="Revenue +25%" --prop x=2cm --prop y=5cm --prop font=Arial --prop size=24 --prop color=FFFFFF --json
officecli view /mnt/data/outputs/deck.pptx outline
officecli validate /mnt/data/outputs/deck.pptx --json
officecli view /mnt/data/outputs/deck.pptx issues --json
```

### Word

```bash
officecli create /mnt/data/outputs/report.docx --json
officecli add /mnt/data/outputs/report.docx /body --type paragraph --prop text="Executive Summary" --prop style=Heading1 --json
officecli add /mnt/data/outputs/report.docx /body --type paragraph --prop text="Revenue increased 25% YoY." --json
officecli validate /mnt/data/outputs/report.docx --json
```

### Excel

```bash
officecli create /mnt/data/outputs/data.xlsx --json
officecli set /mnt/data/outputs/data.xlsx /Sheet1/A1 --prop value="Name" --prop bold=true --json
officecli set /mnt/data/outputs/data.xlsx /Sheet1/B1 --prop value="Score" --prop bold=true --json
officecli set /mnt/data/outputs/data.xlsx /Sheet1/A2 --prop value="Alice" --json
officecli set /mnt/data/outputs/data.xlsx /Sheet1/B2 --prop value=95 --json
```

### 编辑已有附件

```bash
# 用户上传 → /mnt/data/input.docx
officecli view /mnt/data/input.docx outline
officecli get /mnt/data/input.docx /body --depth 1 --json
# 改完后复制/写出到 outputs 再 export_file
officecli close /mnt/data/input.docx --json   # 若开过 resident
cp /mnt/data/input.docx /mnt/data/outputs/input-edited.docx
```

## 性能：batch / resident

多步优先 **batch**（原子，失败整批回滚）或 **open → 多次 set → close**：

```bash
officecli open /mnt/data/outputs/deck.pptx --json
# … 多次 add/set …
officecli close /mnt/data/outputs/deck.pptx --json
```

交付或给 Python 读之前必须 `save`/`close`（flush）。  
非 officecli 程序读盘前务必 flush。

## 自愈

失败响应含 `error.code` 与 `suggestion`。常见码：
`not_found` · `invalid_value` · `unsupported_property` · `invalid_path`。

```bash
# 路径错 → 先枚举子节点
officecli get /mnt/data/outputs/deck.pptx / --depth 1 --json
officecli get /mnt/data/outputs/deck.pptx '/slide[1]' --depth 1 --json
```

交付前：

```bash
officecli validate <file> --json
officecli view <file> issues --json
```

## Shell 陷阱

| 错误 | 正确 |
|------|------|
| 未引号 `'/slide[1]'` | 始终单引号包路径（防 shell glob） |
| `--prop text="$15M"` | 单引号：`--prop text='$15M'` |
| 猜属性名 | `officecli help <fmt> <element>` |
| 产物写 `/tmp` | 写 `/mnt/data/outputs/` 再 `export_file` |
| `watch` / 本地 MCP | 生产 agent **不要用** |

## 场景子 skill（内置）

需要专业版式时：

```bash
officecli load_skill pitch-deck      # 融资 deck
officecli load_skill financial-model # 财务模型
officecli load_skill data-dashboard  # 数据看板
officecli load_skill academic-paper  # 学术论文
officecli load_skill pptx            # 通用 PPT 细则
officecli load_skill word            # 通用 Word 细则
officecli load_skill excel           # 通用 Excel 细则
```

每个产物只 load **一个** 最具体 skill；规则会指导后续 `add`/`set`。

## 与 fallback 库

| 场景 | 用 |
|------|-----|
| 专业 Office 生成/结构化改 | **officecli**（本 skill） |
| 快速读 xlsx 做 pandas 分析 | openpyxl/pandas（无需本 skill） |
| PDF | anthropics-skills-pdf |
| 旧 `.doc` OLE | 优先转 docx 再 officecli；或 olefile 探测 |

## 版本

镜像钉选的 CLI 版本见 `officecli --version`。能力以 `officecli help` 为准。
