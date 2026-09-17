# Agent Note: 沙箱寻址与工具目录分 section

Status: implemented

## Problem

用户上传了文件。模型首轮只能看到 LobeHub 的 `<files_info url="/files/<id>">`。那是 HTTP 身份，不是工作区路径。系统提示里没有工作根、没有 `outputs/`、没有 `/mnt/data/<文件名>`。模型对 `/files/<id>` 做 `executeCode` / `ls` / `listFiles`，再 `find /` 找 xlsx。

同一份 system prompt 还把工具可用性写成 XML `<tools>`。原生 function calling 已经在同一次请求上带了 schema。空 XML 目录是对的；执行环境跟着空目录一起消失是错的。

## Decision

工具目录和沙箱寻址是两个 section。

`ToolsSection` 只渲染 XML 目录。原生 `tool_calls` 路径上 `PromptReasoner.render_turn` 传 `tools=()`，空目录不输出「无可用工具」，也不再附带环境说明。

`CloudSandboxSection`（`cloud_sandbox`）渲染绑定 plane 的工作根、`outputs/`、已同步附件的 guest 路径。`react_prompt` / `routing_prompt` / `hierarchical_prompt` 都在 `tools` 之后引用它。plane 未绑定时默认沙箱（`/mnt/data`）；primary 是 machine 时渲染本机角色。附件列表仍走 `render_system_role`；没有 FileStore 时环境说明照常，上传清单为空。

`PromptSurface.render_sandbox_block` 不因 `tools` 为空而返回空串。`files_info` 的 `/files/<id>` 仍是 LobeHub 身份，不改写成沙箱路径。

## Alternatives considered

### Why not 把真实工具表传进 `render_turn`？

会重新画出 XML `<tools>`，和请求上的 native schema 打架。空目录是刻意的。环境说明不该靠「假装还有 XML 工具」才能出现。

### Why not 继续把 sandbox 塞在 `ToolsSection` 里，只拿掉空目录短路？

两个概念一个 section。下次再改目录策略，寻址会再丢一次。宪法里 `{tools}` 和 `{cloud_sandbox}` 本来就是两个占位符。

### Why not 把 `files_info` 的 url 改成 `/mnt/data/<name>`？

`files_info` 是 LobeHub 的下载身份。guest 路径由 `<uploaded_files>` 提供。混用一条通道，前端和沙箱会抢同一个字段。

## Consequences

首轮 system prompt 带 `/mnt/data` 和已同步附件的 guest 路径。模型不必用 `find /` 猜上传文件。XML `<tools>` 在 native 路径上仍为空。没有 FileStore 时渲染不炸，只是没有附件清单。

## Verification

`tests/cognition/test_prompt_surface.py`：空目录仍渲染 sandbox block。

`tests/lca/cognition/brain/test_reasoner_cloud_branch_renders_uploaded_files.py`：`tools=()` 时 guest 路径是 `/mnt/data/<文件名>`。

`tests/scenario/prompt/test_prompt_assembler_integration.py`：`think.reason.render` 生产路径上 `cloud_sandbox` 有工作根，`tools` 没有。
