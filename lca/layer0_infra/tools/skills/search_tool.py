"""search_skill — discover operational skills with three-level degradation."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.contracts.protocols.operational_skills import SkillImportError, SkillSearchResult
from lca.layer0_infra.search.service import any_search_provider_available
from lca.layer0_infra.search.skill_policy import filter_skill_search_result
from lca.layer0_infra.skills.http_importer import HttpSkillImporter
from lca.layer0_infra.tools.skills._format import format_skill_index_rows

SEARCH_SKILL_TOOL = "search_skill"

_DEGRADED_PREFIX = "（已放宽搜索条件）"
_SANDBOX_FALLBACK = "无匹配 skill。建议用 execute_code 直接编码实现，或尝试更简短的关键词重新搜索。"


class SkillSearchTool(Tool):
    name = SEARCH_SKILL_TOOL
    description = (
        "检索操作技能库（不会做的任务先搜这里）。"
        "优先查 LobeHub Market（需 market 鉴权：market-cli 凭证或 "
        "LCA_SKILL_MARKET_TOKEN / M2M client），否则搜本机已安装 skill。"
        "找到后用 import_skill 安装，再 activate_skill 加载指南。"
        "参数: query（任务关键词，空则列出本地已安装）、page、page_size。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词；空则列出本地已安装"},
            "page": {"type": "integer", "default": 1},
            "page_size": {"type": "integer", "default": 20},
        },
    }
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, importer: HttpSkillImporter) -> None:
        self._importer = importer

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        query = str(args.get("query") or "")
        page = int(args.get("page") or 1)
        page_size = int(args.get("page_size") or 20)

        result = await self._search_with_degradation(query, page, page_size)
        result = filter_skill_search_result(
            result,
            unified_search_available=any_search_provider_available(),
        )
        body = self._format_body(result)
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": body, "total": result.total},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )

    async def _search_with_degradation(
        self, query: str, page: int, page_size: int
    ) -> SkillSearchResult:
        """Three-level degradation: original → core terms → local installed."""
        # Level 1: original query
        result = await self._safe_search(query, page, page_size)
        if result is not None and result.items:
            return result

        # Level 2: extract core terms (first 2 words) and retry
        if query:
            core_terms = " ".join(query.split()[:2])
            if core_terms != query:
                degraded = await self._safe_search(core_terms, page, page_size)
                if degraded is not None and degraded.items:
                    return degraded

        # Level 3: list local installed skills
        local = self._importer.store.list_installed()
        if local:
            local_result = SkillSearchResult(
                items=local,
                total=len(local),
                page=1,
                page_size=len(local),
            )
            return filter_skill_search_result(
                local_result,
                unified_search_available=any_search_provider_available(),
            )

        # Fallback: empty result with guidance
        return SkillSearchResult(items=(), total=0, page=1, page_size=page_size)

    async def _safe_search(self, query: str, page: int, page_size: int) -> SkillSearchResult | None:
        """Search that returns None on error instead of raising."""
        try:
            return await self._importer.search_market(query, page=page, page_size=page_size)
        except SkillImportError:
            return None

    def _format_body(self, result: SkillSearchResult) -> str:
        if not result.items:
            return _SANDBOX_FALLBACK
        header = f"共 {result.total} 条（第 {result.page} 页）:\n"
        return header + format_skill_index_rows(result.items)
