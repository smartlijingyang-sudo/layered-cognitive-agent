"""``lca-ops assistants`` — Assistant lifecycle CLI（ADR-0187 §3 D7）。

创建/查看助理走 REST 薄封装（真值在 ``AssistantCatalog``，经
``routes_assistants``）；``soul-history/diff/rollback`` 与 ``relink-skills``
是内容级回滚 / 技能升级的维护命令，直接进程内读 Home 并调用 catalog 与
skill overlay（与 ``memory`` 命令同构），因为这些写路径尚无 REST 端点。
"""

from __future__ import annotations

import difflib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.skill_overlay import SkillRelinkReport
    from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl

_BASE_URL_DEFAULT = "http://10.36.6.252:8765"


def register(app: typer.Typer) -> None:
    """Register the ``assistants`` subcommand group on the CLI app."""
    assistants_app = typer.Typer(
        help="Assistant lifecycle (ADR-0187; requires web-assistant profile).",
        no_args_is_help=True,
    )
    assistants_app.command(name="list", help=_list.__doc__ or "")(_list)
    assistants_app.command(name="show", help=_show.__doc__ or "")(_show)
    assistants_app.command(name="create", help=_create.__doc__ or "")(_create)
    assistants_app.command(name="soul-history", help=_soul_history.__doc__ or "")(_soul_history)
    assistants_app.command(name="soul-diff", help=_soul_diff.__doc__ or "")(_soul_diff)
    assistants_app.command(name="soul-rollback", help=_soul_rollback.__doc__ or "")(_soul_rollback)
    assistants_app.command(name="relink-skills", help=_relink_skills.__doc__ or "")(_relink_skills)
    app.add_typer(assistants_app, name="assistants")


def _assistants_root() -> Path:
    """CLI 进程内使用的 catalog 根目录（与内核 LCA_ASSISTANTS_ROOT 同源）。"""
    return Path(os.environ.get("LCA_ASSISTANTS_ROOT", str(Path.home() / ".lca" / "assistants")))


def _catalog() -> object:
    """进程内实例化配置面 catalog（同 ``ops.memory`` 的用法）。"""
    from lca.plugins.domain.assistant.catalog.plugin import _AssistantCatalogImpl

    return _AssistantCatalogImpl(root=_assistants_root())


def _load_snapshot(assistant_id: str, revision_seq: int) -> dict[str, object]:
    root = _assistants_root()
    path = root / assistant_id / "revisions" / f"{revision_seq}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        typer.echo(f"读取快照失败 {path}: {exc}")
        raise typer.Exit(code=1) from exc


def _soul_history(
    assistant_id: str = typer.Argument(..., help="asst_* id"),
) -> None:
    """列出助理的修订历史（revisions/N.json 摘要）。"""
    revisions_dir = _assistants_root() / assistant_id / "revisions"
    if not revisions_dir.is_dir():
        typer.echo(f"assistant {assistant_id} 无 revisions/ 目录（可能未创建或已删除）")
        raise typer.Exit(code=1)
    seqs = sorted(int(p.stem) for p in revisions_dir.glob("*.json"))
    if not seqs:
        typer.echo("（无修订快照）")
        return
    for seq in seqs:
        snapshot = _load_snapshot(assistant_id, seq)
        created = str(snapshot.get("created_at") or "?")
        has_files = "files" in snapshot
        typer.echo(f"{seq:>4}  {created}  files={has_files}")


def _soul_diff(
    assistant_id: str = typer.Argument(..., help="asst_* id"),
    from_seq: int = typer.Argument(..., help="起始修订序号"),
    to_seq: int = typer.Argument(..., help="目标修订序号"),
) -> None:
    """对比两个修订快照的配置面文件差异（unified diff）。"""
    snap_from = _load_snapshot(assistant_id, from_seq)
    snap_to = _load_snapshot(assistant_id, to_seq)
    raw_from = snap_from.get("files")
    files_from = raw_from if isinstance(raw_from, dict) else {}
    raw_to = snap_to.get("files")
    files_to = raw_to if isinstance(raw_to, dict) else {}
    if not files_from and not files_to:
        typer.echo(f"revision {from_seq} / {to_seq} 均不含文件内容（digest-only 快照）")
        return
    names = sorted(set(files_from) | set(files_to))
    changed = [name for name in names if files_from.get(name) != files_to.get(name)]
    if not changed:
        typer.echo(f"revision {from_seq} → {to_seq}：无文件差异")
        return
    for name in changed:
        typer.echo(f"── {name} ──")
        old = (files_from.get(name) or "").splitlines()
        new = (files_to.get(name) or "").splitlines()
        for line in difflib.unified_diff(
            old,
            new,
            fromfile=f"rev{from_seq}/{name}",
            tofile=f"rev{to_seq}/{name}",
            lineterm="",
        ):
            typer.echo(line)


