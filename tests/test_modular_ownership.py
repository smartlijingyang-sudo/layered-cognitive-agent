"""Regression guards for focused composition boundaries.

These tests protect concrete ownership decisions that reduce the cognitive load of
three evolving surfaces: Session Spine activation, legacy run-environment
preflight, and profile-registerable Gateway modes.
"""

from __future__ import annotations

from pathlib import Path

from lca.cognition.team.modes.cordis_creator_mode import _CordisCreatorModeAdapter
from lca.cognition.team.modes.default_modes import (
    _CordisCreatorModeAdapter as CompatibilityCreatorAdapter,
)
from lca.cognition.team.modes.default_modes import _SoloModeAdapter as CompatibilitySoloAdapter
from lca.cognition.team.modes.default_modes import _TeamModeAdapter as CompatibilityTeamAdapter
from lca.cognition.team.modes.solo_mode import _SoloModeAdapter
from lca.cognition.team.modes.team_mode import _TeamModeAdapter

ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_session_registry_is_a_facade_over_activation_and_command_routing() -> None:
    """The public registry must not regain storage, recovery, or command ownership."""
    source = _source("lca/harness/agent/registry.py")

    assert "SessionActivator" in source
    assert "AgentCommandRouter" in source
    assert "SessionStore(" not in source
    assert "_idempotency" not in source
    assert "_entry_or_recover" not in source


def test_execution_environment_only_coordinates_scope_order() -> None:
    """Binding resolution and attachment effects must stay outside the coordinator."""
    source = _source("gateway/runs/execute/execution_environment.py")

    assert "lca.plugins.transport.webserver.handlers.runs.execute.environment_bindings" in source
    assert "lca.plugins.transport.webserver.handlers.runs.api.attachment_staging" in source
    assert "resolve_plane_bindings(" not in source
    assert "FileStoreAttachmentIdentity" not in source
    assert "AttachmentStagingStarted" not in source


def test_default_mode_facade_keeps_backward_imports_without_owning_behavior() -> None:
    """Each mode owns its builder and adapter; the old module only re-exports them."""
    source = _source("gateway/plugins/default_modes.py")

    assert "from lca.cognition.team.modes.solo_mode import" in source
    assert "from lca.cognition.team.modes.team_mode import" in source
    assert "from lca.cognition.team.modes.cordis_creator_mode import" in source
    assert "class _" not in source
    assert "def build_" not in source
    assert CompatibilitySoloAdapter is _SoloModeAdapter
    assert CompatibilityTeamAdapter is _TeamModeAdapter
    assert CompatibilityCreatorAdapter is _CordisCreatorModeAdapter


def test_ingress_only_orchestrates_text_history_and_file_reference_parsing() -> None:
    """Message ingress must not regain its platform-specific parsing implementations."""
    source = _source("gateway/runs/ingest/ingress.py")

    assert "lca.plugins.transport.webserver.handlers.runs.session.message_history" in source
    assert "lca.plugins.transport.webserver.handlers.runs.session.message_text" in source
    assert "lca.plugins.transport.webserver.handlers.runs.api.file_reference_parsing" in source
    assert "re.compile(" not in source
    assert "def _collect_file_refs" not in source


def test_ingest_facade_keeps_policy_cache_transport_and_mirroring_separate() -> None:
    """The stable ingest path must not become a second implementation container."""
    source = _source("gateway/runs/ingest/ingest.py")

    assert "lca.plugins.transport.webserver.handlers.runs.ingest.cache" in source
    assert "lca.plugins.transport.webserver.handlers.runs.ingest.integrity" in source
    assert "lca.plugins.transport.webserver.handlers.runs.ingest.policy" in source
    assert "lca.plugins.transport.webserver.handlers.runs.ingest.service" in source
    assert "class IngestCache" not in source
    assert "async def ingest_file_refs" not in source


def test_doctor_facade_routes_step_tree_and_session_spine() -> None:
    """Doctor facade delegates step-tree 和 Session Spine paths;legacy jsonl 已下线。"""
    source = _source("lca/plugins/transport/webserver/handlers/runs/doctor/doctor.py")

    assert "lca.plugins.transport.webserver.handlers.runs.doctor.session_check" in source
    assert "lca.plugins.transport.webserver.handlers.runs.doctor.step_check" in source
    assert "lca.plugins.transport.webserver.handlers.runs.doctor.legacy" not in source
    assert "def _scan_jsonl" not in source
    assert "def _hop_h2" not in source

    legacy_path = ROOT / "lca/plugins/transport/webserver/handlers/runs/doctor/legacy.py"
    assert not legacy_path.exists()


def test_temporal_memory_store_delegates_schema_and_record_codec() -> None:
    """The store adapter must not regain DDL or SQLite-row serialization ownership."""
    source = _source("lca/infrastructure/state_store/sqlite_temporal_memory.py")

    assert "sqlite_temporal_codec" in source
    assert "sqlite_temporal_schema" in source
    assert "CREATE TABLE" not in source
    assert "def _record_values" not in source
    assert "def _row_to_record" not in source


def test_terminalizer_only_coordinates_terminal_transition_order() -> None:
    """Terminal status, artifact closure, manifest, and exporter cleanup have owners."""
    source = _source("gateway/runs/terminal/terminalizer.py")

    assert "lca.plugins.transport.webserver.handlers.runs.terminal.status" in source
    assert "lca.plugins.transport.webserver.handlers.runs.observability.artifact_closure" in source
    assert "lca.plugins.transport.webserver.handlers.runs.terminal.materialization" in source
    assert "lca.plugins.transport.webserver.handlers.runs.lifecycle.export_disposal" in source
    assert "def _derive_terminal_status" not in source
    assert "def _record_terminal_materialization" not in source


def test_openai_shim_is_a_facade_over_protocol_service_and_http_adapters() -> None:
    """OpenAI compatibility must not regain wire, LLM, or HTTP orchestration ownership."""
    source = _source("gateway/openai_shim.py")

    assert "gateway.openai_protocol" in source
    assert "gateway.openai_endpoints" in source
    assert "async def " not in source
    assert "def _message_text" not in source

    endpoint_source = _source("gateway/openai_endpoints.py")
    assert "gateway.openai_housekeeping" in endpoint_source


def test_user_provider_facade_separates_account_workspace_and_cli_resources() -> None:
    """Host-runtime user resources must keep independently managed lifecycles."""
    source = _source("lca/infrastructure/host_runtime/providers/user.py")

    assert "providers.user_account" in source
    assert "providers.user_workspace" in source
    assert "providers.user_cli" in source
    assert "class " not in source
