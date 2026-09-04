"""Event delivery diagnostics — EventBus delivery counters (ADR-0184 D2).

Reads ``EventBus.default().delivery_snapshot()`` of the invoking process:
per-category ``published / persisted / delivered / dropped``. Counters are
process-local memory, not persisted; a standalone CLI process reports its
own bus snapshot (empty until that process publishes).
"""

from __future__ import annotations

import json

import typer

_COLUMNS = ("category", "published", "persisted", "delivered", "dropped")


def register(app: typer.Typer) -> None:
    """Register the events-delivery command on the typer app."""

    @app.command(name="events-delivery")
    def events_delivery_cmd(
        category: str = typer.Option(None, "--category", help="只看该 category"),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        policy: bool = typer.Option(
            False,
            "--policy",
            help="读 PersistenceObserver.fsync_policy（queue_depth n/a=0）",
        ),
    ) -> None:
        """打印本进程 EventBus 的投递计数器快照（published/persisted/delivered/dropped）。

        计数器是进程内内存（ADR-0184 D2），不落盘；独立 CLI 进程显示
        自己总线的快照，空 = 本进程未 publish 过。``--category`` 只
        保留该 category 的行（未出现过 = 空输出）。``--policy`` 切到
        PersistenceObserver 观测（不可用时优雅降级）。
        """
        from lca_kernel.events.bus import EventBus

        if policy:
            try:
                from lca_kernel.events.persistence import PersistenceObserver

                observer = PersistenceObserver.default()
                print(f"fsync_policy: {observer.fsync_policy.value}")
                print("queue_depth: 0")  # n/a: sync observer, no queue
            except (ImportError, AttributeError):
                print("PersistenceObserver not available")
            return

        snapshot = EventBus.default().delivery_snapshot()
        if category is not None:
            snapshot = {category: snapshot[category]} if category in snapshot else {}

        if json_mode:
            print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
            return

        if not snapshot:
            print("（无已发布事件：本进程投递计数器为空）")
            return

        rows: list[tuple[str, ...]] = []
        for cat in sorted(snapshot):
            counts = snapshot[cat]
            rows.append(
                (
                    cat,
                    str(counts["published"]),
                    str(counts["persisted"]),
                    str(counts["delivered"]),
                    str(counts["dropped"]),
                )
            )
        widths = [
            max(len(_COLUMNS[i]), *(len(row[i]) for row in rows)) for i in range(len(_COLUMNS))
        ]
        print("  ".join(col.ljust(widths[i]) for i, col in enumerate(_COLUMNS)))
        for row in rows:
            print("  ".join(row[i].ljust(widths[i]) for i in range(len(_COLUMNS))))
