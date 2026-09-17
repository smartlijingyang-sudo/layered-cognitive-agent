# Agent Note: Skill 激活列出可运行脚本，inspect 不挡住执行

Status: implemented

## Problem

Market 导入的 pdf / xlsx skill 在磁盘上有 `resources/scripts/`，但 `manifest.references` 为空。激活后 prompt 写「无可用 references，不要读」。模型看不到脚本路径，也不会调 `run_skill_script`，而是把整份 reportlab 抄进 `executeCode` / `runCommand`。

同一 run 里 inspect 对 Excel 样例做 `json.dumps`，日期列是 `datetime`，guest 报 `Object of type datetime is not JSON serializable`。`ensure_ready` 把这次观察失败当成环境未就绪。`executeCode` 全挂。`runCommand` 写到 `outputs/` 的 PDF 也收不回来，前端没有文件卡。

## Decision

激活时用 `usable_skill_resources`：frontmatter `references` 优先；否则从 `resource_paths` 取出 `.py` / `.md` 等，丢掉 LICENSE 和 `schemas/`。索引写进 `<skill_references>`。脚本只列路径，要求 `run_skill_script` 在 skill 工作目录执行，不把源码塞进 prompt。

Inspect 的 guest `json.dumps` 带 `_jsonable`（`isoformat` / numpy `.item` / `str`）。Inspect 失败只记 warning，`_ready` 仍为 true，后续 execute 与 `outputs/` harvest 照常。PDF / 图 / HTML 仍由 harvest 进 FileStore 卡片，不依赖模型再调一次 `exportFile`。

## Alternatives considered

### Why not dump every script into the prompt?

xlsx 包带大量 xsd。正文已经很长。业界 skill 是「SKILL.md + 路径，cwd 执行」，不是把脚本当 completion。

### Why not keep inspect as a gate on ready?

Inspect 是观察面。Excel 日期序列化失败不应禁止写 PDF。挡 ready 会让 harvest 返回空，前端没有文件。

### Why not require exportFile for every PDF?

`outputs/` 下的 PDF 已是 FileViewer 原生产物。再强制 `exportFile` 是第二条发布路径。模型漏调就丢卡。Harvest 才是默认出口。

## Consequences

Market pdf/xlsx 激活后模型能看到 `scripts/*.py` 和 `forms.md`。Inspect 炸了也能跑工具、能收 `outputs/*.pdf`。显式 `sandbox_inspect` 工具仍返回失败摘要。