def _soul_rollback(
    assistant_id: str = typer.Argument(..., help="asst_* id"),
    to: int = typer.Option(..., "--to", help="要回滚到的修订序号"),
) -> None:
    """把配置面恢复为历史修订快照（写回全文 → reimport → 新 revision）。"""
    revision = _catalog().restore_revision(assistant_id, to)  # type: ignore[attr-defined]
    typer.echo(
        f"rolled back {assistant_id} → rev{to}，新 revision_seq={revision.revision_seq} "
        f"snapshot={revision.snapshot_path}"
    )


def _overlay() -> AssistantSkillOverlayImpl:
    """进程内实例化 skill overlay（与 ``_catalog`` 同一用法；无 REST 端点）。"""
    from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl

    return AssistantSkillOverlayImpl(catalog=_catalog())  # type: ignore[arg-type]


def _home_assistant_ids() -> list[str]:
    """``assistants`` 根下每个含 manifest.json 的 Home 目录名（= assistant_id）。"""
    root = _assistants_root()
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and (child / "manifest.json").is_file()
    )


_RELINK_BUCKETS = ("relinked", "already_current", "skipped_local", "skipped_missing_global")
"""``SkillRelinkReport`` 的四个分类桶；输出字段名与报告字段名同源。"""


def _relink_row(report: SkillRelinkReport) -> dict[str, Any]:
    """``SkillRelinkReport`` → CLI / JSON 行。"""
    row: dict[str, Any] = {
        "assistant_id": report.assistant_id,
        "revision_seq": report.revision_seq,
        "manifest_digest": report.manifest_digest,
    }
    row.update({bucket: list(getattr(report, bucket)) for bucket in _RELINK_BUCKETS})
    return row


def _relink_totals(rows: list[dict[str, Any]], errors: list[dict[str, str]]) -> dict[str, int]:
    """``--all`` 合计（文本行与 JSON ``totals`` 共用同一份数字）。"""
    totals = {"assistants": len(rows) + len(errors)}
    totals.update({bucket: sum(len(row[bucket]) for row in rows) for bucket in _RELINK_BUCKETS})
    totals["errors"] = len(errors)
    return totals


