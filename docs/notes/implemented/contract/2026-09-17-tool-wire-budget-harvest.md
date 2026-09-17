# Agent Note: 工具 JSON 截断后仍把 path/content 交给沙箱

Status: implemented

## Problem

沙箱已经能分块写入大文件。失败的 PDF run 并不是沙箱写不下，而是 LLM function-call 的 `arguments` JSON 在 `max_tokens=8192` 处被截断后，执行路径把整段 payload 丢成 `{}`。同一套截断 JSON，journal 侧的 partial extractor 已经能抽出 `path` 和 `content`。文件从未到达沙箱，模型再生成一遍同样的 JSON，直到墙钟打满。

## Decision

执行路径与 journal 路径共用 `recover_partial_tool_arguments`：strict JSON 失败时仍抽出 `path` / `content` / `code` / `command`，有可用字段则 `ToolArgumentsOk`，writeFile 照常进沙箱（onlyboxes 对大于 48KB 的写入分块）。抽不出字段才标 incomplete。带 tools 的默认 `max_tokens` 为 32768。墙钟耗尽时 `think.budget.gate` 仍写出用户可见收口。生成 PDF/xlsx 的推荐路径是 `executeCode` 读取工作区已有文件，而不是把数据集内联进脚本。

## Alternatives considered

### Why not reject JSON over 16KB?

That treats the LLM wire as the filesystem. Coding agents write large source files through Write; the sandbox already chunks. Rejecting after a 140s generation wastes the run and never lands the file.

### Why not raise only the 300s wall-clock cap?

The hang was 8317 completion tokens truncated at 8192, then retried. More wall-clock repeats the same empty `{}` execute. The missing piece is recovering the body and giving the tool-call enough output tokens.

### Why not silently close braces and run truncated Python as if complete?

Brace-completion was rejected in ADR-0047 because it fabricates a finished program. Recovering the streamed `content` string and writing it is a Write, not a fabricated execute. A truncated `.py` then fails at run, and the next think can edit.

## Consequences

A truncated writeFile with recoverable `path`+`content` reaches the sandbox. Empty `{}` only happens when no fields can be extracted. Tool-call completions have a 32k token budget. PDF generation still prefers executeCode against files already on disk.
