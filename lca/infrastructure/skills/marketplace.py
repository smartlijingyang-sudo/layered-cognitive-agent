"""LobeHub Market HTTP client — search (auth) + public download/detail."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from lca.contracts.protocols.memory.operational_skills import (
    SkillImportError,
    SkillIndexEntry,
    SkillSearchResult,
)
from lca.infrastructure.skills.market_auth import (
    clear_market_token_cache,
    market_auth_setup_hint,
    resolve_market_access_token,
)
from lca.infrastructure.skills.settings import SkillSettings, get_skill_settings

_IDENTIFIERS_CACHE_NAME = "market_identifiers.json"
_IDENTIFIERS_TTL_S = 24 * 60 * 60
_IDENTIFIERS_TIMEOUT_S = 180.0
_MAX_IDENTIFIER_MATCHES = 500


class LobeHubMarketClient:
    """Thin client for ``market.lobehub.com`` skill APIs."""

    def __init__(self, settings: SkillSettings | None = None) -> None:
        self._settings = settings if settings is not None else get_skill_settings()

    def download_url(self, identifier: str) -> str:
        base = self._settings.market_base_url.rstrip("/")
        return f"{base}/api/v1/skills/{identifier}/download"

    def detail_url(self, identifier: str) -> str:
        base = self._settings.market_base_url.rstrip("/")
        return f"{base}/api/v1/skills/{identifier}"

    async def _auth_headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = await resolve_market_access_token(self._settings, force_refresh=force_refresh)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def download_zip(self, identifier: str) -> bytes:
        url = self.download_url(identifier)
        timeout = httpx.Timeout(self._settings.market_timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                raise SkillImportError(f"Market 下载失败: {exc}") from exc
        if response.status_code >= 400:
            raise SkillImportError(
                f"Market 下载 HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.content
        if not data:
            raise SkillImportError("Market 下载为空")
        return data

    async def fetch_detail(self, identifier: str) -> dict[str, Any]:
        url = self.detail_url(identifier)
        timeout = httpx.Timeout(self._settings.market_timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url, headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                raise SkillImportError(f"Market 详情失败: {exc}") from exc
        if response.status_code >= 400:
            raise SkillImportError(
                f"Market 详情 HTTP {response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise SkillImportError("Market 详情响应格式无效")
        return payload

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> SkillSearchResult:
        headers = await self._auth_headers()
        if "Authorization" not in headers:
            raise SkillImportError(market_auth_setup_hint())

        try:
            return await self._search_list_api(
                query, page=page, page_size=page_size, headers=headers
            )
        except SkillImportError as list_err:
            # M2M tokens currently work on /identifiers but list/search may 401
            # (also observed with @lobehub/market-cli). Fall back to catalog filter.
            try:
                return await self._search_via_identifiers(
                    query, page=page, page_size=page_size, headers=headers
                )
            except SkillImportError:
                raise list_err from None

    async def _search_list_api(
        self,
        query: str,
        *,
        page: int,
        page_size: int,
        headers: dict[str, str],
    ) -> SkillSearchResult:
        base = self._settings.market_base_url.rstrip("/")
        url = urljoin(f"{base}/", "api/v1/skills")
        params: dict[str, str | int] = {
            "q": query,
            "page": max(1, page),
            "pageSize": max(1, min(page_size, 100)),
        }
        timeout = httpx.Timeout(self._settings.market_timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise SkillImportError(f"Market 搜索失败: {exc}") from exc
            if response.status_code == 401:
                clear_market_token_cache()
                headers = await self._auth_headers(force_refresh=True)
                if "Authorization" not in headers:
                    raise SkillImportError(market_auth_setup_hint())
                try:
                    response = await client.get(url, params=params, headers=headers)
                except httpx.HTTPError as exc:
                    raise SkillImportError(f"Market 搜索失败: {exc}") from exc
        if response.status_code >= 400:
            raise SkillImportError(
                f"Market 搜索 HTTP {response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise SkillImportError("Market 搜索响应格式无效")
        return self._parse_list_payload(payload, page=page, page_size=page_size)

    def _parse_list_payload(
        self,
        payload: dict[str, Any],
        *,
        page: int,
        page_size: int,
    ) -> SkillSearchResult:
        raw_items = payload.get("items")
        items_list = raw_items if isinstance(raw_items, list) else []
        entries: list[SkillIndexEntry] = []
        for row in items_list:
            if not isinstance(row, dict):
                continue
            identifier = str(row.get("identifier") or "").strip()
            if not identifier:
                continue
            entries.append(
                SkillIndexEntry(
                    skill_id=identifier,
                    name=str(row.get("name") or identifier),
                    summary=str(row.get("description") or row.get("summary") or ""),
                    source_url=self.download_url(identifier),
                    version=str(row.get("version") or ""),
                )
            )
        total_raw = payload.get("totalCount", payload.get("total", len(entries)))
        try:
            total = int(total_raw)
        except (TypeError, ValueError):
            total = len(entries)
        page_raw = payload.get("currentPage", payload.get("page", page))
        try:
            current_page = int(page_raw)
        except (TypeError, ValueError):
            current_page = page
        size_raw = payload.get("pageSize", page_size)
        try:
            current_size = int(size_raw)
        except (TypeError, ValueError):
            current_size = page_size
        return SkillSearchResult(
            items=tuple(entries),
            total=total,
            page=current_page,
            page_size=current_size,
        )

    def _identifiers_cache_path(self) -> Path:
        root = Path(self._settings.cache_dir)
        root.mkdir(parents=True, exist_ok=True)
        return root / _IDENTIFIERS_CACHE_NAME

    def _load_identifiers_cache(self) -> list[str] | None:
        path = self._identifiers_cache_path()
        if not path.is_file():
            return None
        try:
            if time.time() - path.stat().st_mtime > _IDENTIFIERS_TTL_S:
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, list):
            return None
        out = [str(x) for x in raw if isinstance(x, str) and x.strip()]
        return out or None

    def _save_identifiers_cache(self, identifiers: list[str]) -> None:
        path = self._identifiers_cache_path()
        path.write_text(
            json.dumps(identifiers, ensure_ascii=False),
            encoding="utf-8",
        )

    async def _fetch_identifiers(self, headers: dict[str, str]) -> list[str]:
        cached = self._load_identifiers_cache()
        if cached is not None:
            return cached
        base = self._settings.market_base_url.rstrip("/")
        url = urljoin(f"{base}/", "api/v1/skills/identifiers")
        timeout = httpx.Timeout(_IDENTIFIERS_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise SkillImportError(f"Market identifiers 失败: {exc}") from exc
            if response.status_code == 401:
                clear_market_token_cache()
                headers = await self._auth_headers(force_refresh=True)
                if "Authorization" not in headers:
                    raise SkillImportError(market_auth_setup_hint())
                try:
                    response = await client.get(url, headers=headers)
                except httpx.HTTPError as exc:
                    raise SkillImportError(f"Market identifiers 失败: {exc}") from exc
        if response.status_code >= 400:
            raise SkillImportError(
                f"Market identifiers HTTP {response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
        if not isinstance(payload, list):
            raise SkillImportError("Market identifiers 响应格式无效")
        identifiers: list[str] = []
        for row in payload:
            if isinstance(row, str) and row.strip():
                identifiers.append(row.strip())
            elif isinstance(row, dict):
                ident = str(row.get("identifier") or "").strip()
                if ident:
                    identifiers.append(ident)
        if not identifiers:
            raise SkillImportError("Market identifiers 为空")
        self._save_identifiers_cache(identifiers)
        return identifiers

    async def _search_via_identifiers(
        self,
        query: str,
        *,
        page: int,
        page_size: int,
        headers: dict[str, str],
    ) -> SkillSearchResult:
        identifiers = await self._fetch_identifiers(headers)
        tokens = [t for t in query.lower().split() if t]
        if not tokens:
            matches = identifiers
        else:
            matches = [
                ident for ident in identifiers if all(tok in ident.lower() for tok in tokens)
            ]
        matches = matches[:_MAX_IDENTIFIER_MATCHES]
        page = max(1, page)
        size = max(1, min(page_size, 100))
        start = (page - 1) * size
        slice_ids = matches[start : start + size]
        entries = tuple(
            SkillIndexEntry(
                skill_id=ident,
                name=ident,
                summary="(catalog match; activate after import for full description)",
                source_url=self.download_url(ident),
                version="",
            )
            for ident in slice_ids
        )
        return SkillSearchResult(
            items=entries,
            total=len(matches),
            page=page,
            page_size=size,
        )
