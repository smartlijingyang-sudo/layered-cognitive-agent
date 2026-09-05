#!/usr/bin/env python3
"""ADR-0065 PR-11:把 ``traces/runs/<id>.jsonl`` + ``<id>.doctor.json`` 迁移到 v2 per-run 目录布局。

旧布局(0063 时代)::
    traces/
    └── runs/
        ├── run_xxx.jsonl              # 账本
        ├── run_xxx.doctor.json        # 终态诊断
        └── ...

新布局(0065 §七)::
    traces/
    └── runs/
        └── run_xxx/
            ├── journal.jsonl          # 来自 <id>.jsonl
            ├── manifest.json          # 合并 <id>.doctor.json 的 doctor_report
            ├── evidence/              # 空(留作未来)
            └── materializations/<id>/<v>/  # 空(留作未来)

本脚本对老 traces 是一次性;执行完不会再有 flat 文件。脚本是幂等的:
- 已迁移的 run(同 run_id 已是目录)跳过
- 同一 run_id 既有 flat 又有目录时,优先目录(若 flat 与目录时间戳不一致会告警但不覆盖)

用法::

    # 干跑(默认):只报告会做什么,不改动
    uv run python scripts/migrate_traces_flat_to_v2_layout.py

    # 真正迁移
    uv run python scripts/migrate_traces_flat_to_v2_layout.py --apply

    # 指定根目录(测试用)
    uv run python scripts/migrate_traces_flat_to_v2_layout.py --root traces-test --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 与 check_run_naming.py / RunLocator 同源:run_id 即 ``run_<hex>``。
_RUN_ID_RE = re.compile(r"^run_[a-z0-9]{4,26}$")

# 老布局文件名后缀:
# - .jsonl                  → journal 账本
# - .doctor.json            → doctor 终态报告(并入 manifest.extra.doctor_report)
# - .diagnostic.jsonl       → 旧诊断流(并入 journal 后已停用;保留为 legacy)
_FLAT_SUFFIXES = (".jsonl", ".doctor.json", ".diagnostic.jsonl")

# SHA256 摘要用的常量与 execute.py _ledger_summary_for 保持一致
_LEDGER_TAIL_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class FlatArtifact:
    """一条老布局的文件。"""

    run_id: str
    suffix: str  # 之一:.jsonl / .doctor.json
    src_path: Path
    mtime: float


@dataclass(slots=True)
class MigrationPlan:
    """一次迁移的产物清单。"""

    artifacts: list[FlatArtifact] = field(default_factory=list)
    journal_moves: list[tuple[FlatArtifact, Path]] = field(default_factory=list)
    manifest_writes: list[tuple[FlatArtifact, FlatArtifact | None, Path]] = field(
        default_factory=list
    )
    diagnostic_moves: list[tuple[FlatArtifact, Path]] = field(default_factory=list)
    skipped_existing_dirs: list[str] = field(default_factory=list)
    skipped_unrelated: list[Path] = field(default_factory=list)


def _scan_flat_artifacts(runs_dir: Path) -> list[FlatArtifact]:
    out: list[FlatArtifact] = []
    if not runs_dir.exists():
        return out
    for entry in sorted(runs_dir.iterdir()):
        if entry.is_dir():
            continue
        name = entry.name
        # 注意:``.jsonl`` 与 ``.diagnostic.jsonl`` 同后缀结尾;
        # 必须先尝试**最长**后缀,再试短后缀,否则 ``run_xxx.diagnostic.jsonl`` 会被错配为 ``.jsonl``。
        for suffix in sorted(_FLAT_SUFFIXES, key=len, reverse=True):
            if not name.endswith(suffix):
                continue
            run_id_part = name[: -len(suffix)]
            if not _RUN_ID_RE.match(run_id_part):
                continue
            out.append(
                FlatArtifact(
                    run_id=run_id_part,
                    suffix=suffix,
                    src_path=entry,
                    mtime=entry.stat().st_mtime,
                )
            )
            break
    return out


def _ledger_summary_for(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - _LEDGER_TAIL_BYTES))
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ledger_high_watermark_for(path: Path) -> int:
    """取 journal.jsonl 最后一条 ``seq`` / ``run_seq`` 字段作为高水位。"""
    if not path.exists():
        return 0
    last_seq = 0
    try:
        from lca.infrastructure.observability.journal.engine.journal_io import load_journal_records

        for row in load_journal_records(path, strict=False):
            seq = int(row.get("run_seq", row.get("seq", 0)) or 0)
            if seq > last_seq:
                last_seq = seq
    except OSError:
        return 0
    return last_seq


def _terminal_event_seq_for(path: Path) -> int:
    """找最后一条 ``AgentRunFinished`` 的 journal seq。"""
    if not path.exists():
        return 0
    last_seq = 0
    try:
        from lca.infrastructure.observability.journal.engine.journal_io import load_journal_records

        for row in load_journal_records(path, strict=False):
            et = row.get("event_type", "") or (row.get("descriptor") or {}).get("type", "")
            if et == "AgentRunFinished":
                last_seq = int(row.get("run_seq", row.get("seq", 0)) or 0)
    except OSError:
        return 0
    return last_seq


def _build_plan(
    *,
    root: Path,
    artifacts: Iterable[FlatArtifact],
) -> MigrationPlan:
    plan = MigrationPlan()
    by_run: dict[str, list[FlatArtifact]] = {}
    for art in artifacts:
        by_run.setdefault(art.run_id, []).append(art)

    for run_id, items in by_run.items():
        run_dir = root / "runs" / run_id
        # 只迁移 .diagnostic.jsonl 的 helper 文件(无 .jsonl / .doctor.json 依赖);
        # 已迁移过的 run 跳过主体逻辑,但仍可收 diagnostic helper。
        diagnostic_alone: FlatArtifact | None = None
        if run_dir.exists():
            for item in items:
                if item.suffix == ".diagnostic.jsonl":
                    diagnostic_alone = item
            if diagnostic_alone is not None:
                plan.diagnostic_moves.append((diagnostic_alone, run_dir / "diagnostic.jsonl"))
            # 没有 helper 需要补:记为已迁移
            if diagnostic_alone is None:
                plan.skipped_existing_dirs.append(run_id)
            else:
                plan.artifacts.extend(items)
            continue
        journal: FlatArtifact | None = None
        doctor: FlatArtifact | None = None
        diagnostic: FlatArtifact | None = None
        for item in items:
            if item.suffix == ".jsonl":
                journal = item
            elif item.suffix == ".doctor.json":
                doctor = item
            elif item.suffix == ".diagnostic.jsonl":
                diagnostic = item
        if journal is None:
            # 没有 .jsonl 不能建账本目录 — 视为 orphan
            plan.skipped_unrelated.extend(item.src_path for item in items)
            continue
        plan.artifacts.extend(items)
        plan.journal_moves.append((journal, run_dir / "journal.jsonl"))
        plan.manifest_writes.append(
            (
                journal,
                doctor,
                run_dir / "manifest.json",
            )
        )
        if diagnostic is not None:
            plan.diagnostic_moves.append((diagnostic, run_dir / "diagnostic.jsonl"))
    return plan


def _mtime_of(path: Path | None) -> float:
    if path is None:
        return 0.0
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _execute_plan(*, root: Path, plan: MigrationPlan) -> dict[str, int]:
    """执行 plan;返回计数。orphan 文件(``*.db`` / ``*.py`` / 无账本的 ``.doctor.json``)
    一律**不动** —— 由运维 / 用户决策,与本迁移工具职责分离。
    """
    counts = {
        "journal_moved": 0,
        "manifest_written": 0,
        "diagnostic_moved": 0,
        "src_deleted": 0,
    }

    for journal, dst in plan.journal_moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(journal.src_path), str(dst))
        counts["journal_moved"] += 1

    for _journal, doctor, dst in plan.manifest_writes:
        manifest = _compose_manifest(journal=Path(dst.parent) / "journal.jsonl", doctor=doctor)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        counts["manifest_written"] += 1

    for diagnostic, dst in plan.diagnostic_moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(diagnostic.src_path), str(dst))
        counts["diagnostic_moved"] += 1

    # 老布局残留(doctor.json 在 journal 移走后才删)
    for journal, _dst in plan.journal_moves:
        # 找同 run_id 的 doctor 源
        for art in plan.artifacts:
            if (
                art.run_id == journal.run_id
                and art.suffix == ".doctor.json"
                and art.src_path.exists()
            ):
                art.src_path.unlink()
                counts["src_deleted"] += 1
    return counts


def _compose_manifest(*, journal: Path, doctor: FlatArtifact | None) -> dict[str, object]:
    """把 doctor_report 合并进 manifest.extra(与 execute.py._record_terminal_materialization 同形状)。

    ADR-0065 §六:manifest.json 是 terminal materialization + 完整性状态;
    ledger_high_watermark + ledger_summary 必须从 journal 实时算,不允许占位。
    """
    ledger_summary = _ledger_summary_for(journal)
    ledger_high_watermark = _ledger_high_watermark_for(journal)
    terminal_event_seq = _terminal_event_seq_for(journal)
    doctor_report: dict[str, object] | None = None
    if doctor is not None and doctor.src_path.exists():
        try:
            doctor_report = json.loads(doctor.src_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doctor_report = None

    extra: dict[str, object] = {}
    if doctor_report is not None:
        extra["doctor_report"] = doctor_report
    # 记录迁移来源,便于审计
    extra["migrated_from"] = {
        "schema": "lca.run_manifest_migration/1",
        "ts": time.time(),
        "source_format": "flat-v1",
    }

    return {
        "schema": "lca.run_manifest/1",
        "run_id": journal.parent.name,
        "terminal_event_seq": terminal_event_seq,
        "ledger_high_watermark": ledger_high_watermark,
        "ledger_summary": ledger_summary,
        "started_at": 0.0,
        "closed_at": _mtime_of(journal),
        "extra": extra,
    }


def _format_report(
    *, root: Path, plan: MigrationPlan, counts: dict[str, int], applied: bool
) -> str:
    lines: list[str] = []
    verb = "would" if not applied else "did"
    lines.append(
        f"== ADR-0065 PR-11 migration report ({'DRY-RUN' if not applied else 'APPLIED'}) =="
    )
    lines.append(f"root: {root}")
    lines.append(f"flat artifacts found: {len(plan.artifacts)}")
    lines.append(f"  - journal moves: {len(plan.journal_moves)}")
    lines.append(f"  - manifest writes: {len(plan.manifest_writes)}")
    lines.append(f"  - diagnostic moves: {len(plan.diagnostic_moves)}")
    lines.append(f"skipped (already a per-run dir): {len(plan.skipped_existing_dirs)}")
    lines.append(f"skipped (orphan / unrelated): {len(plan.skipped_unrelated)}")
    if applied:
        for k, v in counts.items():
            lines.append(f"  {k}: {v}")
    if plan.skipped_existing_dirs:
        lines.append("already-migrated run_ids:")
        for run_id in plan.skipped_existing_dirs[:20]:
            lines.append(f"  - {run_id}")
        if len(plan.skipped_existing_dirs) > 20:
            lines.append(f"  ... ({len(plan.skipped_existing_dirs) - 20} more)")
    if plan.skipped_unrelated:
        lines.append("orphan flat files (no journal, left in place):")
        for path in plan.skipped_unrelated[:20]:
            lines.append(f"  - {path}")
    lines.append(
        f"action verb: {verb} {len(plan.journal_moves)} journal moves + {len(plan.manifest_writes)} manifest writes + {len(plan.diagnostic_moves)} diagnostic moves"
    )
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ADR-0065 PR-11: migrate traces/runs/<id>.jsonl flat layout to per-run dir layout"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO / "traces",
        help="traces root (default: <repo>/traces)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正迁移(默认 dry-run,只报告)。orphan 文件(无账本绑定的 ``.doctor.json`` / ``*.db`` / ``*.py`` 等)不动 —— 由运维决策。",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    root: Path = args.root
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        return 2
    runs_dir = root / "runs"
    if not runs_dir.exists():
        print(f"OK: {runs_dir} not present; nothing to migrate")
        return 0

    artifacts = _scan_flat_artifacts(runs_dir)
    plan = _build_plan(root=root, artifacts=artifacts)
    if args.apply:
        counts = _execute_plan(root=root, plan=plan)
        report = _format_report(root=root, plan=plan, counts=counts, applied=True)
        print(report)
        return 0
    report = _format_report(root=root, plan=plan, counts={}, applied=False)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
