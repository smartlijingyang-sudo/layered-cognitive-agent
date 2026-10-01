"""``lca-ops assistants`` — Assistant lifecycle CLI（ADR-0187 §3 D7）。

创建/查看助理走 REST 薄封装（真值在 ``AssistantCatalog``，经
``routes_assistants``）；``soul-history/diff/rollback`` 是内容级回滚的
诊断/恢复命令，直接进程内读 ``revisions/`` 快照并调用 catalog（与
``memory`` 命令同构），因为快照读回尚无 REST 端点。
"""

from __future__ import annotations

import difflib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import typer

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
    files_from = snap_from.get("files") if isinstance(snap_from.get("files"), dict) else {}
    files_to = snap_to.get("files") if isinstance(snap_to.get("files"), dict) else {}
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
    req = urllib.request.Request(  # noqa: S310 — CLI to local kernel; LCA_OPS_BASE_URL is operator-controlled.
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — same justification as Request above.
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
