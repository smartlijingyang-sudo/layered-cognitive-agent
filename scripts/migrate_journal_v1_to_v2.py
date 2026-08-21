#!/usr/bin/env python3
"""migrate_journal_v1_to_v2 —— ADR-0065 PR-3 v1 → v2 升级工具。

将旧 ``journal.v1`` JSONL 升级到 ``journal.v2`` (JournalRecord) 形态。
**不动 ``*_preview`` 字段**:旧 trace 内容本就缺失,迁移只补 envelope 字段
(`schema` / `event_id` / `run_seq` / `occurred_at` / `committed_at` /
`causation` / `descriptor`),完整载荷补录由消费方逐步完成。

用法::

    python scripts/migrate_journal_v1_to_v2.py <input.jsonl> <output.jsonl>
    python scripts/migrate_journal_v1_to_v2.py --in-place <input.jsonl>   # 覆盖原文件

退出码:
    0  成功
    1  输入格式错误(非 JSONL)
    2  schema tag 已是 v2(无需迁移)
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

V1_SCHEMA = "lca.journal/1"
V2_SCHEMA = "lca.journal/2"


def _migrate_record(record: dict[str, Any]) -> dict[str, Any]:
    """单条 v1 → v2 升级;补 envelope 字段,保留 data / scope 原样。"""
    scope_raw = record.get("scope", {}) or {}
    scope = {
        "trace_id": str(scope_raw.get("trace_id", "")),
        "run_id": str(scope_raw.get("run_id", "")),
        "parent_run_id": scope_raw.get("parent_run_id"),
        "parent_trace_id": scope_raw.get("parent_trace_id"),
        "delegation_id": scope_raw.get("delegation_id"),
        "agent_role": str(scope_raw.get("agent_role", "")),
        "step": int(scope_raw.get("step", 0)),
    }
    ts = float(record.get("ts", 0.0))
    seq = int(record.get("seq", 0))
    event_id = str(record.get("event_id", "")) or f"evt_{uuid.uuid4().hex[:12]}"
    return {
        "schema": V2_SCHEMA,
        "event_id": event_id,
        "run_id": scope["run_id"],
        "run_seq": seq,
        "occurred_at": ts,
        "committed_at": ts,
        "scope": scope,
        "causation": {
            "parent_event_id": "",
            "links": [],
        },
        "descriptor": {
            "type": str(record.get("event_type", "")),
            "version": 1,
            "payload_schema_version": 1,
        },
        "data": dict(record.get("data", {}) or {}),
        "evidence": [],
    }


def migrate_file(input_path: Path, output_path: Path | None) -> int:
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        return 1

    target = output_path if output_path is not None else input_path
    in_place = output_path is None

    # in-place 模式:先读全部到内存,再原子覆盖;避免 in-place 模式下读到半
    # 截断文件的 race。
    if in_place:
        records = input_path.read_text(encoding="utf-8")
        migrated = 0
        skipped_v2 = 0
        errors = 0
        out_lines: list[str] = []
        for line_no, line in enumerate(records.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                print(
                    f"ERROR: line {line_no} not JSON: {exc}",
                    file=sys.stderr,
                )
                errors += 1
                continue
            schema = str(record.get("schema", ""))
            if schema == V2_SCHEMA:
                out_lines.append(json.dumps(record, ensure_ascii=False))
                skipped_v2 += 1
                continue
            if schema and schema != V1_SCHEMA:
                print(
                    f"WARN: line {line_no} unknown schema={schema!r}; passthrough",
                    file=sys.stderr,
                )
                out_lines.append(json.dumps(record, ensure_ascii=False))
                continue
            upgraded = _migrate_record(record)
            out_lines.append(json.dumps(upgraded, ensure_ascii=False))
            migrated += 1
        input_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print(
            f"migrated={migrated} skipped_v2={skipped_v2} errors={errors} output={input_path}"
        )
        return 1 if errors > 0 else 0

    migrated = 0
    skipped_v2 = 0
    errors = 0
    with (
        input_path.open("r", encoding="utf-8") as src,
        target.open("w", encoding="utf-8") as dst,
    ):
            for line_no, line in enumerate(src, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    print(
                        f"ERROR: line {line_no} not JSON: {exc}",
                        file=sys.stderr,
                    )
                    errors += 1
                    continue
                schema = str(record.get("schema", ""))
                if schema == V2_SCHEMA:
                    # 已是 v2 —— 原样写回
                    dst.write(json.dumps(record, ensure_ascii=False) + "\n")
                    skipped_v2 += 1
                    continue
                if schema and schema != V1_SCHEMA:
                    # 未知 schema —— 警告但原样透传
                    print(
                        f"WARN: line {line_no} unknown schema={schema!r}; passthrough",
                        file=sys.stderr,
                    )
                    dst.write(json.dumps(record, ensure_ascii=False) + "\n")
                    continue
                upgraded = _migrate_record(record)
                dst.write(json.dumps(upgraded, ensure_ascii=False) + "\n")
                migrated += 1

    print(f"migrated={migrated} skipped_v2={skipped_v2} errors={errors} output={target}")
    if errors > 0:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("input", type=Path, help="v1 JSONL input path")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="v2 JSONL output path (omit for in-place)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite input file in place",
    )
    args = parser.parse_args(argv)
    output = None if args.in_place else args.output
    return migrate_file(args.input, output)


if __name__ == "__main__":
    sys.exit(main())
