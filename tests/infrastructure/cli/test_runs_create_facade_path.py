"""Behavioural tests for ``lca-ops runs create --facade`` (PR-0199-P1-13).

The CLI now exposes two execution paths:

  * **Default (production):** HTTP shell-out to ``${base_url}/runs``
    (unchanged from before P1-13; the HTTP layer is already
    RuntimeFacade-aligned via P1-11).
  * **Offline / dev / test (``--facade``):** in-process dispatch
    through :class:`DefaultRuntimeFacade`. Used to prove CLI↔HTTP
    cross-surface parity — the same ``RunIntent`` yields the same
    ``plan_ref`` / ``activation_ref`` across both surfaces.

These tests pin the ``--facade`` path's contract (I-HPC-1, I-HPC-2,
I-HPC-3) and the COMPAT marker; the default HTTP path is regression-
tested at the end so the production seam is not silently broken.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from lca.application.runtime.plan_resolution import (
    PlanResolutionResult,
    PlanResolutionService,
)
from lca.harness.runtime.activation_ref import (
    compute_activation_ref,
    is_activation_ref,
)
from lca.infrastructure.cli.commands.runs.runs import CLIInProcessDispatcher

_RUNS_MODULE = "lca.infrastructure.cli.commands.runs.runs"
_PLAN_RESOLUTION_MODULE = "lca.application.runtime.plan_resolution"

# Deterministic refs that the patched PlanResolutionService returns.
# Production code hashes the plan; tests want a stable string so we can
# re-derive activation_ref and assert equality.
_PLAN_REF = "plan-facade-test"
_GRAPH_REF = "graph-facade-test"
_PLUGIN_SET_REF = "plugin-set-facade-test"


# ── helpers ────────────────────────────────────────────────────────


class _StubPlan:
    """Minimal stand-in for ``CompiledRunPlan`` (matches the existing
    test pattern in tests/architecture/test_0199_phase1_acceptance.py).

    The facade only forwards the compiled_plan object — it does not
    read any of its attributes — so a stub class is sufficient.
    """

    profile_path = "/abs/profiles/sample.yaml"


def _stub_plan_result() -> PlanResolutionResult:
    return PlanResolutionResult(
        plan_ref=_PLAN_REF,
        graph_ref=_GRAPH_REF,
        plugin_set_ref=_PLUGIN_SET_REF,
        compiled_plan=_StubPlan(),
    )


@pytest.fixture
def plan_service_mock() -> MagicMock:
    """Patch the source ``PlanResolutionService`` class for one test.

    Yields a ``MagicMock`` standing in for the constructed instance so
    callers can assert the CLI delegated K1+K2 to it (brief test #11).
    The patch is automatically torn down on fixture exit so the next
    test sees a clean module state.
    """
    service_mock = MagicMock(spec=PlanResolutionService)
    service_mock.resolve_refs.return_value = _stub_plan_result()
    with patch(
        f"{_PLAN_RESOLUTION_MODULE}.PlanResolutionService",
        return_value=service_mock,
    ):
        yield service_mock


def _build_runs_app() -> typer.Typer:
    """Build a fresh typer app for per-test registration."""
    return typer.Typer()


def _register_runs(app: typer.Typer) -> None:
    """Register ``runs create`` on a fresh app instance."""
    from lca.infrastructure.cli.commands.runs.runs import register

    register(app)


def _extract_field(stdout: str, name: str) -> str:
    """Parse ``name = value`` from typer's facade-path output."""
    pattern = re.compile(rf"{re.escape(name)}\s+=\s+(\S+)")
    match = pattern.search(stdout)
    assert match is not None, f"field {name!r} not found in output:\n{stdout}"
    return match.group(1)


def _invoke_facade(*args: str, session_id: str | None = None) -> str:
    """Invoke ``runs create --facade <args>`` and return stdout.

    Asserts exit_code == 0 with the failure message attached so the
    tests that only inspect stdout get a clean signal.
    """
    from lca.infrastructure.cli.commands.runs.runs import register

    app = typer.Typer()
    register(app)
    runner = CliRunner()
    extra: list[str] = []
    if session_id is not None:
        extra += ["--session-id", session_id]
    result = runner.invoke(
        app,
        [
            "runs",
            "create",
            "--facade",
            "--user-text",
            "hello",
            "--profile",
            "web-standard",
            *extra,
            *args,
        ],
    )
    assert result.exit_code == 0, (
        f"exit_code={result.exit_code}\nstdout:\n{result.stdout}\n"
        f"stderr:\n{getattr(result, 'stderr', '')}"
    )
    return result.stdout


# ── typer registration ──────────────────────────────────────────────


class TestFacadeFlagRegistration:
    """The ``--facade`` flag must be visible to typer so operators and
    tests can discover / invoke it."""

    def test_facade_flag_registered(self) -> None:
        """``--facade`` appears in ``runs create --help`` output."""
        app = _build_runs_app()
        _register_runs(app)
        runner = CliRunner()
        result = runner.invoke(app, ["runs", "create", "--help"])
        assert result.exit_code == 0
        assert "--facade" in result.stdout

    def test_facade_default_is_false(self) -> None:
        """Inspecting the underlying function shows ``facade`` defaults to False.

        We assert on the typer option metadata instead of parsing the
        rich-formatted ``--help`` output (typer collapses ``[default: ...]``
        for bool flags when the default is False). The CLI's ``_create``
        is the canonical source for option defaults.
        """
        import inspect

        from lca.infrastructure.cli.commands.runs import runs as runs_module

        sig = inspect.signature(runs_module._create)
        param = sig.parameters["facade"]
        # typer ``Option(False, ...)`` is exposed as a ``typer.Option``
        # sentinel; the actual default lives on ``OptionInfo.default``.
        assert param.default.default is False


# ── facade path: behaviour ──────────────────────────────────────────


class TestFacadePathBehaviour:
    """The ``--facade`` flag triggers in-process dispatch."""

    def test_facade_path_emits_plan_ref(self, plan_service_mock: MagicMock) -> None:
        """#3: ``--facade`` output contains ``plan_ref =`` token."""
        stdout = _invoke_facade()
        assert "plan_ref" in stdout
        assert f"plan_ref         = {_PLAN_REF}" in stdout
        assert plan_service_mock.resolve_refs.call_count == 1

    def test_facade_path_emits_activation_ref(self, plan_service_mock: MagicMock) -> None:
        """#4: ``--facade`` output contains ``activation_ref = lca.activation.v1:...``."""
        stdout = _invoke_facade(session_id="sess_emit")
        match = re.search(r"activation_ref\s+=\s+(\S+)", stdout)
        assert match is not None, f"activation_ref not found: {stdout!r}"
        activation_ref = match.group(1)
        assert activation_ref.startswith("lca.activation.v1:")
        assert is_activation_ref(activation_ref)

    def test_facade_path_skips_http(self, plan_service_mock: MagicMock) -> None:
        """#5: ``urllib.request.urlopen`` is NEVER called in ``--facade`` mode."""
        urlopen_mock = MagicMock()
        with patch(f"{_RUNS_MODULE}.urllib.request.urlopen", urlopen_mock):
            stdout = _invoke_facade(session_id="sess_skip_http")
        assert "plan_ref" in stdout
        urlopen_mock.assert_not_called()

    def test_facade_path_activation_ref_matches_compute(self, plan_service_mock: MagicMock) -> None:
        """#6: the printed ``activation_ref`` equals
        ``compute_activation_ref(plan_ref, graph_ref, plugin_set_ref, session_id)``.
        """
        stdout = _invoke_facade(session_id="sess_test_xyz")

        activation_ref = _extract_field(stdout, "activation_ref")
        plan_ref = _extract_field(stdout, "plan_ref")
        graph_ref = _extract_field(stdout, "graph_ref")
        plugin_set_ref = _extract_field(stdout, "plugin_set_ref")
        session_id = _extract_field(stdout, "session_id")

        expected = compute_activation_ref(
            plan_ref=plan_ref,
            graph_ref=graph_ref,
            plugin_set_ref=plugin_set_ref,
            session_id=session_id,
        )
        assert activation_ref == expected
        assert plan_ref == _PLAN_REF
        assert graph_ref == _GRAPH_REF
        assert plugin_set_ref == _PLUGIN_SET_REF
        assert session_id == "sess_test_xyz"

    def test_facade_path_session_id_generated_when_missing(
        self, plan_service_mock: MagicMock
    ) -> None:
        """#7: omitting ``--session-id`` → output session_id starts with ``sess_``."""
        stdout = _invoke_facade()
        session_id = _extract_field(stdout, "session_id")
        assert session_id.startswith("sess_")

    def test_facade_path_session_id_preserved_when_provided(
        self, plan_service_mock: MagicMock
    ) -> None:
        """#8: ``--session-id sess_test_xyz`` → output session_id is verbatim."""
        stdout = _invoke_facade(session_id="sess_test_xyz")
        session_id = _extract_field(stdout, "session_id")
        assert session_id == "sess_test_xyz"

    def test_facade_path_intent_does_not_carry_agent(self, plan_service_mock: MagicMock) -> None:
        """#9: ``--agent agt_xxx`` does NOT affect the activation — agent is
        not in CliRunArgs (L0 principal metadata, intentionally dropped per
        ADR-0199 I-HPC-1).

        We confirm this indirectly: changing the agent does not change the
        plan_ref or activation_ref because the adapter does not carry
        ``agent`` into the RunIntent (verified in the adapter's tests; this
        is the end-to-end regression through the CLI).
        """
        stdout_a = _invoke_facade("--agent", "agt_alpha", session_id="sess_agent")
        stdout_b = _invoke_facade("--agent", "agt_beta", session_id="sess_agent")

        plan_ref_a = _extract_field(stdout_a, "plan_ref")
        plan_ref_b = _extract_field(stdout_b, "plan_ref")
        activation_ref_a = _extract_field(stdout_a, "activation_ref")
        activation_ref_b = _extract_field(stdout_b, "activation_ref")
        assert plan_ref_a == plan_ref_b == _PLAN_REF
        assert activation_ref_a == activation_ref_b

    def test_facade_path_uses_plan_resolution_service(self, plan_service_mock: MagicMock) -> None:
        """#11: ``PlanResolutionService.resolve_refs`` was invoked exactly once."""
        stdout = _invoke_facade(session_id="sess_used")
        assert "plan_ref" in stdout
        # PlanResolutionService(...) was constructed and resolve_refs
        # called once with the parsed ``profile`` + ``session_id``.
        assert plan_service_mock.resolve_refs.call_count == 1
        (path_arg,), kwargs = plan_service_mock.resolve_refs.call_args
        assert str(path_arg) == "web-standard"
        assert kwargs["session_id"] == "sess_used"


# ── CLIInProcessDispatcher (the seam the facade path uses) ─────────


class TestCLIInProcessDispatcher:
    """The CLI-side dispatcher must satisfy the structural
    ``RunDispatcher`` protocol used by :class:`DefaultRuntimeFacade`.
    """

    def test_satisfies_run_dispatcher_protocol(self) -> None:
        """``isinstance(CLIInProcessDispatcher(), RunDispatcher)`` is True."""
        from lca.application.runtime.default_facade import RunDispatcher

        assert isinstance(CLIInProcessDispatcher(), RunDispatcher)

    async def test_dispatch_run_returns_synthetic_handle(self) -> None:
        """``dispatch_run`` returns a synthetic handle correlated with the activation."""
        from lca.contracts.runtime.facade import RunHandle

        dispatcher = CLIInProcessDispatcher()
        activation = MagicMock()
        activation.activation_ref = "lca.activation.v1:" + "a" * 64
        handle = await dispatcher.dispatch_run(activation, MagicMock())
        # ``RunHandle`` is a ``NewType`` over ``str`` (erases at runtime).
        assert type(handle) is str
        assert isinstance(handle, str)
        assert handle == RunHandle(f"cli_facade_{activation.activation_ref[:16]}")

    async def test_dispatch_resume_returns_synthetic_handle(self) -> None:
        """``dispatch_resume`` returns a synthetic resume handle."""
        from lca.contracts.runtime.facade import RunHandle

        dispatcher = CLIInProcessDispatcher()
        handle = await dispatcher.dispatch_resume(MagicMock(), "run_xyz_123")
        # ``RunHandle`` is a ``NewType`` over ``str`` (erases at runtime).
        assert type(handle) is str
        assert isinstance(handle, str)
        assert handle == RunHandle("cli_facade_resume_run_xyz_123")


# ── COMPAT marker presence ────────────────────────────────────────


class TestCompatMarker:
    def test_facade_path_compat_comment_present(self) -> None:
        """#10: ``runs.py`` carries the ADR-0199 COMPAT template (owner /
        from / to / delete_when / forbidden_new_usage)."""
        from lca.infrastructure.cli.commands.runs import runs as runs_module

        source = Path(runs_module.__file__).read_text(encoding="utf-8")
        assert "COMPAT(owner: ADR-0199" in source
        assert "from: CLI-direct-resolve" in source
        assert "to: RuntimeFacade" in source
        assert "delete_when:" in source
        assert "forbidden_new_usage:" in source


# ── HTTP path regression (default mode unchanged) ────────────────


class TestHttpPathRegression:
    """The default HTTP path (no ``--facade``) must STILL hit
    ``urllib.request.urlopen`` — P1-13 only adds the facade branch; it
    does NOT change the production seam (HPC-L2).
    """

    def test_http_path_still_works_unchanged(self) -> None:
        """#12: invoking ``runs create`` without ``--facade`` calls
        ``urllib.request.urlopen`` (regression — the production HTTP
        path was never broken).
        """
        urlopen_mock = MagicMock()
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps(
            {"run_id": "run_regression", "trace_id": "tr_regression", "live_url": "/x"}
        ).encode("utf-8")
        urlopen_mock.return_value.__enter__.return_value = response

        app = _build_runs_app()
        _register_runs(app)
        runner = CliRunner()
        with patch(f"{_RUNS_MODULE}.urllib.request.urlopen", urlopen_mock):
            result = runner.invoke(
                app,
                [
                    "runs",
                    "create",
                    "--user-text",
                    "hello",
                    "--profile",
                    "web-standard",
                    "--base-url",
                    "http://127.0.0.1:8765",
                ],
            )
        assert result.exit_code == 0, result.stdout
        assert urlopen_mock.call_count == 1
        assert "run_regression" in result.stdout


# ── Module-level sanity ────────────────────────────────────────────


def test_module_docstring_cites_adr_0199() -> None:
    """The module docstring of ``runs.py`` cites ADR-0199 + I-HPC-1."""
    from lca.infrastructure.cli.commands.runs import runs as runs_module

    source = Path(runs_module.__file__).read_text(encoding="utf-8")
    assert "ADR-0199" in source
    assert "I-HPC-1" in source
