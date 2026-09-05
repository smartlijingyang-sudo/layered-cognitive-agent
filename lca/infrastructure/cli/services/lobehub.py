"""LobeHub service — Next.js frontend.

Full lifecycle: sync source, apply patches, configure env, install deps,
start dev server, stop, restart.

Design: each phase is a separate method, all idempotent. The service
tracks what's been done via stamps so restart doesn't redo setup.
"""

from __future__ import annotations

import json
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lca.infrastructure.cli.config import KernelServeConfig, LobeHubConfig
from lca.infrastructure.cli.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    free_port,
    http_ready,
    kill_tree,
    pid_alive,
    pid_on_port,
)
from lca.infrastructure.cli.state import StateStore


@dataclass(frozen=True, slots=True)
class _VerifySummary:
    """Structured result from ``patch_lobehub.py verify``.

    ``total`` is the number of patches the engine actually checked.
    ``ok`` patches have their verify marker present in the target file.
    ``broken`` patches are missing or carry a stale marker.
    ``names`` lists broken patch names so the status can name them.
    ``error`` is non-empty when the verify subprocess itself failed
    (script missing, timeout, etc.) — in that case the other fields
    are zero/empty and the caller should report "unknown".
    """

    ok: int
    broken: int
    names: tuple[str, ...]
    error: str = ""


@dataclass(frozen=True, slots=True)
class _VerifyCache:
    ts: float
    summary: _VerifySummary


def _parse_verify_output(stdout: str) -> _VerifySummary:
    """Parse the ``[verify] N ok, M broken/missing`` summary line.

    Falls back to scanning per-patch OK/BROKEN/MISS lines when the
    summary line is missing (older engine versions). Names listed as
    SKIP are not counted as broken — they simply have no verify marker.
    """
    broken_names: list[str] = []
    ok_count = 0
    broken_count = 0

    for line in stdout.splitlines():
        # Per-patch lines look like: "[patch] OK     dev_auth_files"
        if line.startswith("[patch]"):
            parts = line.split()
            if len(parts) < 3:
                continue
            verdict, name = parts[1], parts[2]
            if verdict == "OK":
                ok_count += 1
            elif verdict in {"BROKEN", "MISS"}:
                broken_count += 1
                broken_names.append(name)
            # SKIP / WARNING are not counted (no verify marker).
            continue
        # Summary line: "[verify] 18 ok, 0 broken/missing"
        if line.startswith("[verify]"):
            tokens = line.split()
            for i, tok in enumerate(tokens):
                if tok == "ok," and i > 0:
                    with suppress(ValueError):
                        ok_count = int(tokens[i - 1])
                if tok == "broken/missing" and i > 0:
                    with suppress(ValueError):
                        broken_count = int(tokens[i - 1])

    return _VerifySummary(ok=ok_count, broken=broken_count, names=tuple(broken_names))


