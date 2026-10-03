"""SQLite 派生索引器：FTS5 全文检索与关系图拓扑 (ADR-0277 派生中枢)。

只读派生索引，删除后可根据 Markdown SSOT 秒级全量重建。
支持 CJK 中英文分词与短语检索。
"""

from __future__ import annotations

import collections
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from lca.infrastructure.memory.contextfiles.domain.search import rank_document, tokenize


@dataclass(frozen=True)
class EntitySearchResult:
    domain: str
    slug: str
    content: str
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    is_archived: bool


class EntityGraphIndexer:
    """实体图谱 SQLite 索引器（FTS5 + 关系表）。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    domain TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    aliases TEXT NOT NULL,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    updated_at_ms INTEGER NOT NULL,
                    PRIMARY KEY (domain, slug)
                );
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                    domain,
                    slug,
                    searchable,
                    tokenize='unicode61'
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entity_relations (
                    source_slug TEXT NOT NULL,
                    target_slug TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    PRIMARY KEY (source_slug, target_slug, relation_type)
                );
                """
            )
            conn.commit()

    def index_entity(
        self,
        domain: str,
        slug: str,
        content: str,
        tags: tuple[str, ...] = (),
        aliases: tuple[str, ...] = (),
        relations: dict[str, str] | None = None,
        is_archived: bool = False,
        updated_at_ms: int = 0,
    ) -> None:
        tags_str = ", ".join(tags)
        aliases_str = ", ".join(aliases)
        searchable_text = " ".join(tokenize(f"{domain} {slug} {content} {tags_str} {aliases_str}"))

        with self._get_connection() as conn:
            # 1. 插入实体主表
            conn.execute(
                """
                INSERT OR REPLACE INTO entities (domain, slug, content, tags, aliases, is_archived, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    domain,
                    slug,
                    content,
                    tags_str,
                    aliases_str,
                    1 if is_archived else 0,
                    updated_at_ms,
                ),
            )

            # 2. 刷新 FTS5
            conn.execute(
                "DELETE FROM entities_fts WHERE domain = ? AND slug = ?;",
                (domain, slug),
            )
            conn.execute(
                """
                INSERT INTO entities_fts (domain, slug, searchable)
                VALUES (?, ?, ?);
                """,
                (domain, slug, searchable_text),
            )

            # 3. 刷新关系
            if relations is not None:
                conn.execute(
                    "DELETE FROM entity_relations WHERE source_slug = ?;",
                    (slug,),
                )
                for target_slug, rel_type in relations.items():
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO entity_relations (source_slug, target_slug, relation_type)
                        VALUES (?, ?, ?);
                        """,
                        (slug, target_slug, rel_type),
                    )

            conn.commit()

    def mark_archived(self, domain: str, slug: str, is_archived: bool = True) -> None:
        """更新实体的归档状态标记。"""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE entities SET is_archived = ? WHERE domain = ? AND slug = ?;",
                (1 if is_archived else 0, domain, slug),
            )
            conn.commit()

    def search(self, query: str, limit: int = 10) -> list[EntitySearchResult]:
        """全文检索实体（采用分词与多词项高精度匹配）。"""
        terms = tokenize(query)
        if not terms:
            return []

        # 优先使用 AND 精确交集匹配
        and_clause = " AND ".join(f'"{t}"' for t in terms)

        rows = self._execute_fts(and_clause, limit=limit)
        if not rows and len(terms) > 1:
            # 回退使用 OR 容错匹配
            or_clause = " OR ".join(f'"{t}"' for t in terms)
            rows = self._execute_fts(or_clause, limit=limit)

        results: list[EntitySearchResult] = []
        for r in rows:
            tags = tuple(t.strip() for t in r["tags"].split(",") if t.strip())
            aliases = tuple(a.strip() for a in r["aliases"].split(",") if a.strip())
            results.append(
                EntitySearchResult(
                    domain=r["domain"],
                    slug=r["slug"],
                    content=r["content"],
                    tags=tags,
                    aliases=aliases,
                    is_archived=bool(r["is_archived"]),
                )
            )

        # 二次按 rank_document 排序保证最贴合的置顶
        results.sort(
            key=lambda x: rank_document(terms, f"{x.slug} {x.content} {' '.join(x.tags)}"),
            reverse=True,
        )
        return results[:limit]

    def _execute_fts(self, match_clause: str, limit: int) -> list[sqlite3.Row]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT e.domain, e.slug, e.content, e.tags, e.aliases, e.is_archived
                FROM entities_fts f
                JOIN entities e ON e.domain = f.domain AND e.slug = f.slug
                WHERE entities_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
                """,
                (match_clause, limit),
            )
            return cursor.fetchall()

    def find_relation_path(
        self, source_slug: str, target_slug: str, max_hops: int = 2
    ) -> list[tuple[str, str, str]] | None:
        """BFS 遍历实体多跳关系链。"""
        if source_slug == target_slug:
            return []

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT source_slug, target_slug, relation_type FROM entity_relations;"
            )
            rows = cursor.fetchall()

        # 构建邻接表
        graph: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
        for r in rows:
            graph[r["source_slug"]].append((r["target_slug"], r["relation_type"]))

        # BFS 寻路
        queue = collections.deque([(source_slug, [])])
        visited = {source_slug}

        while queue:
            current, path = queue.popleft()
            if len(path) >= max_hops:
                continue

            for neighbor, rel_type in graph[current]:
                next_path = [*path, (current, neighbor, rel_type)]
                if neighbor == target_slug:
                    return next_path
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, next_path))

        return None
