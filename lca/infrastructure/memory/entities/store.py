"""开放实体知识图谱存储适配器 (EntityGraphStore - File-as-SSOT)。

负责实体 Markdown 文件的读写、开放动态领域目录管理、GRAPH.md 微索引维护与沉降 GC 淘汰。
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .indexer import EntityGraphIndexer, EntitySearchResult


class EntityGraphStore:
    """实体图谱存储中枢（File-as-SSOT 唯一真值管理）。"""

    def __init__(
        self,
        root_path: Path | str | None = None,
        max_active_entities: int = 50,
        max_graph_entries: int = 15,
        *,
        base_dir: Path | str | None = None,
    ) -> None:
        target_path = root_path if root_path is not None else base_dir
        if target_path is None:
            raise ValueError("Either root_path or base_dir must be provided")
        self.root_path = Path(target_path)
        self.max_active_entities = max_active_entities
        self.max_graph_entries = max_graph_entries

        self.entities_dir = self.root_path / "memory/entities"
        self.archives_dir = self.root_path / "memory/archives/entities"
        self.graph_md_path = self.entities_dir / "GRAPH.md"
        self.index_db_path = self.root_path / "index/memory.sqlite3"

        self.entities_dir.mkdir(parents=True, exist_ok=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)

        self._indexer = EntityGraphIndexer(self.index_db_path)

    def write_entity(
        self,
        domain: str,
        slug: str,
        content: str,
        tags: tuple[str, ...] = (),
        aliases: tuple[str, ...] = (),
        relations: dict[str, str] | None = None,
    ) -> None:
        """写入或更新实体页面（纯净 Markdown），并同步微索引与派生库。"""
        domain_clean = domain.strip().lower()
        slug_clean = slug.strip().lower()

        domain_dir = self.entities_dir / domain_clean
        domain_dir.mkdir(parents=True, exist_ok=True)

        entity_file = domain_dir / f"{slug_clean}.md"

        # 序列化为自解释 Markdown
        lines = [f"# {slug_clean}"]
        if tags:
            lines.append(f"- tags: {', '.join(tags)}")
        if aliases:
            lines.append(f"- aliases: {', '.join(aliases)}")
        if relations:
            rel_strs = [f"{target}:{rel}" for target, rel in relations.items()]
            lines.append(f"- relations: {', '.join(rel_strs)}")
        lines.append("")
        lines.append(content.strip())
        lines.append("")

        entity_file.write_text("\n".join(lines), encoding="utf-8")

        # 检查并执行 GC 沉降（如果活跃实体超出预算）
        self._enforce_budget_and_gc()

        # 更新常驻微索引 GRAPH.md
        self._refresh_graph_micro_index()

        # 同步更新 SQLite 派生索引
        now_ms = int(time.time() * 1000)
        self._indexer.index_entity(
            domain=domain_clean,
            slug=slug_clean,
            content=content,
            tags=tags,
            aliases=aliases,
            relations=relations,
            is_archived=False,
            updated_at_ms=now_ms,
        )

    save_entity = write_entity

    def read_entity(self, domain: str, slug: str) -> str | None:
        """读取实体内容（优先活跃目录，其次归档目录）。"""
        active_path = self.entities_dir / domain / f"{slug}.md"
        if active_path.is_file():
            return active_path.read_text(encoding="utf-8")

        archive_path = self.archives_dir / domain / f"{slug}.md"
        if archive_path.is_file():
            return archive_path.read_text(encoding="utf-8")

        return None

    def delete_entity(self, domain: str, slug: str) -> bool:
        """物理删除实体文件（含活跃与归档），并清除 SQLite 派生索引与微索引（右忘/遗忘）。"""
        deleted = False
        active_file = self.entities_dir / domain / f"{slug}.md"
        if active_file.is_file():
            active_file.unlink()
            deleted = True
        archive_file = self.archives_dir / domain / f"{slug}.md"
        if archive_file.is_file():
            archive_file.unlink()
            deleted = True

        if deleted:
            self._indexer.delete_entity(domain, slug)
            self._refresh_graph_micro_index()
        return deleted

    def search_entities(self, query: str, limit: int = 10) -> list[EntitySearchResult]:
        """通过 SQLite 派生索引全文检索实体。"""
        return self._indexer.search(query=query, limit=limit)

    def get_relation_path(
        self, source_slug: str, target_slug: str, max_hops: int = 2
    ) -> list[tuple[str, str, str]] | None:
        """查询两实体之间的关系扩散路径。"""
        return self._indexer.find_relation_path(source_slug, target_slug, max_hops)

    def get_active_graph_index(self) -> str:
        """获取 GRAPH.md 常驻微索引文本。"""
        if self.graph_md_path.is_file():
            return self.graph_md_path.read_text(encoding="utf-8")
        return ""

    def rebuild_derived_index(self) -> None:
        """从 Markdown SSOT 物理全量重建 SQLite 派生索引。"""
        self._indexer = EntityGraphIndexer(self.index_db_path)

        # 遍历活跃与归档的所有 .md 文件
        all_dirs = [(self.entities_dir, False), (self.archives_dir, True)]
        for base_dir, is_archived in all_dirs:
            if not base_dir.exists():
                continue
            for domain_path in base_dir.iterdir():
                if not domain_path.is_dir():
                    continue
                domain = domain_path.name
                for file_path in domain_path.glob("*.md"):
                    if file_path.name == "GRAPH.md":
                        continue
                    slug = file_path.stem
                    parsed = self._parse_entity_file(file_path)
                    self._indexer.index_entity(
                        domain=domain,
                        slug=slug,
                        content=parsed["content"],
                        tags=parsed["tags"],
                        aliases=parsed["aliases"],
                        relations=parsed["relations"],
                        is_archived=is_archived,
                        updated_at_ms=int(file_path.stat().st_mtime * 1000),
                    )

    def _parse_entity_file(self, file_path: Path) -> dict[str, object]:
        text = file_path.read_text(encoding="utf-8")
        tags: list[str] = []
        aliases: list[str] = []
        relations: dict[str, str] = {}
        content_lines: list[str] = []

        in_header = True
        for line in text.splitlines():
            line_s = line.strip()
            if in_header:
                if line_s.startswith("# "):
                    continue
                if line_s.startswith("- tags:"):
                    tags_str = line_s[len("- tags:") :].strip()
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                    continue
                if line_s.startswith("- aliases:"):
                    aliases_str = line_s[len("- aliases:") :].strip()
                    aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
                    continue
                if line_s.startswith("- relations:"):
                    rel_str = line_s[len("- relations:") :].strip()
                    for item in rel_str.split(","):
                        if ":" in item:
                            t_slug, rel = item.split(":", 1)
                            relations[t_slug.strip()] = rel.strip()
                    continue
                if line_s == "":
                    in_header = False
                    continue
            content_lines.append(line)

        return {
            "tags": tuple(tags),
            "aliases": tuple(aliases),
            "relations": relations,
            "content": "\n".join(content_lines).strip(),
        }

    def _enforce_budget_and_gc(self) -> None:
        """检查活跃实体数，超出上限则沉降淘汰至 archives/entities/。"""
        entity_files: list[tuple[float, Path]] = []
        for domain_dir in self.entities_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            for f in domain_dir.glob("*.md"):
                if f.name == "GRAPH.md":
                    continue
                entity_files.append((f.stat().st_mtime, f))

        if len(entity_files) <= self.max_active_entities:
            return

        # 按 mtime 升序排列（最旧的优先沉降）
        entity_files.sort(key=lambda x: x[0])
        num_to_evict = len(entity_files) - self.max_active_entities

        for _, file_path in entity_files[:num_to_evict]:
            domain = file_path.parent.name
            slug = file_path.stem
            dest_dir = self.archives_dir / domain
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / file_path.name
            file_path.rename(dest_file)
            self._indexer.mark_archived(domain, slug, is_archived=True)

    def _refresh_graph_micro_index(self) -> None:
        """刷新常驻视界的 GRAPH.md 微索引（控制在 max_graph_entries 范围内）。"""
        active_entries: list[tuple[float, str, str, str, tuple[str, ...]]] = []
        for domain_dir in self.entities_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            domain = domain_dir.name
            for f in domain_dir.glob("*.md"):
                if f.name == "GRAPH.md":
                    continue
                parsed = self._parse_entity_file(f)
                content = str(parsed["content"])
                snippet = (
                    re.sub(r"\s+", " ", content)[:40] + "..." if len(content) > 40 else content
                )
                mtime = f.stat().st_mtime
                tags = tuple(parsed["tags"])  # type: ignore[assignment]
                active_entries.append((mtime, domain, f.stem, snippet, tags))

        # 按 mtime 降序（最新/最高激活度的排前面）
        active_entries.sort(key=lambda x: x[0], reverse=True)
        top_entries = active_entries[: self.max_graph_entries]

        lines = ["# Entity Graph Micro-Index (Top Active Entities)"]
        for _, domain, slug, snippet, tags in top_entries:
            tag_suffix = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"- {domain}/{slug}: {snippet}{tag_suffix}")

        lines.append("")
        self.graph_md_path.write_text("\n".join(lines), encoding="utf-8")
