"""Assistant governed memory tools (ADR-0246 PR-6).

Model-facing tools for the assistant's memory. Record writes go through
``AssistantMemory`` (``upsert`` / ``supersede`` / ``remove``), which enforces
dedupe_key idempotency and supersede lifecycle. Person and group pages are
Markdown under the context-file layout, not rows in that store. The tools
run through the C10 Body → SafeExecutor narrow door like every other tool.
No tool writes Home config files or USER.md directly.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType, MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.service.groups import GroupsDirectory
from lca.infrastructure.memory.contextfiles.service.people import PeopleDirectory

_MEMORY_SEARCH_TOOL = "memory_search"
_MEMORY_ADD_TOOL = "memory_add"
_MEMORY_UPDATE_TOOL = "memory_update"
_MEMORY_REMOVE_TOOL = "memory_remove"
_MEMORY_EXPLAIN_TOOL = "memory_explain"
_PERSON_NOTE_TOOL = "person_note"
_GROUP_NOTE_TOOL = "group_note"

_SENSITIVE_CONFIRMATION_HINT = (
    "这是敏感操作，必须先经用户确认：调用 askUserQuestion 询问用户是否确认，"
    "用户明确同意后才可携带 confirmed=true 再次调用。"
)


class _BaseMemoryTool(Tool):
    """Shared scaffolding for the memory tools."""

    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, *, memory: AssistantMemory) -> None:
        self._memory = memory

    def _ok(self, start: float, payload: dict[str, Any] | None, text: str = "") -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=payload,
            content_type=ContentType.STRUCTURED if payload else ContentType.TEXT,
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def _fail(self, start: float, message: str) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=message,
            latency_ms=int((time.monotonic() - start) * 1000),
            extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
        )


class MemorySearchTool(_BaseMemoryTool):
    """Search the assistant's structured memory (read-only)."""

    name = _MEMORY_SEARCH_TOOL
    required_grant: ClassVar[str] = "profile.revise"
    description = (
        "搜索当前助理的结构化记忆（身份/偏好/事实）。只读，不修改任何数据。"
        "参数: query（关键词）、limit（可选，最多返回条数，默认 5）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "最多返回条数（默认 5）"},
        },
        "required": ["query"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        query = str(args.get("query") or "").strip()
        if not query:
            return self._fail(start, "query 必须为非空字符串")
        try:
            limit = max(1, min(50, int(args.get("limit") or 5)))
        except (TypeError, ValueError):
            limit = 5
        records = self._memory.query(MemoryLayer.SEMANTIC) + self._memory.query(
            MemoryLayer.EPISODIC
        )
        lowered = query.lower()
        terms = [t for t in lowered.split() if t]

        def _score(r: MemoryRecord) -> int:
            content_lower = r.content.lower()
            key_lower = (r.dedupe_key or "").lower()
            cat_lower = r.category.value.lower()
            target = f"{content_lower} {key_lower} {cat_lower}"
            score = 10 if (query in r.content or lowered in content_lower) else 0
            for t in terms:
                if t in target:
                    score += 2
            return score

        scored = [(r, _score(r)) for r in records]
        scored_matched = [item for item in scored if item[1] > 0]
        scored_matched.sort(key=lambda item: item[1], reverse=True)
        matched = [item[0] for item in scored_matched][:limit]
        return self._ok(
            start,
            {
                "query": query,
                "count": len(matched),
                "records": [
                    {
                        "record_id": r.record_id,
                        "category": r.category.value,
                        "content": r.content,
                        "dedupe_key": r.dedupe_key,
                        "created_at_ms": r.created_at_ms,
                    }
                    for r in matched
                ],
            },
        )


class MemoryAddTool(_BaseMemoryTool):
    """Add a structured memory record (governed write)."""

    name = _MEMORY_ADD_TOOL
    required_grant: ClassVar[str] = "profile.revise"
    description = (
        "把用户明确陈述的身份/偏好/事实写入结构化记忆。"
        "参数: content（结构化事实，如「用户身份：系统架构师」）、category（identity/"
        "preference/fact）、dedupe_key（可选，属性维度键，如 preference:tech_stack、identity:role，"
        "同维度新事实会自动覆盖旧事实，严禁包含具体取值）。"
        "非敏感操作，改完告知用户。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "结构化事实内容"},
            "category": {
                "type": "string",
                "enum": ["identity", "preference", "fact"],
                "description": "记忆类别",
            },
            "dedupe_key": {
                "type": "string",
                "description": "可选属性维度键（如 preference:tech_stack、identity:role，严禁包含具体取值）",
            },
        },
        "required": ["content", "category"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        content = str(args.get("content") or "").strip()
        category_raw = str(args.get("category") or "").strip()
        if not content:
            return self._fail(start, "content 必须为非空字符串")
        try:
            category = MemoryCategory(category_raw)
        except ValueError:
            return self._fail(
                start, f"未知 category={category_raw!r}，必须是 identity/preference/fact"
            )
        dedupe_key = str(args.get("dedupe_key") or "").strip() or None
        record = MemoryRecord(
            record_id=new_id("mem"),
            content=content,
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=category,
            dedupe_key=dedupe_key,
            confidence=1.0,
            metadata={"source": "user"},
        )
        persisted = self._memory.upsert(record)
        await self._memory.refresh_user_profile()
        return self._ok(
            start,
            {
                "record_id": persisted.record_id,
                "category": persisted.category.value,
                "content": persisted.content,
                "message": f"已记录 {category.value} 记忆。",
            },
        )


class MemoryUpdateTool(_BaseMemoryTool):
    """Supersede an existing memory record with a corrected fact."""

    name = _MEMORY_UPDATE_TOOL
    required_grant: ClassVar[str] = "profile.revise"
    description = (
        "用新事实替换一条已有记忆记录（旧记录标记 superseded，保留审计）。"
        "参数: record_id（要替换的记录 id）、content（新事实）、category（可选）、"
        "dedupe_key（可选，默认自动继承旧记录维度键）。非敏感操作，改完告知用户。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "record_id": {"type": "string", "description": "要替换的记录 id"},
            "content": {"type": "string", "description": "新的事实内容"},
            "category": {
                "type": "string",
                "enum": ["identity", "preference", "fact"],
                "description": "记忆类别（可选，默认 fact）",
            },
            "dedupe_key": {
                "type": "string",
                "description": "可选属性维度键（默认继承旧记录键，同维度替换）",
            },
        },
        "required": ["record_id", "content"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        record_id = str(args.get("record_id") or "").strip()
        content = str(args.get("content") or "").strip()
        if not record_id:
            return self._fail(start, "record_id 必须为非空字符串")
        if not content:
            return self._fail(start, "content 必须为非空字符串")
        category_raw = str(args.get("category") or "fact").strip()
        try:
            category = MemoryCategory(category_raw)
        except ValueError:
            return self._fail(start, f"未知 category={category_raw!r}")
        dedupe_key = str(args.get("dedupe_key") or "").strip() or None
        replacement = MemoryRecord(
            record_id=new_id("mem"),
            content=content,
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=category,
            dedupe_key=dedupe_key,
            confidence=1.0,
            metadata={"source": "user"},
        )
        persisted = self._memory.supersede(record_id, replacement)
        await self._memory.refresh_user_profile()
        return self._ok(
            start,
            {
                "record_id": persisted.record_id,
                "supersedes": record_id,
                "message": f"已更新记忆（替换 {record_id}）。",
            },
        )


class MemoryExplainTool(_BaseMemoryTool):
    """Expand one memory record into its eight audit fields."""

    name = _MEMORY_EXPLAIN_TOOL
    is_idempotent = True
    required_grant: ClassVar[str] = "profile.revise"
    description = (
        "展开一条记忆的出处。只读。"
        "返回 claim、kind、salience、attribution、quote、timeline、confidence、supersession_chain。"
        "参数: record_id（memory_search 返回的记录 id）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "record_id": {"type": "string", "description": "要展开的记录 id"},
        },
        "required": ["record_id"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        record_id = str(args.get("record_id") or "").strip()
        if not record_id:
            return self._fail(start, "record_id 必须为非空字符串")
        explained = self._memory.explain(record_id)
        if explained is None:
            return self._fail(start, f"没有记录 {record_id}")
        return self._ok(
            start,
            {
                "record_id": record_id,
                "claim": explained.claim,
                "kind": explained.kind,
                "salience": explained.salience,
                "attribution": explained.attribution,
                "quote": explained.quote,
                "timeline": explained.timeline,
                "confidence": explained.confidence,
                "supersession_chain": list(explained.supersession_chain),
            },
        )


class PersonNoteTool(_BaseMemoryTool):
    """Write one person page under the assistant home and refresh the index."""

    name = _PERSON_NOTE_TOOL
    required_grant: ClassVar[str] = "profile.revise"
    description = (
        "记下一个人。按当前主目录的上下文布局写入人物页，并重写人物索引。"
        "参数: name（显示名）、note（关于这个人的话）。同名会覆盖。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "人物显示名"},
            "note": {"type": "string", "description": "关于这个人的话"},
        },
        "required": ["name", "note"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        name = str(args.get("name") or "").strip()
        note = str(args.get("note") or "").strip()
        if not name or not note:
            return self._fail(start, "name 和 note 都必须为非空字符串")
        layout = layout_for_home(self._memory.home_path)
        try:
            page = PeopleDirectory(
                DiskFileStore(self._memory.home_path),
                layout=layout,
            ).upsert(name, note)
        except ValueError as exc:
            return self._fail(start, str(exc))
        except OSError as exc:
            return self._fail(start, f"人物页没有写入: {exc}")
        return self._ok(
            start,
            {"slug": page.slug, "name": page.name, "path": layout.person_page_path(page.slug)},
        )


class GroupNoteTool(_BaseMemoryTool):
    """Write one group page under the assistant home and refresh the index."""

    name = _GROUP_NOTE_TOOL
    required_grant: ClassVar[str] = "profile.revise"
    description = (
        "记下一个群体。按当前主目录的上下文布局写入群体页，并重写群体索引。"
        "参数: name（显示名）、note（关于这个群体的话）。同名会覆盖。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "群体显示名"},
            "note": {"type": "string", "description": "关于这个群体的话"},
        },
        "required": ["name", "note"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        name = str(args.get("name") or "").strip()
        note = str(args.get("note") or "").strip()
        if not name or not note:
            return self._fail(start, "name 和 note 都必须为非空字符串")
        layout = layout_for_home(self._memory.home_path)
        try:
            page = GroupsDirectory(
                DiskFileStore(self._memory.home_path),
                layout=layout,
            ).upsert(name, note)
        except ValueError as exc:
            return self._fail(start, str(exc))
        except OSError as exc:
            return self._fail(start, f"群体页没有写入: {exc}")
        return self._ok(
            start,
            {"slug": page.slug, "name": page.name, "path": layout.group_page_path(page.slug)},
        )


class MemoryRemoveTool(_BaseMemoryTool):
    """Remove a memory record (sensitive, requires confirmation)."""

    name = _MEMORY_REMOVE_TOOL
    required_grant: ClassVar[str] = "profile.revise"
    description = (
        "删除一条记忆记录（不可逆，敏感操作）。必须先经用户确认。"
        "参数: record_id（要删除的记录 id）、confirmed（用户是否已确认，必须为 true）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "record_id": {"type": "string", "description": "要删除的记录 id"},
            "confirmed": {
                "type": "boolean",
                "description": "用户是否已明确确认删除（敏感操作必须为 true）",
            },
        },
        "required": ["record_id", "confirmed"],
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        record_id = str(args.get("record_id") or "").strip()
        if not record_id:
            return self._fail(start, "record_id 必须为非空字符串")
        if args.get("confirmed") is not True:
            return self._fail(start, f"删除记忆需要用户确认。{_SENSITIVE_CONFIRMATION_HINT}")
        self._memory.remove(record_id)
        await self._memory.refresh_user_profile()
        return self._ok(
            start,
            {
                "removed_record_id": record_id,
                "message": f"已删除记忆「{record_id}」。",
            },
        )


def assistant_memory_tools_from_run(
    run: object | None,
    *,
    catalog: object,
    profile_backfill: object | None = None,
) -> list[Tool]:
    """物化受治理记忆工具；run 绑定 assistant_id 时出现。

    ``catalog`` 只用于解析 assistant Home 路径；记忆读写全部走
    ``AssistantMemory`` typed 存储。``profile_backfill`` 是 ADR-0246 PR-5
    的可选异步回调，经工具写入身份/偏好事实后同样触发 USER.md 回填。
    """
    from lca.contracts.protocols.assistant.catalog import AssistantCatalog
    from lca.infrastructure.observability.facade.run.ambit import current_assistant_id

    if not isinstance(catalog, AssistantCatalog):
        return []
    if run is None:
        explicit = ""
    elif isinstance(run, dict):
        explicit = str(run.get("assistant_id") or "").strip()
    else:
        explicit = str(getattr(run, "assistant_id", "") or "").strip()
    assistant_id = explicit or current_assistant_id().strip()
    if not assistant_id:
        return []
    try:
        spec = catalog.get(assistant_id)
        memory = AssistantMemory(spec.home_path, profile_backfill=profile_backfill)
    except Exception:
        return []
    return [
        MemorySearchTool(memory=memory),
        MemoryAddTool(memory=memory),
        MemoryUpdateTool(memory=memory),
        MemoryRemoveTool(memory=memory),
        MemoryExplainTool(memory=memory),
        PersonNoteTool(memory=memory),
        GroupNoteTool(memory=memory),
    ]


__all__ = [
    "_MEMORY_ADD_TOOL",
    "_MEMORY_REMOVE_TOOL",
    "_MEMORY_SEARCH_TOOL",
    "_MEMORY_UPDATE_TOOL",
    "GroupNoteTool",
    "MemoryAddTool",
    "MemoryExplainTool",
    "MemoryRemoveTool",
    "MemorySearchTool",
    "MemoryUpdateTool",
    "PersonNoteTool",
    "assistant_memory_tools_from_run",
]
