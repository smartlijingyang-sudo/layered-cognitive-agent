"""``create_assistant_skill`` must accept a sandbox directory as well as a file.

``sandbox_path`` may point to a single SKILL.md or to a directory containing
SKILL.md plus bundled resources. The tool stages a complete skill directory
before handing it to the overlay, so ``resources/`` and friends survive
alongside SKILL.md.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.infrastructure.tools.assistant.create_skill_tool import AssistantCreateSkillTool

_SKILL_MD = "---\nname: flight-booker\ndescription: d\nreferences: []\n---\nbody"


def _snapshot_dir(local: Path) -> dict[str, bytes]:
    """Read every staged file into memory before the tool cleans up staging."""
    files: dict[str, bytes] = {}
    for path in sorted(local.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(local))] = path.read_bytes()
    return files


class _RecordingOverlay:
    """Records the staged source and snapshots its files before cleanup."""

    def __init__(self) -> None:
        self.calls = 0
        self.local_path: str | None = None
        self.files: dict[str, bytes] = {}

    async def install(self, assistant_id: str, source: object, *, actor: str) -> object:
        self.calls += 1
        local = Path(source.local_path)  # type: ignore[attr-defined]
        self.local_path = str(local)
        self.files = await asyncio.to_thread(_snapshot_dir, local)
        return SimpleNamespace(skill_id="flight-booker", install_path=str(local))


def _tool(overlay: _RecordingOverlay) -> AssistantCreateSkillTool:
    return AssistantCreateSkillTool(overlay=overlay, assistant_id="asst-1")  # type: ignore[arg-type]


def _bind_workspace(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(
        "lca.infrastructure.observability.facade.run.ambit.current_workspace",
        lambda: SimpleNamespace(root=str(root)),
    )


@pytest.mark.asyncio
async def test_directory_install_copies_skill_and_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "ws"
    src = workspace_root / "skill-src"
    (src / "resources").mkdir(parents=True)
    (src / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    (src / "resources" / "helper.py").write_text("HELPER = 1\n", encoding="utf-8")
    _bind_workspace(monkeypatch, workspace_root)

    overlay = _RecordingOverlay()
    obs = await _tool(overlay).execute({"sandbox_path": "skill-src"})

    assert obs.success is True
    assert obs.payload["skill_id"] == "flight-booker"
    assert overlay.calls == 1
    assert "SKILL.md" in overlay.files
    assert "resources/helper.py" in overlay.files


@pytest.mark.asyncio
async def test_single_file_sandbox_path_stages_skill_md(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "ws"
    draft = workspace_root / "draft"
    draft.mkdir(parents=True)
    (draft / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    _bind_workspace(monkeypatch, workspace_root)

    overlay = _RecordingOverlay()
    obs = await _tool(overlay).execute({"sandbox_path": "draft/SKILL.md"})

    assert obs.success is True
    assert overlay.calls == 1
    assert overlay.files["SKILL.md"] == _SKILL_MD.encode()


@pytest.mark.asyncio
async def test_directory_without_skill_md_fails_without_installing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "ws"
    empty = workspace_root / "empty"
    empty.mkdir(parents=True)
    _bind_workspace(monkeypatch, workspace_root)

    overlay = _RecordingOverlay()
    obs = await _tool(overlay).execute({"sandbox_path": "empty"})

    assert obs.success is False
    assert overlay.calls == 0
    assert "缺少 SKILL.md" in (obs.error or "")


@pytest.mark.asyncio
async def test_missing_sandbox_path_fails_without_installing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "ws"
    workspace_root.mkdir(parents=True)
    _bind_workspace(monkeypatch, workspace_root)

    overlay = _RecordingOverlay()
    obs = await _tool(overlay).execute({"sandbox_path": "does-not-exist"})

    assert obs.success is False
    assert overlay.calls == 0
    assert "不存在" in (obs.error or "")


@pytest.mark.asyncio
async def test_missing_workspace_fails_with_unresolvable_message() -> None:
    overlay = _RecordingOverlay()
    obs = await _tool(overlay).execute({"sandbox_path": "skill-src"})

    assert obs.success is False
    assert overlay.calls == 0
    assert "无法解析沙箱路径" in (obs.error or "")
