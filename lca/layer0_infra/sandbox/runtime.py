"""Run-bound sandbox runtime — single execution plane (ADR-0050).

One run → one ``SandboxRuntime`` → one backend session (or stateless fallback).
Tools delegate here; they do not manage sessions directly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import structlog

from lca.contracts.models.core.guest_layout import GuestLayout
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    MountManifest,
    SandboxErrorKind,
    SandboxExecResult,
    SandboxFile,
    SandboxResult,
    SessionInfo,
)
from lca.contracts.protocols import Sandbox, SandboxRuntime
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.sandbox.artifact_scanner import GUEST_ARTIFACT_SCANNER
from lca.layer0_infra.sandbox.bootstrap import SANDBOX_INIT_TIMEOUT_S
from lca.layer0_infra.sandbox.error_parse import classify_execution_error
from lca.layer0_infra.sandbox.exec_result import sandbox_exec_result_from
from lca.layer0_infra.sandbox.inspect_prelude import INSPECT_SCRIPT, parse_inspect_stdout
from lca.layer0_infra.sandbox.paths import ONLYBOXES
from lca.layer0_infra.sandbox.runtime_mount import (
    build_mount_manifest,
    load_mount_files,
    verify_mount_or_error,
)

_log = structlog.get_logger(__name__)

PYTHON_LANGUAGES: frozenset[str] = frozenset({"python", "py"})

# Minimal python body — ``_execute_raw`` appends ``GUEST_ARTIFACT_SCANNER``.
_HARVEST_STUB = "pass  # LCA outputs harvest"


def _office_flush_cmd(layout: GuestLayout) -> str:
    return (
        "if command -v officecli >/dev/null 2>&1; then "
        "for ext in pptx docx xlsx; do "
        f'for f in {layout.outputs_dir}/*."$ext"; do '
        '[ -f "$f" ] || continue; '
        'officecli save "$f" --json >/dev/null 2>&1 '
        '|| officecli close "$f" --json >/dev/null 2>&1 '
        "|| true; "
        "done; done; fi"
    )


def _append_artifact_scanner(code: str) -> str:
    """Append artifact scanner so generated files are captured after execution."""
    return code + "\n\n" + GUEST_ARTIFACT_SCANNER + "\n"


def _file_fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RunBoundSandboxRuntime(SandboxRuntime):
    """Run-scoped sandbox: mount → verify → inspect → execute."""

    def __init__(
        self,
        *,
        sandbox: Sandbox,
        store: FileStore,
        run_id: str,
        attachment_ids: tuple[str, ...] = (),
        default_timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        layout: GuestLayout | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._store = store
        self._run_id = run_id
        self._attachment_ids = attachment_ids
        self._default_timeout_s = default_timeout_s
        self.layout = layout if layout is not None else ONLYBOXES
        self._session: SessionInfo | None = None
        self._stateless = False
        self._mount_files: dict[str, bytes] = {}
        self._manifest = MountManifest()
        self._inspect_profile: dict[str, Any] | None = None
        self._ready = False
        self._staged_file_keys: set[str] = set()
        # name → sha256 of last harvested content (run-scoped; skips unchanged re-export)
        self._output_fingerprints: dict[str, str] = {}

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def manifest(self) -> MountManifest:
        return self._manifest

    @property
    def inspect_profile(self) -> dict[str, Any] | None:
        return self._inspect_profile

    @property
    def environment_ready(self) -> bool:
        return self._ready

    async def ensure_ready(self, explicit_ids: list[str] | None = None) -> SandboxExecResult | None:
        """Mount attachments, verify guest paths, auto-inspect. Returns error result on failure."""
        self._mount_files = load_mount_files(self._store, explicit_ids)
        self._manifest = build_mount_manifest(self._store, self._mount_files)

        if self._session is None and not self._stateless:
            try:
                self._session = await self._sandbox.create_session()
            except Exception:
                _log.debug("sandbox_session_create_failed", exc_info=True)
                self._session = None
            if self._session is None:
                self._stateless = True
                _log.info("sandbox_runtime_stateless_fallback", run_id=self._run_id)

        workspace_err = await self._ensure_workspace_dirs()
        if workspace_err is not None:
            return workspace_err

        mount_err = await verify_mount_or_error(
            self._execute_raw,
            manifest=self._manifest,
            timeout_s=min(30, self._default_timeout_s),
        )
        if mount_err is not None:
            return mount_err

        inspect_result = await self._run_inspect_internal()
        if inspect_result is not None and not inspect_result.success:
            return inspect_result

        self._ready = True
        return None

    async def _ensure_workspace_dirs(self) -> SandboxExecResult | None:
        """Create the harvest directory via staged marker file (all backends)."""

        session_id = self._session.session_id if self._session else ""
        timeout_s = min(30, SANDBOX_INIT_TIMEOUT_S, self._default_timeout_s)
        result = await self._sandbox.write_files(
            {".workspace-initialized": b""},
            base_dir=self.layout.outputs_dir,
            session_id=session_id,
            timeout_s=timeout_s,
        )
        if result.success:
            return None
        return sandbox_exec_result_from(
            result,
            error_kind=SandboxErrorKind.INFRA,
            error_summary=result.error or "sandbox workspace init failed",
            suggested_fix="检查 Onlyboxes worker 是否可用",
            mount_manifest=self._manifest,
            environment_ready=False,
        )

    async def inspect(self, *, force: bool = False) -> SandboxExecResult:
        """Return structured file listing and tabular profiles."""
        if self._inspect_profile is not None and not force:
            return SandboxExecResult(
                success=True,
                environment_ready=self._ready,
                mount_manifest=self._manifest,
                inspect_profile=self._inspect_profile,
                stdout=json.dumps(self._inspect_profile, ensure_ascii=False),
            )
        if not self._ready:
            err = await self.ensure_ready()
            if err is not None:
                return err
        result = await self._run_inspect_internal(force=True)
        if result is None:
            return SandboxExecResult(
                success=False,
                error_kind=SandboxErrorKind.INFRA,
                error_summary="inspect 未返回结果",
                mount_manifest=self._manifest,
                environment_ready=self._ready,
            )
        return result

    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        timeout_s: int | None = None,
        invocation_id: str = "",
        explicit_attachment_ids: list[str] | None = None,
        extra_files: dict[str, bytes] | None = None,
        harvest_artifacts: bool = True,
    ) -> SandboxExecResult:
        """Execute user code in the run-bound environment.

        ``harvest_artifacts`` is for ``execute_code`` only. Structured computer
        ops (read/list/edit) must pass False — they are JSON RPCs, not
        deliverable producers, and the scanner would pollute their stdout.
        """
        if not self._ready:
            mount_err = await self.ensure_ready(explicit_attachment_ids)
            if mount_err is not None:
                return mount_err
        elif explicit_attachment_ids:
            merged = load_mount_files(self._store, explicit_attachment_ids)
            if merged != self._mount_files:
                self._mount_files = merged
                self._manifest = build_mount_manifest(self._store, self._mount_files)

        budget = timeout_s if timeout_s is not None else self._default_timeout_s
        raw = await self._execute_raw(
            code,
            language=language,
            timeout_s=budget,
            invocation_id=invocation_id,
            extra_files=extra_files,
            harvest_artifacts=harvest_artifacts,
        )
        # Track fingerprints so a later run_terminal harvest does not re-emit
        # the same outputs/ bytes as this execute_code call.
        self._remember_generated(raw.generated_files)
        if raw.success:
            return sandbox_exec_result_from(
                raw,
                mount_manifest=self._manifest,
                environment_ready=True,
                inspect_profile=self._inspect_profile,
            )

        kind, summary, fix, line_no, partial = classify_execution_error(raw)
        return sandbox_exec_result_from(
            raw,
            error_kind=kind,
            error_summary=summary,
            suggested_fix=fix,
            mount_manifest=self._manifest,
            environment_ready=self._ready,
            partial=partial,
            failed_at_line=line_no,
            inspect_profile=self._inspect_profile,
        )

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        invocation_id: str = "",
        harvest_outputs: bool = True,
    ) -> SandboxResult:
        """Shell command through the session — filesystem state persists across calls.

        Follows the same session-affinity principle as ``execute()``: commands
        within a single run share the same backend session, so ``pip install``
        in step N is visible to ``import`` in step N+1.

        After the command returns, scans the outputs dir (ADR-0046) and
        attaches **new or changed immediate products** (images/PDF/HTML).
        Office binaries stay on disk until ``export_file`` / close / run-end
        seal — they are Works, not per-mutation cards.
        """
        session_id = self._session.session_id if self._session else ""
        result = await self._sandbox.run_terminal(
            command,
            timeout_s=timeout_s,
            invocation_id=invocation_id,
            session_id=session_id,
        )
        if not harvest_outputs:
            return result
        try:
            delta = await self.harvest_output_delta(
                invocation_id=invocation_id or "run_terminal_harvest",
                timeout_s=min(60, timeout_s, self._default_timeout_s),
            )
        except Exception:
            _log.warning(
                "run_terminal_harvest_failed",
                run_id=self._run_id,
                inv=invocation_id,
                exc_info=True,
            )
            return result
        if not delta:
            return result
        merged = tuple(result.generated_files) + delta
        return SandboxResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            success=result.success,
            generated_files=merged,
            error=result.error,
        )

    async def harvest_output_delta(
        self,
        *,
        invocation_id: str = "",
        timeout_s: int | None = None,
    ) -> tuple[SandboxFile, ...]:
        """Scan guest outputs; return only new/changed files.

        Idempotent for unchanged content within a run (sha256 fingerprint).
        Harvest failures return empty — never override the shell command outcome.
        """
        if not self._ready:
            mount_err = await self.ensure_ready()
            if mount_err is not None:
                return ()
        budget = timeout_s if timeout_s is not None else min(60, self._default_timeout_s)
        raw = await self._execute_raw(
            _HARVEST_STUB,
            language="python",
            timeout_s=budget,
            invocation_id=invocation_id or "harvest_outputs",
        )
        return self._delta_generated(raw.generated_files)

    async def scan_output_files(
        self,
        *,
        invocation_id: str = "",
        timeout_s: int | None = None,
    ) -> tuple[SandboxFile, ...]:
        """Read current outputs bytes. Does not update fingerprints."""
        if not self._ready:
            mount_err = await self.ensure_ready()
            if mount_err is not None:
                return ()
        budget = timeout_s if timeout_s is not None else min(60, self._default_timeout_s)
        raw = await self._execute_raw(
            _HARVEST_STUB,
            language="python",
            timeout_s=budget,
            invocation_id=invocation_id or "scan_outputs",
        )
        return tuple(raw.generated_files)

    async def flush_office_residents(self, *, timeout_s: int = 30) -> None:
        """Persist officecli resident handles to disk before a Work publish."""
        await self._flush_office_residents(timeout_s=timeout_s)

    async def _flush_office_residents(self, *, timeout_s: int) -> None:
        """Persist officecli resident handles to disk before harvest."""
        session_id = self._session.session_id if self._session else ""
        try:
            await self._sandbox.run_terminal(
                _office_flush_cmd(self.layout),
                timeout_s=timeout_s,
                invocation_id="office_flush",
                session_id=session_id,
            )
        except Exception:
            _log.debug("office_resident_flush_skipped", run_id=self._run_id, exc_info=True)

    def _remember_generated(self, files: Sequence[SandboxFile]) -> None:
        for sf in files:
            self._output_fingerprints[sf.name] = _file_fingerprint(sf.data)

    def _delta_generated(self, files: Sequence[SandboxFile]) -> tuple[SandboxFile, ...]:
        out: list[SandboxFile] = []
        for sf in files:
            digest = _file_fingerprint(sf.data)
            if self._output_fingerprints.get(sf.name) == digest:
                continue
            self._output_fingerprints[sf.name] = digest
            out.append(sf)
        return tuple(out)

    async def destroy(self) -> None:
        """Release backend session (idempotent)."""
        if self._session is not None:
            sid = self._session.session_id
            self._session = None
            try:
                await self._sandbox.destroy_session(sid)
            except Exception:
                _log.debug("sandbox_runtime_destroy_error", run_id=self._run_id, exc_info=True)
        self._ready = False

    async def _run_inspect_internal(self, *, force: bool = False) -> SandboxExecResult | None:
        if self._inspect_profile is not None and not force:
            return None
        raw = await self._execute_raw(
            INSPECT_SCRIPT,
            timeout_s=min(60, self._default_timeout_s),
            harvest_artifacts=False,
        )
        profile = parse_inspect_stdout(raw.stdout)
        if profile is None:
            if not raw.success:
                return sandbox_exec_result_from(
                    raw,
                    error_kind=SandboxErrorKind.INFRA,
                    error_summary="inspect 执行失败",
                    mount_manifest=self._manifest,
                    environment_ready=False,
                )
            profile = {"files": [], "profiles": {}}
        from lca.layer0_infra.skills.format_routing import enrich_inspect_profile
        from lca.layer0_infra.workspace import get_run_workspace

        profile = enrich_inspect_profile(profile)
        self._inspect_profile = profile
        workspace = get_run_workspace()
        if workspace is not None:
            workspace.inspect_profile = profile
        return SandboxExecResult(
            success=True,
            stdout=raw.stdout,
            stderr=raw.stderr,
            exit_code=raw.exit_code,
            mount_manifest=self._manifest,
            environment_ready=True,
            inspect_profile=profile,
        )

    async def _execute_raw(
        self,
        code: str,
        *,
        language: str = "python",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        invocation_id: str = "",
        extra_files: dict[str, bytes] | None = None,
        harvest_artifacts: bool = True,
    ) -> SandboxResult:
        # Phase 1: Stage files incrementally (only new files)
        all_files: dict[str, bytes | str] = {**self._mount_files, **(extra_files or {})}
        new_files = {k: v for k, v in all_files.items() if k not in self._staged_file_keys}
        if new_files:
            session_id = self._session.session_id if self._session else ""
            await self._sandbox.write_files(
                new_files, base_dir=self.layout.root, session_id=session_id
            )
            self._staged_file_keys.update(new_files.keys())

        # Phase 2: Execute. Artifact scan is execute_code / harvest only —
        # LobeHub file ops print one JSON object and stop.
        lang_key = language.lower() if language else "python"
        if harvest_artifacts and lang_key in PYTHON_LANGUAGES:
            code = _append_artifact_scanner(code)

        if self._session is not None and not self._stateless:
            return await self._sandbox.run_in_session(
                session_id=self._session.session_id,
                code=code,
                language=language,
                timeout_s=timeout_s,
                invocation_id=invocation_id,
            )
        return await self._sandbox.run(
            code=code,
            language=language,
            timeout_s=timeout_s,
            invocation_id=invocation_id,
        )
