"""ADR-0185 fold 章节渲染器 —— 从 FoldedModelVisible 派生 5 个章节
(🧰 Tools / 🎯 Skills / 📚 Sections / 💬 Context items / 🧠 Reasoning)。

fold = None 时每个子渲染器显式降级到 N/A 占位;``FoldProvider`` seam
类型也在此定义。渲染结果由 ``writer._render_step`` 组装进 narrative。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from lca.infrastructure.observability.journal.step.narrative_writer.sections import (
    _short,
)

if TYPE_CHECKING:
    from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

# Fold provider seam —— 每 step 调一次;返回 None 表示 fold SSOT 不可用,
# narrative 应优雅降级到 N/A 占位(不抛错、不影响其它章节)。test 用 mock
# callable 注入;production 走默认 ``fold_model_visible``(读 spine.jsonl)。
FoldProvider = Callable[[str, str], "FoldedModelVisible | None"]

# ── Fold 章节(ADR-0185 PR-3.1 narrative 增强) ── ──

_FOLD_NA = "_N/A (fold SSOT 不可用)_"
"""fold_provider 返回 None 时的占位串;章节数 / 标题保留,内容降级。"""


def _tool_name(tool: object) -> str:
    """tool schema 的 name 字段,降级回退 attribute / key。"""
    if isinstance(tool, Mapping):
        value = tool.get("name")
        if value is not None:
            return str(value)
        fn = tool.get("function")
        if isinstance(fn, Mapping):
            nested = fn.get("name")
            if nested is not None:
                return str(nested)
    return getattr(tool, "name", None) or "<unnamed>"


def _tool_description(tool: object) -> str:
    """tool schema 的 description,缺失降级空串。"""
    if isinstance(tool, Mapping):
        value = tool.get("description")
        if value is None:
            fn = tool.get("function")
            if isinstance(fn, Mapping):
                value = fn.get("description")
    else:
        value = getattr(tool, "description", None)
    return str(value) if value is not None else ""


def _render_tools_sent(fold: FoldedModelVisible | None) -> list[str]:
    """🧰 Tools sent to model(N) —— fold.header.tools 列表渲染。

    fold = None ⇒ 整段显示 N/A 占位(不抛错)。
    tools 为空 ⇒ 标题后显式「(空,本 step 未下发工具)」。
    """
    if fold is None or fold.header is None:
        return [f"**🧰 Tools sent to model(0)** — {_FOLD_NA}"]
    tools = fold.header.tools or ()
    lines = [f"**🧰 Tools sent to model({len(tools)})**"]
    if not tools:
        lines.append("- _(空,本 step 未下发工具)_")
        return lines
    for tool in tools:
        name = _tool_name(tool)
        desc = _short(_tool_description(tool), 60)
        if desc:
            lines.append(f"- `{name}` — {desc}")
        else:
            lines.append(f"- `{name}`")
    return lines


def _render_skills_activated(fold: FoldedModelVisible | None) -> list[str]:
    """🎯 Skills activated(N) —— fold.manifest.activated_skill_ids + available_skills_count。

    manifest 缺 / skill_router 未启用 ⇒ 显式标注「SkillRouter 未启用」。
    有 catalog 但无激活 ⇒ 标注「无匹配 (catalog=N)」。
    """
    if fold is None or fold.header is None:
        return [f"**🎯 Skills activated(0)** — {_FOLD_NA}"]
    manifest = fold.manifest or {}
    if "activated_skill_ids" not in manifest and "available_skills_count" not in manifest:
        return ["**🎯 Skills activated** — SkillRouter 未启用或本 step 未触发 prompt assembler"]
    activated = manifest.get("activated_skill_ids") or []
    catalog_count = manifest.get("available_skills_count")
    lines = [f"**🎯 Skills activated({len(activated)})**"]
    if catalog_count is not None:
        lines.append(f"- catalog 总数: {catalog_count}")
    if activated:
        for sid in activated:
            lines.append(f"- `{sid}`")
    else:
        if catalog_count:
            lines.append("- _(无匹配 / SkillRouter 已启用但本 step 未选中)_")
        else:
            lines.append("- _(SkillRouter 已启用,catalog 空)_")
    return lines


def _render_prompt_sections(fold: FoldedModelVisible | None) -> list[str]:
    """📚 Sections in prompt(N) —— fold.manifest.sections 列表渲染。

    字段:name + text_chars + content_digest 前 16(碰撞足够区分)。
    sections 缺失 ⇒ 标注「未携带 section trace(reasoner 降级路径)」。
    """
    if fold is None or fold.header is None:
        return [f"**📚 Sections in prompt(0)** — {_FOLD_NA}"]
    manifest = fold.manifest or {}
    sections = manifest.get("sections")
    if sections is None:
        return [
            "**📚 Sections in prompt** — 未携带 section trace(reasoner 降级路径或非 think step)"
        ]
    lines = [f"**📚 Sections in prompt({len(sections)})**"]
    for section in sections:
        if not isinstance(section, Mapping):
            lines.append(f"- {_short(section, 100)}")
            continue
        name = section.get("name", "<unnamed>")
        text_chars = section.get("text_chars")
        digest = section.get("content_digest") or ""
        digest_short = str(digest)[:16] if digest else "—"
        chars_str = f"{text_chars}" if text_chars is not None else "?"
        line = f"- `{name}` — text_chars={chars_str} digest={digest_short}"
        if section.get("skipped_empty"):
            line += " (skipped_empty)"
        if section.get("used_fallback"):
            line += " (used_fallback)"
        lines.append(line)
    return lines


def _render_context_items(fold: FoldedModelVisible | None) -> list[str]:
    """💬 Context items(N) —— fold.manifest.context_manifest_items 列表渲染。

    每项 kind + payload_preview[:120];无 manifest 路径 ⇒ 标注降级。
    """
    if fold is None or fold.header is None:
        return [f"**💬 Context items(0)** — {_FOLD_NA}"]
    manifest = fold.manifest or {}
    items = manifest.get("context_manifest_items")
    if items is None:
        return ["**💬 Context items** — 未携带 context_manifest(not Hub 路径 / 降级)"]
    lines = [f"**💬 Context items({len(items)})**"]
    for item in items:
        if not isinstance(item, Mapping):
            lines.append(f"- {_short(item, 120)}")
            continue
        kind = item.get("kind", "<unknown>")
        preview = _short(item.get("payload_preview", ""), 120)
        if preview:
            lines.append(f"- `{kind}` — {preview}")
        else:
            lines.append(f"- `{kind}`")
    return lines


def _render_reasoning_per_step(fold: FoldedModelVisible | None) -> list[str]:
    """🧠 Reasoning per step —— SpineLlmRequestHeaderAssistantPayload.assistant_content。

    fold.assistant 为 None ⇒ 标注「assistant payload 缺失」;空字符串
    视为「模型直接调用工具 / 无文字回复」。
    """
    if fold is None or fold.header is None:
        return [f"**🧠 Reasoning per step** — {_FOLD_NA}"]
    assistant = fold.assistant
    if assistant is None:
        return ["**🧠 Reasoning per step** — assistant payload 缺失(post hook 未跑 / skip)"]
    content = getattr(assistant, "assistant_content", "") or ""
    if not content:
        return ["**🧠 Reasoning per step** — _(空,模型直接调用工具 / 无文字回复)_"]
    # 不截断 reasoning;落地即为真值(总字数限制在调用方 enforce)
    return ["**🧠 Reasoning per step**", "", content]


def _render_fold_chapters(
    fold: FoldedModelVisible | None,
    *,
    char_budget: int = 4000,
) -> list[str]:
    """聚合 5 个 fold 章节;超 char_budget 时整体截断。

    budget = 每 step 允许的 fold 章节总字数(per task spec);默认 4000。
    """
    sections: list[list[str]] = [
        _render_tools_sent(fold),
        _render_skills_activated(fold),
        _render_prompt_sections(fold),
        _render_context_items(fold),
        _render_reasoning_per_step(fold),
    ]
    out: list[str] = []
    used = 0
    truncated = False
    for section in sections:
        body = "\n".join(section)
        section_chars = len(body) + 1  # +1 for join newline
        if used + section_chars > char_budget and out:
            truncated = True
            break
        out.extend(section)
        out.append("")
        used += section_chars
    if truncated:
        out.append(f"_… (后续 fold 章节因 {char_budget} 字符上限截断;详见 fold SSOT)_")
    # 去掉末尾多余空行
    while out and out[-1] == "":
        out.pop()
    return out