def _relink_skills(
    assistant: str = typer.Option("", "--assistant", help="助理 id（与 --all 二选一）。"),
    all_homes: bool = typer.Option(
        False, "--all", help="遍历 assistants 根下每个 Home（与 --assistant 二选一）。"
    ),
    json_mode: bool = typer.Option(False, "--json", help="Print raw JSON."),
) -> None:
    """把 global_link 技能重链到全局库当前版本（ADR-0243 D1 显式升级）。

    全局技能更新只写新版本，已链接 Home 保持旧 inode，所以升级必须显式触发。
    只动 Home manifest 里 ``source=global_link`` 的条目：``local`` 副本与全局已
    缺失/退役的包一律保留（版本固定；删除走 ``remove``）。一个 Home 整批只产生
    一次 manifest 修订。任一 Home 失败 ⇒ 退出码 1，其余 Home 继续。
    """
    target = assistant.strip()
    if bool(target) == all_homes:
        typer.echo("必须且只能指定 --assistant / --all 之一")
        raise typer.Exit(code=1)
    ids = [target] if target else _home_assistant_ids()
    if not ids:
        typer.echo(f"（{_assistants_root()} 下无助理 Home）")
        return

    overlay = _overlay()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for assistant_id in ids:
        try:
            report = overlay.relink_global_skills(assistant_id)
        except Exception as exc:  # 单个 Home 失败不阻断整批；退出码承担失败信号
            errors.append({"assistant_id": assistant_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        rows.append(_relink_row(report))

    if json_mode:
        payload: object
        if target:
            payload = rows[0] if rows else errors[0]
        else:
            payload = {
                "assistants": rows,
                "errors": errors,
                "totals": _relink_totals(rows, errors),
            }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            counts = " ".join(f"{bucket}={len(row[bucket])}" for bucket in _RELINK_BUCKETS)
            typer.echo(f"{row['assistant_id']}  {counts}  rev={row['revision_seq']}")
        for row in errors:
            typer.echo(f"{row['assistant_id']}  ERROR {row['error']}")
        if not target:
            totals = " ".join(f"{k}={v}" for k, v in _relink_totals(rows, errors).items())
            typer.echo(f"total: {totals}")
    if errors:
        raise typer.Exit(code=1)


def _request(
    method: str,
    base_url: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, dict | str]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    user_id = os.environ.get("LCA_USER_ID", "local-dev-user").strip() or "local-dev-user"
    auth_token = os.environ.get("LCA_AUTH_TOKEN", "lca-local").strip() or "lca-local"
    headers: dict[str, str] = {
        "x-lca-user-id": user_id,
        "Authorization": f"Bearer {auth_token}",
    }
    if data:
        headers["content-type"] = "application/json"
    req = urllib.request.Request(  # noqa: S310 -- URL from operator CLI args/env; scheme not attacker-controlled
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 -- URL from operator CLI args/env; scheme not attacker-controlled
            text = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def _emit(status: int, payload: dict | str, *, json_mode: bool) -> None:
    if json_mode:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if status >= 400:
        detail = payload.get("error") if isinstance(payload, dict) else payload
        typer.echo(f"HTTP {status}: {detail}")
        raise typer.Exit(code=1)


def _list(
    base_url: str = typer.Option(
        _BASE_URL_DEFAULT, "--base-url", envvar="LCA_OPS_BASE_URL", help="Kernel base URL."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Print raw JSON."),
) -> None:
    """List assistants (GET /v1/assistants)."""
    status, payload = _request("GET", base_url, "/v1/assistants")
    _emit(status, payload, json_mode=json_mode)
    if json_mode or status >= 400 or not isinstance(payload, dict):
        return
    items = payload.get("assistants") or []
    if not items:
        typer.echo("（尚无助理）")
        return
    for item in items:
        typer.echo(
            f"{item.get('assistant_id')}  {item.get('name')}  "
            f"[{item.get('status')}]  template={item.get('template_id')}  "
            f"rev={item.get('revision_seq')}"
        )


def _show(
    assistant_id: str = typer.Argument(..., help="asst_* id"),
    base_url: str = typer.Option(
        _BASE_URL_DEFAULT, "--base-url", envvar="LCA_OPS_BASE_URL", help="Kernel base URL."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Print raw JSON."),
) -> None:
    """Show one assistant (GET /v1/assistants/{id})."""
    status, payload = _request("GET", base_url, f"/v1/assistants/{assistant_id}")
    _emit(status, payload, json_mode=json_mode)
    if json_mode or status >= 400 or not isinstance(payload, dict):
        return
    typer.echo(f"assistant_id: {payload.get('assistant_id')}")
    typer.echo(f"name:         {payload.get('profile_name')}")
    typer.echo(f"description:  {payload.get('profile_description')}")
    typer.echo(f"template_id:  {payload.get('template_id')}")
    typer.echo(f"revision_seq: {payload.get('revision_seq')}")
    typer.echo(f"home_path:    {payload.get('home_path')}")


def _create(
    name: str = typer.Option(..., "--name", help="助理名字。"),
    description: str = typer.Option("", "--description", help="一句话职责。"),
    template_id: str = typer.Option(
        "assistant.default",
        "--template",
        help="角色模板 id（assistant.default/research/writing/coding/translation/daily）。",
    ),
    seed_user_md: str = typer.Option(
        "", "--seed-user-md", help="可选：USER.md 内容（提供则完成 BOOTSTRAP）。"
    ),
    base_url: str = typer.Option(
        _BASE_URL_DEFAULT, "--base-url", envvar="LCA_OPS_BASE_URL", help="Kernel base URL."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Print raw JSON."),
) -> None:
    """Create an assistant (POST /v1/assistants).

    注意：本命令只走后端 catalog；前端 agents 行注册在对话创建流
    （create_assistant 工具 + frontend_bridge）内发生。
    """
    body: dict = {
        "name": name,
        "description": description,
        "template_id": template_id,
    }
    if seed_user_md:
        body["seed_user_md"] = seed_user_md
    status, payload = _request("POST", base_url, "/v1/assistants", body)
    _emit(status, payload, json_mode=json_mode)
    if json_mode or status >= 400 or not isinstance(payload, dict):
        return
    typer.echo(f"created: {payload.get('assistant_id')}  name={name}  template={template_id}")
    typer.echo(f"home:    {payload.get('home_path')}")
