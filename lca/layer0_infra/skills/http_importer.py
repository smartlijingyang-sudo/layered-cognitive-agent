"""HTTP skill importer — Market / GitHub / ZIP / Markdown sources."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

import httpx

from lca.contracts.protocols.operational_skills import (
    SkillImporter,
    SkillImportError,
    SkillIndexEntry,
    SkillPackage,
    SkillPackageInstaller,
    SkillSearchResult,
)
from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore, sanitize_skill_id
from lca.layer0_infra.skills.frontmatter import skill_title, split_frontmatter
from lca.layer0_infra.skills.marketplace import LobeHubMarketClient
from lca.layer0_infra.skills.settings import SkillSettings, get_skill_settings
from lca.layer0_infra.skills.url_sources import (
    ParsedSkillUrl,
    github_raw_url,
    is_host_allowed,
    parse_skill_url,
)
from lca.layer0_infra.skills.zip_security import (
    extract_zip_bytes,
    find_skill_markdown,
    list_resource_paths,
)


class HttpSkillImporter(SkillImporter):
    """Fetch skill packages from network and persist through the installer seam."""

    def __init__(
        self,
        store: SkillPackageInstaller | None = None,
        market: LobeHubMarketClient | None = None,
        settings: SkillSettings | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_skill_settings()
        self._store = store if store is not None else DiskSkillPackageStore(self._settings)
        self._market = market if market is not None else LobeHubMarketClient(self._settings)

    @property
    def store(self) -> SkillPackageInstaller:
        return self._store

    async def search_market(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> SkillSearchResult:
        q = query.strip()
        if not q:
            local = self._search_local("")
            return SkillSearchResult(
                items=local,
                total=len(local),
                page=1,
                page_size=max(page_size, len(local) or 1),
            )
        try:
            return await self._market.search(q, page=page, page_size=page_size)
        except SkillImportError:
            local = self._search_local(q)
            if local:
                return SkillSearchResult(
                    items=local,
                    total=len(local),
                    page=1,
                    page_size=len(local),
                )
            from lca.layer0_infra.skills.market_auth import market_auth_setup_hint

            raise SkillImportError(
                "Market 搜索不可用且本地无匹配 skill。\n" + market_auth_setup_hint()
            ) from None

    async def import_from_market(self, identifier: str) -> SkillPackage:
        ident = identifier.strip()
        if not ident:
            raise SkillImportError("identifier 不能为空")
        detail: dict[str, Any] = {}
        try:
            detail = await self._market.fetch_detail(ident)
        except SkillImportError:
            detail = {}
        zip_bytes = await self._market.download_zip(ident)
        files = extract_zip_bytes(zip_bytes)
        skill_key, skill_bytes = find_skill_markdown(files)
        skill_text = skill_bytes.decode("utf-8", errors="replace")
        resource_paths = list_resource_paths(files, skill_key)
        resources = {rel: files[rel] for rel in resource_paths}
        version = str(detail.get("version") or "")
        return self._store.install_package(
            skill_id=sanitize_skill_id(ident),
            skill_md_text=skill_text,
            resource_files=resources,
            source_url=self._market.download_url(ident),
            version=version,
        )

    async def import_from_url(self, url: str, *, kind: str = "auto") -> SkillPackage:
        parsed = parse_skill_url(url, kind=kind)
        if parsed.kind == "market" and parsed.market_identifier:
            return await self.import_from_market(parsed.market_identifier)
        if not is_host_allowed(parsed.url, self._settings.allowed_hosts):
            raise SkillImportError(f"主机不在允许列表内: {parsed.url}")
        if parsed.kind == "zip":
            data = await self._fetch_bytes(parsed.url)
            files = extract_zip_bytes(data)
            skill_key, skill_bytes = find_skill_markdown(files)
            skill_text = skill_bytes.decode("utf-8", errors="replace")
            meta, _ = split_frontmatter(skill_text)
            skill_id = sanitize_skill_id(skill_title(meta, PurePosixPath(parsed.url).stem))
            resource_paths = list_resource_paths(files, skill_key)
            resources = {rel: files[rel] for rel in resource_paths}
            return self._store.install_package(
                skill_id=skill_id,
                skill_md_text=skill_text,
                resource_files=resources,
                source_url=parsed.url,
            )
        if parsed.kind == "github_dir":
            return await self._import_github_dir(parsed)
        if parsed.kind in {"github_file", "raw", "markdown", "url"}:
            return await self._import_single_markdown(parsed.url)
        raise SkillImportError(f"不支持的 URL 类型: {parsed.kind}")

    async def _import_github_dir(self, parsed: ParsedSkillUrl) -> SkillPackage:
        base_path = parsed.path.strip("/")
        candidates = [
            f"{base_path}/SKILL.md" if base_path else "SKILL.md",
            f"{base_path}/skill.md" if base_path else "skill.md",
        ]
        last_error = ""
        for candidate in candidates:
            raw_url = github_raw_url(parsed.owner, parsed.repo, parsed.ref, candidate)
            try:
                text = await self._fetch_text(raw_url)
            except SkillImportError as exc:
                last_error = str(exc)
                continue
            skill_id = sanitize_skill_id(f"{parsed.owner}-{parsed.repo}-{base_path or 'root'}")
            meta, _ = split_frontmatter(text)
            skill_id = sanitize_skill_id(skill_title(meta, skill_id))
            return self._store.install_package(
                skill_id=skill_id,
                skill_md_text=text,
                resource_files={},
                source_url=parsed.url,
            )
        raise SkillImportError(last_error or "GitHub 目录中未找到 SKILL.md")

    async def _import_single_markdown(self, url: str) -> SkillPackage:
        text = await self._fetch_text(url)
        meta, _ = split_frontmatter(text)
        fallback = PurePosixPath(url).stem or "skill"
        skill_id = sanitize_skill_id(skill_title(meta, fallback))
        return self._store.install_package(
            skill_id=skill_id,
            skill_md_text=text,
            resource_files={},
            source_url=url,
        )

    async def _fetch_bytes(self, url: str) -> bytes:
        timeout = httpx.Timeout(self._settings.market_timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                raise SkillImportError(f"下载失败: {exc}") from exc
        if response.status_code >= 400:
            raise SkillImportError(f"下载 HTTP {response.status_code}: {response.text[:300]}")
        return response.content

    async def _fetch_text(self, url: str) -> str:
        data = await self._fetch_bytes(url)
        return data.decode("utf-8", errors="replace")

    def _search_local(self, query: str) -> tuple[SkillIndexEntry, ...]:
        q = query.strip().lower()
        hits: list[SkillIndexEntry] = []
        for entry in self._store.list_installed():
            if not q:
                hits.append(entry)
                continue
            hay = f"{entry.skill_id} {entry.name} {entry.summary}".lower()
            if q in hay:
                hits.append(entry)
        return tuple(hits)