class LobeHubService:
    """LobeHub Next.js frontend.

    Next on ``dev_port`` is the service. Vite SPA on ``spa_port`` is a
    sidecar with an independent lifetime — its exit must not kill Next.
    """

    _SPA_NAME = "lobehub-spa"

    def __init__(
        self,
        config: LobeHubConfig,
        gateway: KernelServeConfig,
        state_dir: Path,
        root: Path,
    ) -> None:
        self.name = "lobehub"
        self._config = config
        self._kernel_serve = gateway
        self._state = StateStore(state_dir)
        self._root = root
        self._dir = root / config.dir
        # Verify subprocess is ~1s; cache 30s so status stays snappy.
        self._verify_cache: _VerifyCache | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> ServiceState:
        """Start Vite sidecar first, then Next (Next proxies SPA HTML from Vite)."""
        current = self.state()
        if current.is_running:
            return current

        self.ensure_ready()
        spa_pid = self._ensure_spa()
        if spa_pid is None:
            return ServiceState(status=ServiceStatus.STOPPED, detail="vite spawn failed")
        if not self._spa_ready():
            return ServiceState(
                status=ServiceStatus.STOPPED,
                pid=spa_pid,
                detail="vite sidecar start timeout",
            )
        pid = self._ensure_next()
        if pid is None:
            return ServiceState(status=ServiceStatus.STOPPED, detail="spawn failed")
        if not self._next_ready():
            return ServiceState(
                status=ServiceStatus.STOPPED,
                pid=pid,
                detail="dev server start timeout",
            )
        return ServiceState(
            status=ServiceStatus.RUNNING,
            pid=pid,
            port=self._config.dev_port,
            detail="dev server ready",
        )

    def stop(self) -> ServiceState:
        """Stop Next and the Vite sidecar."""
        pids = self._collect_pids()
        for pid in pids:
            kill_tree(pid)

        time.sleep(0.5)
        free_port(self._config.dev_port)
        free_port(self._config.spa_port)
        self._state.remove_pid(self.name)
        self._state.remove_pid(self._SPA_NAME)

        return ServiceState(status=ServiceStatus.STOPPED)

    def restart(self) -> ServiceState:
        """Restart the dev server."""
        self.stop()
        return self.start()

    # ── Setup (idempotent) ────────────────────────────────────────────

    def ensure_ready(self) -> bool:
        """Ensure all prerequisites: source, patches, env, deps.

        Each step checks if it needs to run, so this is safe to call
        repeatedly.
        """
        worked = False
        worked |= self._ensure_source()
        worked |= self._ensure_patches()
        worked |= self._ensure_pnpm_patches()
        worked |= self._ensure_env()
        worked |= self._ensure_deps()
        return worked

    # ── Health ────────────────────────────────────────────────────────

    def state(self) -> ServiceState:
        """Observe current state."""
        stored_pid = self._state.read_pid(self.name)
        checks: list[HealthCheck] = []

        # Dev server responding? HTTP is the ground truth for "UI is up".
        dev_ok = http_ready(f"{self._config.dev_url}/", timeout=2.0)
        checks.append(HealthCheck("dev", dev_ok, f":{self._config.dev_port}"))

        spa_pid = pid_on_port(self._config.spa_port)
        spa_ok = spa_pid is not None
        stored_spa = self._state.read_pid(self._SPA_NAME)
        if spa_ok and spa_pid and (stored_spa is None or not pid_alive(stored_spa)):
            self._state.write_pid(self._SPA_NAME, spa_pid)
        checks.append(HealthCheck("spa", spa_ok, f":{self._config.spa_port}" if spa_ok else "none"))

        # Reconcile PID: next-server may outlive the recorded bun parent.
        port_pid = pid_on_port(self._config.dev_port) if dev_ok else None
        if dev_ok and port_pid and (stored_pid is None or not pid_alive(stored_pid)):
            self._state.write_pid(self.name, port_pid)

        pid = stored_pid if stored_pid and pid_alive(stored_pid) else port_pid
        process_ok = pid is not None and pid_alive(pid)
        checks.append(HealthCheck("process", process_ok, f"pid={pid}" if pid else "none"))

        # Source synced?
        source_ok = self._dir.exists() and (self._dir / "package.json").exists()
        checks.append(HealthCheck("source", source_ok, str(self._dir)))

        # Patches applied? — verify is the source of truth, not file counts.
        # ``.lca-patched`` only proves *some* apply once ran; ``verify`` proves
        # every patch marker is still present in the target file.
        deploy_dir = self._root / "deploy" / "lobehub"
        verify = self._run_patch_verify()
        patch_drift = self._state.detect_changes("patches", [deploy_dir], "*")
        if verify.error:
            patch_detail = f"verify unavailable ({verify.error})"
            patches_ok = False
        elif verify.broken:
            patch_detail = (
                f"{verify.ok}/{verify.ok + verify.broken} verified, "
                f"broken: {', '.join(verify.names)}"
            )
            patches_ok = False
        elif patch_drift.has_changes:
            patch_detail = (
                f"{verify.ok} verified, patch source changed "
                f"({patch_drift.summary}) — re-run `patch_lobehub.py`"
            )
            patches_ok = False
        elif verify.ok == 0:
            patch_detail = "no patches registered"
            patches_ok = True
        else:
            patch_detail = f"{verify.ok}/{verify.ok} verified"
            patches_ok = True
        checks.append(HealthCheck("patches", patches_ok, patch_detail))

        # Pnpm patchedDependencies check(ADR-0163). Marker encodes the
        # last attempt: ``patched_count`` applied cleanly,
        # ``failed`` names drift hunk(s) that no longer fit upstream.
        pnpm_marker = self._state._dir / "lobehub-pnpm-patches.marker"
        if pnpm_marker.exists():
            try:
                marker_payload = json.loads(pnpm_marker.read_text())
            except (json.JSONDecodeError, OSError):
                marker_payload = {}
            applied = int(marker_payload.get("patched_count", 0) or 0)
            failed_raw = marker_payload.get("failed") or []
            if failed_raw:
                failed_pkgs = ", ".join(f.split(":", 1)[0] for f in failed_raw)
                # Drift = hunk(s) the upstream no longer matches. This is a
                # upstream dependency bump, not an LCA misconfiguration —
                # call it that so operators stop chasing it with `ensure`.
                if applied > 0:
                    pnpm_detail = (
                        f"drift ({applied} applied, "
                        f"{len(failed_raw)} drift: {failed_pkgs}) — "
                        f"upstream patch hunk no longer fits; regenerate "
                        f"`lobehub-ui/patches/*.patch` from upstream"
                    )
                else:
                    pnpm_detail = (
                        f"drift (0 applied, {len(failed_raw)} drift: "
                        f"{failed_pkgs}) — regenerate "
                        f"`lobehub-ui/patches/*.patch` from upstream"
                    )
                checks.append(HealthCheck("pnpm-patches", False, pnpm_detail))
            elif applied > 0:
                checks.append(
                    HealthCheck(
                        "pnpm-patches",
                        True,
                        f"{applied} pnpm patches applied",
                    )
                )

        why = ""
        next_action = ""
        patches_drift = patch_drift.has_changes  # source changed since snapshot
        patches_broken = verify.broken > 0  # markers missing in target files
        if dev_ok and not spa_ok:
            status = ServiceStatus.DEGRADED
            detail = "Next up, Vite sidecar down"
            why = (
                f"SPA sidecar :{self._config.spa_port} is down; "
                f"{self._config.dev_url} still answers"
            )
            next_action = "./scripts/lca-ops lobehub heal"
        elif dev_ok:
            status = ServiceStatus.RUNNING
            detail = "healthy"
            if patches_broken:
                detail = f"healthy ({patch_detail})"
                why = (
                    "patch markers missing in target files — "
                    "run `python3 deploy/lobehub/patch_lobehub.py`"
                )
                next_action = "python3 deploy/lobehub/patch_lobehub.py"
            elif patches_drift:
                detail = f"healthy (patch source drifted — {patch_drift.summary})"
                why = "patch source changed since last apply"
                next_action = "./scripts/lca-ops lobehub ensure"
        elif process_ok:
            status = ServiceStatus.DEGRADED
            detail = "process alive but dev server not responding"
            why = f"{self._config.dev_url} is not answering yet"
            next_action = "./scripts/lca-ops logs lobehub"
        elif not source_ok:
            status = ServiceStatus.STOPPED
            detail = "source missing"
            why = f"{self._dir} has no package.json — UI is not synced"
            next_action = "./scripts/lca-ops lobehub ensure"
        else:
            status = ServiceStatus.STOPPED
            detail = "not running"
            why = f"UI is down — open {self._config.dev_url} will fail"
            next_action = "./scripts/lca-ops lobehub start"

        return ServiceState(
            status=status,
            checks=tuple(checks),
            pid=pid if process_ok else None,
            port=self._config.dev_port,
            detail=detail,
            why=why,
            next_action=next_action,
        )

    def heal(self) -> ServiceState:
        """Repair without a death pact: Next stays up if only the sidecar is missing."""
        current = self.state()
        if current.is_running and not current.next_action:
            return current

        # Patch drift/broken → run the patch engine in place; do NOT stop Next.
        # The dev server will HMR the patched files.
        if current.is_running and current.next_action.startswith("python3 "):
            patch_script = self._root / "deploy" / "lobehub" / "patch_lobehub.py"
            if patch_script.exists():
                with suppress(subprocess.SubprocessError, OSError):
                    subprocess.run(  # noqa: S603
                        ["python3", str(patch_script)],  # noqa: S607
                        cwd=self._root,
                        capture_output=True,
                        timeout=60,
                    )
                self._verify_cache = None
                return self.state()

        spa_down = not any(c.name == "spa" and c.ok for c in current.checks)
        next_up = any(c.name == "dev" and c.ok for c in current.checks)

        if next_up and spa_down and current.next_action.endswith("heal"):
            self._ensure_spa()
            return self.state()

        if current.is_running:
            self.stop()

        self.ensure_ready()
        return self.start()

    # ── Setup Internals ───────────────────────────────────────────────

    def _ensure_source(self) -> bool:
        """Sync LobeHub source if not present or version mismatch."""
        pkg = self._dir / "package.json"
        if pkg.exists():
            content = pkg.read_text()
            if f'"version": "{self._config.release.lstrip("v")}"' in content:
                return False

        # Run sync script
        sync_script = self._root / "scripts" / "sync_lobehub_ui.sh"
        if not sync_script.exists():
            return False

        try:
            subprocess.run(  # noqa: S603
                ["bash", str(sync_script)],  # noqa: S607
                env={"LOBEHUB_RELEASE": self._config.release},
                cwd=self._root,
                capture_output=True,
                timeout=300,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _count_patches(deploy_dir: Path) -> int:
        """Count patch module files (excluding __init__ and __pycache__).

        Kept for legacy callers; the authoritative count comes from
        ``patch_lobehub.py verify`` (``_run_patch_verify``).
        """
        patches_dir = deploy_dir / "patches"
        if not patches_dir.is_dir():
            return 0
        return sum(
            1
            for f in patches_dir.rglob("*.py")
            if f.name != "__init__.py" and "__pycache__" not in f.parts
        )

    def _run_patch_verify(self) -> _VerifySummary:
        """Run ``patch_lobehub.py verify`` and return a structured summary.

        Result is cached for 30s because ``state()`` may be called several
        times in a single CLI invocation (e.g. status then heal). The cache
        is invalidated by ``ensure_patches()`` after a successful apply.
        """
        now = time.monotonic()
        if self._verify_cache and now - self._verify_cache.ts < 30:
            return self._verify_cache.summary

        patch_script = self._root / "deploy" / "lobehub" / "patch_lobehub.py"
        if not patch_script.exists() or not self._dir.exists():
            summary = _VerifySummary(0, 0, (), error="script or ui source missing")
        else:
            try:
                proc = subprocess.run(  # noqa: S603
                    ["python3", str(patch_script), "verify"],  # noqa: S607
                    cwd=self._root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                summary = _VerifySummary(0, 0, (), error=f"{type(exc).__name__}: {exc}")
            else:
                summary = _parse_verify_output(proc.stdout)

        self._verify_cache = _VerifyCache(ts=now, summary=summary)
        return summary

    def _ensure_patches(self) -> bool:
        """Apply patches if source changed."""
        # Check if patches need reapplication
        deploy_dir = self._root / "deploy" / "lobehub"
        if not self._state.has_changed("patches", [deploy_dir], "*"):
            return False

        # Apply patches
        patch_script = self._root / "deploy" / "lobehub" / "patch_lobehub.py"
        if not patch_script.exists():
            return False

        try:
            subprocess.run(  # noqa: S603
                ["python3", str(patch_script)],  # noqa: S607
                cwd=self._root,
                capture_output=True,
                timeout=60,
            )
            self._state.save_snapshot("patches", [deploy_dir], "*")
            self._verify_cache = None
            return True
        except Exception:
            return False

    def _ensure_pnpm_patches(self) -> bool:
        """Apply pnpm-style patchedDependencies to bun-installed node_modules.

        LobeHub 上游声明 pnpm-workspace.yaml ``patchedDependencies``(如
        ``@upstash/qstash``),LCA 用 ``bun install`` 但 bun 不读 pnpm-workspace.yaml,
        导致上游 patch 永不 apply。本方法用 Python stdlib ``git apply`` 兼容风格
        把 pnpm patch 文件 apply 到 bun-installed node_modules 的对应路径。

        触发条件: ``lobehub-ui/package.json`` 含 ``patchedDependencies`` 字段 +
        ``lobehub-ui/patches/*.patch`` 存在 + bun node_modules 含对应包。
        No-op 条件: 已 apply(marker 文件存在)+ 无 patchedDependencies。
        """
        pkg_json = self._dir / "package.json"
        if not pkg_json.exists():
            return False
        try:
            data = json.loads(pkg_json.read_text())
        except (json.JSONDecodeError, OSError):
            return False
        # patchedDependencies 位置:pnpm 子对象(标准 pnpm v10 风格)+ 顶层 fallback
        patched = data.get("pnpm", {}).get("patchedDependencies") or data.get("patchedDependencies")
        if not isinstance(patched, dict) or not patched:
            return False

        patches_dir = self._dir / "patches"
        if not patches_dir.is_dir():
            return False

        # marker: 同一组 patched deps 全 apply 后写一次,避免每次 ensure 都全 apply
        marker = self._state._dir / "lobehub-pnpm-patches.marker"
        if marker.exists():
            return False

        worked = False
        failed: list[str] = []
        for pkg_name, rel_path in patched.items():
            patch_file = self._dir / rel_path
            if not patch_file.exists():
                failed.append(f"{pkg_name}: patch file missing ({rel_path})")
                continue
            bun_pkg_root = _find_bun_pkg_root(self._dir, pkg_name)
            if bun_pkg_root is None:
                failed.append(f"{pkg_name}: bun pkg root not found")
                continue
            try:
                import subprocess

                # git apply 不接受绝对 --directory;必须 cwd=ui_dir + 相对路径
                rel_dir = bun_pkg_root.resolve().relative_to(self._dir.resolve())
                # --reject: 让 git 把 apply 不上的 hunk 写到 .rej 文件方便诊断
                result = subprocess.run(  # noqa: S603
                    [  # noqa: S607
                        "git",
                        "apply",
                        "--reject",
                        "--whitespace=nowarn",
                        "--directory",
                        str(rel_dir),
                        str(patch_file),
                    ],
                    capture_output=True,
                    cwd=str(self._dir),
                    timeout=30,
                )
                stderr_text = result.stderr.decode(errors="replace")
                # git apply 在 skip 不能 fit 的 hunk 时会输出 "Skipped patch '...'"
                # 到 stderr 但 exit 仍为 0(设计如此)。必须显式检测。
                skipped = "Skipped patch" in stderr_text
                if result.returncode == 0 and not skipped:
                    worked = True
                else:
                    # 清理可能的 .rej 文件(下个 ensure 会重试)
                    with suppress(OSError):
                        for rej in bun_pkg_root.glob("*.rej"):
                            rej.unlink()
                    detail = stderr_text.strip()[:200] or f"rc={result.returncode}"
                    failed.append(f"{pkg_name}: git apply failed ({detail})")
            except (subprocess.SubprocessError, FileNotFoundError, ValueError) as exc:
                failed.append(f"{pkg_name}: {type(exc).__name__}: {exc}")

        if worked:
            marker_payload = {
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "patched_count": len(patched),
            }
            if failed:
                # 部分失败:不写 marker,下次 ensure 重试;但记 failed 到 log
                marker_payload["failed"] = failed
            marker.write_text(json.dumps(marker_payload))
        elif failed:
            # 全部失败:写 marker 记录失败状态,避免无限 retry 噪音
            marker.write_text(
                json.dumps(
                    {
                        "applied_at": datetime.now(timezone.utc).isoformat(),
                        "patched_count": 0,
                        "failed": failed,
                    }
                )
            )
        return worked

    def _ensure_env(self) -> bool:
        """Configure .env for LobeHub."""
        env_file = self._dir / ".env"
        template = self._root / self._config.env_template

        if not template.exists():
            return False

        # Copy template if .env doesn't exist
        if not env_file.exists():
            env_file.write_text(template.read_text())

        # Update kernel_serve proxy URLs (use LAN/public URL, not bind address 0.0.0.0)
        gateway_base = self._client_gateway_base()
        kernel_serve_url = f"{gateway_base}/v1"
        lines = env_file.read_text().splitlines()
        updated = []
        changed = False

        for line in lines:
            if line.startswith("OPENAI_PROXY_URL="):
                updated.append(f"OPENAI_PROXY_URL={kernel_serve_url}")
                changed = True
            elif line.startswith("NEXT_PUBLIC_OPENAI_PROXY_URL="):
                updated.append(f"NEXT_PUBLIC_OPENAI_PROXY_URL={kernel_serve_url}")
                changed = True
            elif line.startswith("OPENAI_API_KEY="):
                updated.append("OPENAI_API_KEY=lca-local")
                changed = True
            elif line.startswith("QWEN_PROXY_URL="):
                updated.append(f"QWEN_PROXY_URL={kernel_serve_url}")
                changed = True
            elif line.startswith("QWEN_API_KEY="):
                updated.append("QWEN_API_KEY=lca-local")
                changed = True
            else:
                updated.append(line)

        if changed:
            env_file.write_text("\n".join(updated) + "\n")

        return changed

    def _client_gateway_base(self) -> str:
        """Browser-reachable LCA gateway base (not the bind address)."""
        template = self._root / self._config.env_template
        if template.exists():
            vite_host = ""
            for line in template.read_text().splitlines():
                if line.startswith("LCA_GATEWAY_PUBLIC_URL="):
                    url = line.split("=", 1)[1].strip()
                    if url:
                        return url.rstrip("/")
                if line.startswith("VITE_DEV_HOST="):
                    vite_host = line.split("=", 1)[1].strip()
            if vite_host:
                return f"http://{vite_host}:{self._kernel_serve.port}"
        bind = self._kernel_serve.host
        if bind in {"0.0.0.0", "::"}:
            return f"http://127.0.0.1:{self._kernel_serve.port}"
        return self._kernel_serve.base_url.rstrip("/")

    def _ensure_deps(self) -> bool:
        """Install dependencies if node_modules missing."""
        if (self._dir / "node_modules").exists():
            return False

        try:
            subprocess.run(
                ["bun", "install"],  # noqa: S607
                cwd=self._dir,
                capture_output=True,
                timeout=300,
            )
            return True
        except Exception:
            return False

    # ── Lifecycle Internals ───────────────────────────────────────────

    def _next_ready(self) -> bool:
        needed = 3
        consec = 0
        for _ in range(120):
            time.sleep(0.5)
            if http_ready(f"{self._config.dev_url}/", timeout=1.0):
                consec += 1
                if consec >= needed:
                    return True
            else:
                consec = 0
        return False

    def _spa_ready(self) -> bool:
        spa_url = f"http://127.0.0.1:{self._config.spa_port}/"
        needed = 2
        consec = 0
        for _ in range(120):
            time.sleep(0.5)
            if http_ready(spa_url, timeout=1.0):
                consec += 1
                if consec >= needed:
                    return True
            else:
                consec = 0
        return False

    def _spa_listening(self) -> bool:
        return pid_on_port(self._config.spa_port) is not None

    def _ensure_next(self) -> int | None:
        if http_ready(f"{self._config.dev_url}/", timeout=1.0):
            port_pid = pid_on_port(self._config.dev_port)
            if port_pid:
                self._state.write_pid(self.name, port_pid)
                return port_pid
            stored = self._state.read_pid(self.name)
            if stored and pid_alive(stored):
                return stored
        pid = self._spawn_script("dev:next", self.name)
        if pid is not None:
            self._state.write_pid(self.name, pid)
        return pid

    def _ensure_spa(self) -> int | None:
        if self._spa_listening():
            port_pid = pid_on_port(self._config.spa_port)
            if port_pid:
                self._state.write_pid(self._SPA_NAME, port_pid)
                return port_pid
        pid = self._spawn_script("dev:spa", self._SPA_NAME)
        if pid is not None:
            self._state.write_pid(self._SPA_NAME, pid)
        return pid

    def _child_env(self) -> dict[str, str]:
        import os

        return {
            **os.environ,
            "PORT": str(self._config.dev_port),
            "SPA_PORT": str(self._config.spa_port),
            "VITE_DEV_PORT": str(self._config.spa_port),
            "OPENAI_PROXY_URL": f"{self._kernel_serve.base_url}/v1",
            "OPENAI_API_KEY": "lca-local",
            "ENABLED_OPENAI": "1",
        }

    def _spawn_script(self, script: str, log_name: str) -> int | None:
        try:
            log_path = self._state.log_file(log_name)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_path.open("a")
            proc = subprocess.Popen(  # noqa: S603
                ["bun", "run", script],  # noqa: S607
                cwd=self._dir,
                env=self._child_env(),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            return proc.pid
        except OSError:
            return None

    def _collect_pids(self) -> list[int]:
        """Collect Next and Vite pids from files and listening ports."""
        pids: list[int] = []
        for name in (self.name, self._SPA_NAME):
            pid = self._state.read_pid(name)
            if pid:
                pids.append(pid)
        for port in (self._config.dev_port, self._config.spa_port):
            port_pid = pid_on_port(port)
            if port_pid:
                pids.append(port_pid)
        return list(set(pids))


def _find_bun_pkg_root(ui_dir: Path, pkg_name: str) -> Path | None:
    """Return the bun-installed package root for ``pkg_name``, or None.

    Bun 解压 npm 包到 ``node_modules/.bun/<scope>+<name>@<version>/node_modules/<pkg_name>``。
    Scope 形式(@scope/name))→ bun 目录前缀 ``@scope+name@<version>``;
    无 scope(name 直接是 foo))→ ``foo@<version>``。
    本函数扫一遍 ``.bun/`` 找到匹配的子目录。
    """
    bun_root = ui_dir / "node_modules" / ".bun"
    if not bun_root.is_dir():
        return None
    # 把 pkg_name 归一化为前缀: "@scope/foo" -> "@scope+foo"; "foo" -> "foo"
    if pkg_name.startswith("@"):
        scope, name = pkg_name[1:].split("/", 1)
        prefix = f"@{scope}+{name}@"
    else:
        prefix = f"{pkg_name}@"
    for entry in bun_root.iterdir():
        if entry.name.startswith(prefix):
            # 包实际解压在 <entry>/node_modules/<pkg_name>
            candidate = entry / "node_modules" / pkg_name
            if candidate.is_dir():
                return candidate
    return None
