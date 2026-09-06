"""``lca-ops assistants`` — CLI wrapper for ``/v1/assistants`` (ADR-0187 §3 D7).

Thin wrapper：创建/查看助理的真值在 ``AssistantCatalog``（经
``routes_assistants`` REST），本模块只构造/转发 HTTP，不复制业务。
内核未启用 ``assistant-runtime`` bundle（web-standard）时端点返回
501 ``catalog_unavailable``，命令原样呈现错误。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import typer

_BASE_URL_DEFAULT = "http://127.0.0.1:8765"


def register(app: typer.Typer) -> None:
    """Register the ``assistants`` subcommand group on the CLI app."""
    assistants_app = typer.Typer(
        help="Assistant lifecycle (ADR-0187; requires web-assistant profile).",
        no_args_is_help=True,
    )
    assistants_app.command(name="list", help=_list.__doc__ or "")(_list)
    assistants_app.command(name="show", help=_show.__doc__ or "")(_show)
    assistants_app.command(name="create", help=_create.__doc__ or "")(_create)
    app.add_typer(assistants_app, name="assistants")


def _request(
    method: str,
    base_url: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, dict | str]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(  # noqa: S310 — CLI to local kernel; LCA_OPS_BASE_URL is operator-controlled.
        url,
        data=data,
        method=method,
        headers={"content-type": "application/json"} if data else {},
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
