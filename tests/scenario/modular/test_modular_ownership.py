"""Regression guards for focused composition boundaries.

These tests protect concrete ownership decisions that reduce the cognitive load of
three evolving surfaces: Session Spine activation, legacy run-environment
preflight, and profile-registerable Gateway modes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.cognition.team.modes.default_modes import (
    _CordisCreatorModeAdapter as CompatibilityCreatorAdapter,
)
from lca.cognition.team.modes.default_modes import _SoloModeAdapter as CompatibilitySoloAdapter
from lca.cognition.team.modes.default_modes import _TeamModeAdapter as CompatibilityTeamAdapter
from lca.plugins.collaboration.modes.cordis_creator import _CordisCreatorModeAdapter
from lca.plugins.collaboration.modes.solo import _SoloModeAdapter
from lca.plugins.collaboration.modes.team import _TeamModeAdapter

ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_execution_environment_only_coordinates_scope_order() -> None:
    """Binding resolution and attachment effects must stay outside the coordinator."""
    source = _source("lca/plugins/transport/webserver/carrier/runs/execute/execution_environment.py")

    assert "lca.plugins.transport.webserver.carrier.runs.execute.environment_bindings" in source
    assert "lca.plugins.transport.webserver.handlers.runs.api.attachment_staging" in source
    assert "resolve_plane_bindings(" not in source
    assert "FileStoreAttachmentIdentity" not in source
    assert "AttachmentStagingStarted" not in source


def test_default_mode_facade_keeps_backward_imports_without_owning_behavior() -> None:
    """Each mode owns its builder and adapter; the facade only re-exports them."""
    source = _source("lca/cognition/team/modes/default_modes.py")

    assert "from lca.plugins.collaboration.modes.solo import" in source
    assert "from lca.plugins.collaboration.modes.team import" in source
    assert "from lca.plugins.collaboration.modes.cordis_creator import" in source
    assert "class _" not in source
    assert "def build_" not in source
    assert CompatibilitySoloAdapter is _SoloModeAdapter
    assert CompatibilityTeamAdapter is _TeamModeAdapter
    assert CompatibilityCreatorAdapter is _CordisCreatorModeAdapter


def test_ingress_only_orchestrates_text_history_and_file_reference_parsing() -> None:
    """Message ingress must not regain its platform-specific parsing implementations."""
    source = _source("lca/plugins/transport/webserver/handlers/runs/ingest/ingress/ingress.py")

    assert "lca.plugins.transport.webserver.handlers.runs.session.message.history" in source
    assert "lca.plugins.transport.webserver.handlers.runs.session.message.text" in source
    assert "lca.plugins.transport.webserver.handlers.runs.api.file_reference_parsing" in source
    assert "re.compile(" not in source
    assert "def _collect_file_refs" not in source


def test_ingest_facade_keeps_policy_cache_transport_and_mirroring_separate() -> None:
    """The stable ingest path must not become a second implementation container."""
    source = _source("lca/plugins/transport/webserver/handlers/runs/ingest/ingest/ingest.py")

    assert "lca.plugins.transport.webserver.handlers.runs.ingest.cache.cache" in source
    assert "lca.plugins.transport.webserver.handlers.runs.ingest.integrity.integrity" in source
    assert "lca.plugins.transport.webserver.handlers.runs.ingest.policy.policy" in source
    assert "lca.plugins.transport.webserver.handlers.runs.ingest.service.service" in source
    assert "class IngestCache" not in source
    assert "async def ingest_file_refs" not in source


def test_doctor_facade_routes_step_tree_and_session_spine() -> None:
    """Doctor facade delegates step-tree 和 Session Spine paths;legacy jsonl 已下线。"""
    source = _source("lca/plugins/transport/webserver/doctor/doctor.py")

    assert "lca.plugins.transport.webserver.doctor.session_check" in source
    assert "lca.plugins.transport.webserver.doctor.step_check" in source
    assert "lca.plugins.transport.webserver.doctor.legacy" not in source
    assert "def _scan_jsonl" not in source
    assert "def _hop_h2" not in source

    legacy_path = ROOT / "lca/plugins/transport/webserver/doctor/legacy.py"
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
    """Retired: terminalizer/status/outcome 浅目录收敛为 terminal/lifecycle.py (INV-ARCH-01/02)。

    新形态由 tests/lca_plugins/transport/webserver/test_run_terminal_coordinator.py 守护。
    """
    pytest.skip("retired: terminalizer.py consolidated into terminal/lifecycle.py; guarded by test_run_terminal_coordinator.py")


def test_openai_shim_is_a_facade_over_protocol_service_and_http_adapters() -> None:
    """OpenAI compatibility must not regain wire, LLM, or HTTP orchestration ownership."""
    source = _source("lca/plugins/transport/webserver/handlers/openai/shim.py")

    assert "handlers.openai.protocol" in source
    assert "handlers.openai.endpoints" in source
    assert "async def " not in source
    assert "def _message_text" not in source

    endpoint_source = _source("lca/plugins/transport/webserver/handlers/openai/endpoints.py")
    assert "handlers.openai.housekeeping" in endpoint_source


# NOTE(2026-10-02, round-0417):test_user_provider_facade_* 已退役——
# lca/infrastructure/host_runtime/providers/user.py 在 43f76e975
# ("remove re-export shells") 被刻意删除,三模块改为直引
# (lca/infrastructure/host_runtime/environment.py:18-20)。新形态由
# tests/architecture/test_no_shallow_reexport_shells.py 守护(断言 user.py
# 不存在)。本 stub 保留占位以防后人误以为测试缺失。
def test_user_provider_facade_separates_account_workspace_and_cli_resources() -> None:
    """Retired: SUT(user.py re-export shell)已刻意删除,见上 NOTE。"""
    pytest.skip("retired: user.py removed in 43f76e975; guarded by test_no_shallow_reexport_shells.py")
