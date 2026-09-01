"""Journal migrate: 一次性把老 journal.jsonl 迁移到 step-tree (ADR-0164 Phase 6)。

用法:
    lca-ops journal migrate <run_id>              # 迁移单个 run
    lca-ops journal migrate --all                # 迁移所有有 journal.jsonl 的 run
    lca-ops journal migrate <run_id> --dry-run    # 不写文件, 只打 stats

迁移结果:
    + traces/runs/<id>/journal.json          (lca.journal/3, 标 migration_inferred=true)
    + traces/runs/<id>/journal.narrative.md  (StepNarrativeWriter 产出)
    ? traces/runs/<id>/journal.jsonl         (保留, 不动, 是迁移源)

启发式见 lca.infrastructure.observability.journal.step.migrate.JournalMigrator。
不保证 100% 准确(老事件可能丢失 detail), 但保留所有 step 边界 / context_before / tool_call / tool_result。
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from lca.infrastructure.observability.journal.step.migrate import (
    iter_run_ids,
    migrate_run,
)

_DEFAULT_TRACES_ROOT = Path("traces")  # CLI 默认 traces 根目录


def _migrate_one(traces_root: Path, run_id: str, *, dry_run: bool) -> None:
    if dry_run:
        from lca.infrastructure.observability.journal.engine.journal_io import (
            load_journal_records,
        )

        jsonl_path = traces_root / "runs" / run_id / "journal.jsonl"
        if not jsonl_path.exists():
            print(f"  - {run_id}: no journal.jsonl")
            return
        records = list(load_journal_records(jsonl_path, strict=False))
        schemas = {r.get("schema") for r in records}
        # ADR-0164 Phase 6: 当前只支持 v2 → step-tree 迁移
        # v1 数据更老, 提示但不报错
        unsupported = schemas - frozenset({"lca.journal/2", None})
        if unsupported:
            print(
                f"  - {run_id}: {len(records)} records, "
                f"schemas={schemas} (unsupported: {unsupported}, 跳过)"
            )
            return
        print(f"  - {run_id}: {len(records)} records, schemas={schemas}")
        return
    try:
        journal_path, narrative_path = migrate_run(traces_root, run_id)
    except FileNotFoundError as exc:
        print(f"  - {run_id}: {exc}", file=sys.stderr)
        return
    print(f"  + {run_id}: {journal_path} + {narrative_path}")


def register(app: typer.Typer) -> None:
    """Register the migrate command under the ``journal`` group."""

    @app.command(name="migrate")
    def migrate_cmd(
        run_id: str = typer.Argument("", help="run_id(空 + --all 时跑所有)"),
        all_runs: bool = typer.Option(False, "--all", help="迁移所有有 journal.jsonl 的 run"),
        dry_run: bool = typer.Option(False, "--dry-run", help="不写文件, 只统计 records / schema"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """把 journal.jsonl(v2 stream) 迁移到 journal.json(step-tree)。

        不删原 journal.jsonl, 是迁移源。 migration 标记 metadata.migration_inferred=true。
        """
        if not all_runs and not run_id:
            print("error: 传 run_id 或 --all", file=sys.stderr)
            raise SystemExit(1)
        if dry_run:
            print(f"# dry-run mode, traces_root={traces_root}")
        if all_runs:
            ids = list(iter_run_ids(traces_root))
            print(f"# migrating {len(ids)} runs (all_runs=True, dry_run={dry_run})")
            for rid in ids:
                _migrate_one(traces_root, rid, dry_run=dry_run)
            return
        _migrate_one(traces_root, run_id, dry_run=dry_run)


__all__ = ["register"]
