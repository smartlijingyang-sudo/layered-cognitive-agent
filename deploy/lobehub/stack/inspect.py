"""Read-only inspection: routes, process, probes, patches, code delta."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from starlette.routing import Route, WebSocketRoute

from deploy.lobehub.stack.config import ProbeConfig, StackConfig, SurfaceMeta
from deploy.lobehub.stack.process import listening, pid_alive, public_url, read_pid, start_epoch
from deploy.lobehub.stack.types import (
    BoundSurface,
    Check,
    DiscoveredRoute,
    ProcessSnapshot,
    RestartDelta,
    Section,
    Status,
)


def iter_app_routes(app: Any) -> list[DiscoveredRoute]:
    found: dict[str, DiscoveredRoute] = {}
    for route in app.routes:
        if isinstance(route, WebSocketRoute):
            found[route.path] = DiscoveredRoute(
                path=route.path, methods=("WS",), kind="websocket"
            )
            continue
        if not isinstance(route, Route):
            continue
        methods = tuple(sorted(m for m in (route.methods or set()) if m != "HEAD"))
        if methods == ("OPTIONS",):
            continue
        existing = found.get(route.path)
        if existing is None:
            found[route.path] = DiscoveredRoute(path=route.path, methods=methods, kind="http")
            continue
        merged = tuple(sorted(set(existing.methods) | set(methods)))
        found[route.path] = existing.model_copy(update={"methods": merged})
    return list(found.values())


def bind_surfaces(
    routes: list[DiscoveredRoute], metas: list[SurfaceMeta]
) -> list[BoundSurface]:
    remaining = list(routes)
    bound: list[BoundSurface] = []
    for meta in metas:
        pattern = re.compile(meta.match)
        matched = tuple(route for route in remaining if pattern.search(route.path))
        remaining = [route for route in remaining if route not in matched]
        bound.append(
            BoundSurface(
                id=meta.id,
                title=meta.title,
                purpose=meta.purpose,
                routes=matched,
                classified=True,
            )
        )
    if remaining:
        bound.append(
            BoundSurface(
                id="unclassified",
                title="Unclassified",
                purpose="Live routes with no surface metadata — add a match in stack.yaml",
                routes=tuple(remaining),
                classified=False,
            )
        )
    return bound


def newer_files(
    watch: list[str],
    *,
    since_epoch: float,
    glob: str,
    root: Path,
) -> list[Path]:
    found: list[Path] = []
    for item in watch:
        path = (root / item).resolve() if not Path(item).is_absolute() else Path(item)
        if path.is_file():
            if path.stat().st_mtime > since_epoch:
                found.append(path)
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob(glob):
            if candidate.is_file() and candidate.stat().st_mtime > since_epoch:
                found.append(candidate)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found


def http_probe(url: str, *, timeout: float = 2.0) -> tuple[int, dict[str, Any] | None, str]:
    try:
        with urlopen(url, timeout=timeout) as resp:  # noqa: S310
            status = int(resp.status)
            raw = resp.read()
    except HTTPError as exc:
        return int(exc.code), None, str(exc.reason)
    except (URLError, TimeoutError, OSError) as exc:
        return 0, None, str(exc.reason if isinstance(exc, URLError) else exc)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None, ""
    return status, payload if isinstance(payload, dict) else None, ""


def process_snapshot(root: Path, config: StackConfig) -> ProcessSnapshot:
    gw = config.gateway
    pid_path = root / gw.pid_file
    pid = read_pid(pid_path)
    alive = pid_alive(pid) if pid is not None else False
    base = f"http://127.0.0.1:{gw.port}"
    code, payload, err = http_probe(f"{base}{gw.health_path}") if alive else (0, None, "not running")
    return ProcessSnapshot(
        pid=pid,
        alive=alive,
        started_epoch=start_epoch(pid) if alive and pid is not None else None,
        port=gw.port,
        bind=gw.bind,
        listening=listening(gw.port),
        public_url=public_url(gw.port),
        log_file=str(root / gw.log_file),
        health=payload if code == 200 else None,
        health_error=None if code == 200 else (err or f"http {code}"),
    )


def probe_surfaces(
    surfaces: list[BoundSurface],
    metas: list[SurfaceMeta],
    *,
    port: int,
) -> list[BoundSurface]:
    by_id = {meta.id: meta for meta in metas}
    probed: list[BoundSurface] = []
    for surface in surfaces:
        meta = by_id.get(surface.id)
        probe = meta.probe if meta is not None else None
        if probe is None:
            probed.append(surface)
            continue
        probed.append(_apply_probe(surface, probe, port=port))
    return probed


def _apply_probe(surface: BoundSurface, probe: ProbeConfig, *, port: int) -> BoundSurface:
    url = f"http://127.0.0.1:{port}{probe.path}"
    code, payload, err = http_probe(url)
    ok = code == probe.expect
    detail = f"{code} {url}"
    if payload is not None:
        bits = []
        if "status" in payload:
            bits.append(f"status={payload['status']}")
        if "llm_available" in payload:
            bits.append(f"llm={payload['llm_available']}")
        if "runs" in payload:
            bits.append(f"runs={payload['runs']}")
        if "devices" in payload:
            bits.append(f"devices={payload['devices']}")
        if "data" in payload and isinstance(payload["data"], list):
            bits.append(f"models={len(payload['data'])}")
        if bits:
            detail = f"{code} {' '.join(bits)}"
    elif err:
        detail = f"{code} {err}"
    return surface.model_copy(
        update={"probe_status": Status.OK if ok else Status.ERROR, "probe_detail": detail}
    )


def inspect_patches(ui_dir: Path) -> Section:
    from deploy.lobehub.engine import PatchContext, discover_patches

    modules = discover_patches()
    ctx = PatchContext(ui_dir)
    checks: list[Check] = []
    for module in sorted(modules, key=lambda item: (item.meta.category, item.meta.name)):
        meta = module.meta
        prefix = f"{meta.category} · {meta.risk}"
        if not ui_dir.is_dir():
            checks.append(Check(name=meta.name, status=Status.WARN, detail=f"{prefix} · ui missing"))
            continue
        if not meta.verify_marker:
            checks.append(
                Check(name=meta.name, status=Status.OK, detail=f"{prefix} · {meta.description}")
            )
            continue
        check_file = meta.verify_file or (meta.files[0] if meta.files else "")
        if not check_file:
            checks.append(Check(name=meta.name, status=Status.WARN, detail=f"{prefix} · no verify file"))
            continue
        path = ctx.path(check_file)
        if not path.is_file():
            checks.append(
                Check(name=meta.name, status=Status.MISSING, detail=f"{prefix} · missing {check_file}")
            )
            continue
        present = meta.verify_marker in path.read_text(encoding="utf-8")
        checks.append(
            Check(
                name=meta.name,
                status=Status.OK if present else Status.ERROR,
                detail=f"{prefix} · {'marker present' if present else f'marker absent in {check_file}'}",
            )
        )
    return Section(id="patches", title="patches", checks=tuple(checks))


def inspect_lobehub(root: Path, config: StackConfig) -> Section:
    ui = root / config.lobehub.dir
    env_file = ui / ".env"
    template = root / config.lobehub.env_template
    pid = read_pid(root / config.lobehub.pid_file)
    version = "missing"
    pkg = ui / "package.json"
    if pkg.is_file():
        try:
            version = str(json.loads(pkg.read_text(encoding="utf-8")).get("version", "?"))
        except json.JSONDecodeError:
            version = "unreadable"
    expected = config.lobehub.release.lstrip("v")
    version_ok = version == expected
    checks = (
        Check(
            name="lobehub-ui",
            status=Status.OK if version_ok else Status.WARN,
            detail=f"version={version} expected={expected}",
        ),
        Check(
            name="env",
            status=Status.OK if env_file.is_file() else Status.WARN,
            detail=str(env_file if env_file.is_file() else f"missing (template {template})"),
        ),
        Check(
            name="dev",
            status=Status.OK if listening(config.lobehub.dev_port) else Status.MISSING,
            detail=f":{config.lobehub.dev_port} pid={pid or '—'}",
        ),
    )
    return Section(id="lobehub", title="lobehub", checks=checks)


def inspect_infra(root: Path, config: StackConfig) -> Section:
    env_file = root / config.lobehub.dir / ".env"
    if not env_file.is_file():
        env_file = root / config.lobehub.env_template
    targets = _infra_targets(env_file) if env_file.is_file() else []
    if not targets:
        return Section(
            id="infra",
            title="infra",
            checks=(Check(name="endpoints", status=Status.WARN, detail="no DATABASE_URL/REDIS_URL/S3"),),
        )
    checks = []
    for name, host, port in targets:
        ok = _tcp_open(host, port)
        checks.append(
            Check(
                name=name,
                status=Status.OK if ok else Status.MISSING,
                detail=f"{host}:{port}",
            )
        )
    return Section(id="infra", title="infra", checks=tuple(checks))


def inspect_host(root: Path, config: StackConfig) -> list[Section]:
    from lca.layer0_infra.host_runtime.config import HostRuntimeConfig
    from lca.layer0_infra.host_runtime.environment import HostEnvironment
    from lca.layer0_infra.host_runtime.providers import ItemStatus

    mapping = {
        ItemStatus.OK: Status.OK,
        ItemStatus.MISSING: Status.MISSING,
        ItemStatus.WARN: Status.WARN,
        ItemStatus.ERROR: Status.ERROR,
    }
    host_cfg = HostRuntimeConfig.from_yaml_or_default(root / config.host.config_file)
    reports = HostEnvironment(host_cfg).status(config.host.user)
    sections: list[Section] = []
    for report in reports:
        checks = tuple(
            Check(name=item.name, status=mapping[item.status], detail=item.detail)
            for item in report.checks
        )
        sections.append(Section(id=f"host.{report.provider}", title=report.provider, checks=checks))
    return sections


def build_delta(
    *,
    previous: ProcessSnapshot | None,
    current: ProcessSnapshot,
    newer: list[Path],
    root: Path,
    reason: str,
) -> RestartDelta:
    rels: list[str] = []
    for path in newer:
        try:
            rels.append(str(path.relative_to(root)))
        except ValueError:
            rels.append(str(path))
    return RestartDelta(
        reason=reason,
        previous_pid=previous.pid if previous is not None else None,
        current_pid=current.pid,
        newer_files=tuple(rels),
    )


def restart_reason(*, force: bool, previous: ProcessSnapshot | None, newer: list[Path]) -> str:
    if force:
        return "force"
    if previous is None or not previous.alive:
        return "not-running"
    if newer:
        return f"code-newer ({len(newer)} files)"
    return "already-running"


def _infra_targets(env_file: Path) -> list[tuple[str, str, int]]:
    from urllib.parse import urlparse

    env: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    checks: list[tuple[str, str, int]] = []
    if db := env.get("DATABASE_URL"):
        parsed = urlparse(db)
        checks.append(("postgres", parsed.hostname or "127.0.0.1", parsed.port or 5432))
    if redis := env.get("REDIS_URL"):
        parsed = urlparse(redis)
        checks.append(("redis", parsed.hostname or "127.0.0.1", parsed.port or 6379))
    if s3 := env.get("S3_ENDPOINT"):
        parsed = urlparse(s3)
        if parsed.hostname:
            default = 443 if parsed.scheme == "https" else 80
            checks.append(("s3", parsed.hostname, parsed.port or default))
    return checks


def _tcp_open(host: str, port: int) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False
