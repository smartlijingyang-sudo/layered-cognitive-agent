"""Journal migrate: 一次性把老 journal.jsonl 迁移到 step-tree (ADR-0164 Phase 6)，
以及 lca.journal/3 → 3.1 的 schema 升级 (ADR-0167 D11)。

用法:
    lca-ops journal migrate <run_id>                  # 迁移单个 run
    lca-ops journal migrate --all                    # 迁移所有有 journal.jsonl 的 run
    lca-ops journal migrate <run_id> --dry-run        # 不写文件, 只打 stats

    lca-ops journal migrate-to-3-1 <run_id>           # 升级 lca.journal/3 → 3.1
    lca-ops journal migrate-to-3-1 --all              # 升级所有 3.0 文档

迁移结果:
    + traces/runs/<id>/journal.json          (lca.journal/3, 标 migration_inferred=true)
    + traces/runs/<id>/journal.narrative.md  (StepNarrativeWriter 产出)
    ? traces/runs/<id>/journal.jsonl         (保留, 不动, 是迁移源)

3.0 → 3.1:
    就地覆盖 journal.json；同步重写 narrative.md；totals + phases 字段补齐。
    idempotent：已是 3.1 的 run 直接跳过。

启发式见 lca.infrastructure.observability.journal.step.migrate.JournalMigrator /
upgrade_to_3_1。
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from lca.infrastructure.observability.journal.step.migrate import (
    iter_run_ids,
    migrate_run,
    migrate_to_3_1,
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
    """Register the migrate commands under the ``journal`` group."""

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

    @app.command(name="migrate-to-3-1")
    def migrate_to_3_1_cmd(
        run_id: str = typer.Argument("", help="run_id(空 + --all 时跑所有)"),
        all_runs: bool = typer.Option(False, "--all", help="升级所有 lca.journal/3 文档"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """把 lca.journal/3 step 树就地升级到 3.1（totals + phases 显式数组）。

        idempotent：已是 3.1 的 run 自动跳过。原 journal.jsonl 保留不动。
        """
        if not all_runs and not run_id:
            print("error: 传 run_id 或 --all", file=sys.stderr)
            raise SystemExit(1)
        runs_root = traces_root / "runs"
        targets: list[str] = []
        if all_runs:
            for run_dir in sorted(runs_root.iterdir()):
                if run_dir.is_dir():
                    targets.append(run_dir.name)
        else:
            targets = [run_id]
        upgraded = 0
        skipped = 0
        for rid in targets:
            path = migrate_to_3_1(traces_root, rid)
            if path is None:
                skipped += 1
                continue
            upgraded += 1
            print(f"  + {rid}: {path} (schema=lca.journal/3.1)")
        print(
            f"# migrate-to-3-1 done: upgraded={upgraded} skipped={skipped} "
            f"(skipped = 已是 3.1 或无 journal.json)"
        )


__all__ = ["register"]
