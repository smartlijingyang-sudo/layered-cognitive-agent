# Agent Note: BackstorySection 收敛为 standing 注入标记的单发射器

Status: implemented

## Problem

`BackstorySection` 在渲染提示词 backstory 段时，曾对已经带 `INJECTED FILE` 注入标记的 standing 文本再次包一层 `<!-- INJECTED FILE: SOUL.md -->` 块。当 `role_profile.backstory` 来自 `persona_from_home`（`lca/plugins/assistant/persona/persona.py` 经 `assemble_standing` 产出，`runnable_assembly.py:169-173` 把它放入 `RoleProfile.backstory`）时，同一份 standing 文本在输出里出现两次：一次在 `BACKSTORY:` 标签行内，一次在新包裹的 SOUL.md 块内。每份 standing 文件的 `INJECTED FILE` 标记也因此出现两次，初始渲染浪费约一半的 backstory 预算。

## Decision

`BackstorySection.render`（`lca/plugins/prompts/sections/role.py`）只输出 `label_line('BACKSTORY', text)`，不再包裹新的 `<!-- INJECTED FILE: SOUL.md -->` 块。standing 文本自带的注入标记由 `assemble_standing` / `render_injected` 发射，直接暴露在 `BACKSTORY:` 标签下（标签与 SOUL.md 起始标记同行），`refresh_injected` 在后续轮次原位替换这些块。

`refresh_injected`（`lca/infrastructure/memory/contextfiles/domain/standing.py`）对任意嵌套或重复输入都收敛到每 name 恰好一块，END 按 name 匹配，函数是自身不动点。`tests/infrastructure/memory/test_standing_preservation.py` 的嵌套、重复、无主 END 回归测试保留为对该防御性行为的验证。

## Verification

- `tests/plugins/assistant/test_soul_to_prompt.py` 断言 standing backstory 渲染输出中 `<!-- INJECTED FILE: SOUL.md -->` 恰好出现一次。
- `tests/runtime/test_adr0255_muse_runtime_conformance.py` T1 断言绑定 Home 的 backstory 渲染只发射一次 SOUL.md 标记，空 backstory 输出为空。
- `tests/infrastructure/memory/test_standing_refresh_inline_marker.py` 钉住 `BACKSTORY:` 标签与起始标记同行的形状。
- `tests/infrastructure/memory/test_standing_preservation.py` 覆盖 `refresh_injected` 对重复、嵌套、无主 END 的收敛。

## Consequences

- 初始 system prompt 的 backstory 段只包含每份 standing 文件的一份拷贝，字符数约为修复前的一半。
- `BACKSTORY:` 标签、`_PERSONA_INJECTION_WARNING` 位置、空 backstory 行为均不变。
- `RoleProfile` / `SectionOutput` 契约与 Profile 拓扑不变。

## Alternatives considered

### Why not 保留外层包裹，继续依赖 `refresh_injected` 折叠？

`refresh_injected` 能折叠嵌套输入，但初始渲染仍会把每份 standing 文件复制两次，浪费 backstory 预算，每次刷新还要做额外折叠。保留第二发射器等于保留已知浪费源头，与"一个事实一个生产者"相悖。

### Why not 让 `BackstorySection` 在非 standing backstory 时也发射 SOUL.md 块？

那是修复前行为。纯文本 backstory 没有注入标记，`refresh_injected` 不会替换它；发射一个磁盘上不存在的 SOUL.md 块属于指称幻觉，`test_adr0255` T1 在空 backstory 场景防御这一点。