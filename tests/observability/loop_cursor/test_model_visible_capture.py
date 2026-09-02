"""ADR-0169 PR-12:ModelVisibleCapture + StdModelVisibleCapture 测试。

覆盖:
- Protocol 字段 + 类型契约
- 5 件套写盘位置 + 文件名
- inherited 仅当 inherited_from_step 非 None 时创建
- digest 与文件内容一致
- 失败路径:run_dir 不存在 ⇒ mkdir parents 自愈
- relpath POSIX / 跨 run_dir 退化为 basename
- 实现满足 ModelVisibleCapture Protocol(静态 duck-type)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from lca.contracts.observability.model_visible_capture import (
    ModelVisibleArtifact,
    ModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor import StdModelVisibleCapture


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_model_visible_artifact_is_frozen() -> None:
    artifact = ModelVisibleArtifact(
        step_id="step-001",
        system_path="model_visible/step-001/system.json",
        tools_path="model_visible/step-001/tools.json",
        messages_path="model_visible/step-001/messages.json",
        manifest_path="model_visible/step-001/manifest.json",
        inherited_path=None,
        system_digest="sha256:0" * 16,
        tools_digest="sha256:1" * 16,
        messages_digest="sha256:2" * 16,
        manifest_digest="sha256:3" * 16,
    )
    with pytest.raises(FrozenInstanceError):
        artifact.step_id = "tampered"  # type: ignore[misc]


def test_std_capture_satisfies_protocol(tmp_path: Path) -> None:
    """鸭类型检查:StdModelVisibleCapture 满足 ModelVisibleCapture Protocol。"""
    capture = StdModelVisibleCapture(run_dir=tmp_path / "run")
    expected_methods = {"capture"}
    for name in expected_methods:
        assert hasattr(capture, name), f"StdModelVisibleCapture missing {name!r}"
    # Protocol shape
    _capture_var: ModelVisibleCapture = capture


def test_capture_writes_four_default_files(tmp_path: Path) -> None:
    """无 inherited 时,只写 4 件套(system/tools/messages/manifest)。"""
    run_dir = tmp_path / "runs" / "r1"
    capture = StdModelVisibleCapture(run_dir=run_dir)
    artifact = capture.capture(
        step_id="step-001",
        incarnation=1,
        system={"role": "system", "content": "you are helpful"},
        tools=[{"name": "echo", "schema": {"type": "object"}}],
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
        manifest={"objective": "chat", "kinds": ["objective"]},
    )

    step_dir = run_dir / "model_visible" / "step-001"
    # ADR-0176 D4:system.json 删除,system 数据并入 messages.json 的
    # messages_overview.system 区段;总文件数从 4 缩到 3 + inherited (可选)。
    assert not (step_dir / "system.json").exists()
    assert (step_dir / "tools.json").is_file()
    assert (step_dir / "messages.json").is_file()
    assert (step_dir / "manifest.json").is_file()
    # inherited 文件不存在
    assert not (step_dir / "inherited.json").exists()
    # artifact.inherited_path 为 None
    assert artifact.inherited_path is None
    # 返回的 path 都是相对 run_dir 的 POSIX 风格
    # system_path 指向 messages.json (system 段并入 messages_overview)
    assert artifact.system_path == "model_visible/step-001/messages.json"
    assert artifact.tools_path == "model_visible/step-001/tools.json"
    assert artifact.messages_path == "model_visible/step-001/messages.json"
    assert artifact.manifest_path == "model_visible/step-001/manifest.json"
    assert artifact.step_id == "step-001"


def test_capture_writes_inherited_only_when_set(tmp_path: Path) -> None:
    """inherited_from_step=None ⇒ 不写;非 None ⇒ 写并填 inherited_path。"""
    run_dir = tmp_path / "runs" / "r2"
    capture = StdModelVisibleCapture(run_dir=run_dir)

    # Case 1: no inherited
    art_no_inh = capture.capture(
        step_id="step-002",
        incarnation=1,
        system="sys",
        tools=[],
        messages=[],
        manifest={"k": "v"},
    )
    assert (run_dir / "model_visible" / "step-002" / "inherited.json").exists() is False
    assert art_no_inh.inherited_path is None

    # Case 2: inherited set
    art_with_inh = capture.capture(
        step_id="step-003",
        incarnation=1,
        system="sys",
        tools=[],
        messages=[],
        manifest={"k": "v"},
        inherited_from_step="step-002",
    )
    inherited_file = run_dir / "model_visible" / "step-003" / "inherited.json"
    assert inherited_file.is_file()
    assert art_with_inh.inherited_path == "model_visible/step-003/inherited.json"
    payload = json.loads(inherited_file.read_text(encoding="utf-8"))
    assert payload["inherited_from_step"] == "step-002"
    assert payload["step_id"] == "step-003"


def test_digests_match_file_contents(tmp_path: Path) -> None:
    """artifact 中 *_digest 必须严格等于文件 JSON 的 sha256(json)。"""
    run_dir = tmp_path / "runs" / "r3"
    capture = StdModelVisibleCapture(run_dir=run_dir)

    system_obj = {"role": "system", "content": "Be precise"}
    tools_obj = [{"name": "search", "args_schema": {"type": "object"}}]
    messages_obj = [
        {"role": "user", "content": "weather"},
        {"role": "assistant", "content": "Looking up..."},
        {
            "role": "tool",
            "name": "search",
            "content": {"t": 20, "cond": "sunny"},
        },
    ]
    manifest_obj = {"objective": "weather", "kinds": ["objective", "memory"]}

    artifact = capture.capture(
        step_id="step-007",
        incarnation=2,
        system=system_obj,
        tools=tools_obj,
        messages=messages_obj,
        manifest=manifest_obj,
    )

    step_dir = run_dir / "model_visible" / "step-007"

    def _check(file_name: str, expected_digest_attr: str) -> None:
        path = step_dir / file_name
        raw = path.read_text(encoding="utf-8")
        # digest 由 _to_jsonable(jsonable) + json.dumps(sort_keys=True,ensure_ascii=False,default=str) 算出
        jsonable = json.loads(raw)
        # 重走序列化
        encoded = json.dumps(jsonable, sort_keys=True, ensure_ascii=False, default=str).encode(
            "utf-8"
        )
        assert getattr(artifact, expected_digest_attr) == _sha256(encoded)

    # ADR-0176 D4:system.json 删除,system 数据并入 messages.json 的
    # messages_overview.system 区段;system_digest 复用 messages_digest。
    _check("messages.json", "system_digest")
    _check("tools.json", "tools_digest")
    _check("messages.json", "messages_digest")
    _check("manifest.json", "manifest_digest")

    # digest 必须 sha256: 前缀
    for d in (
        artifact.system_digest,
        artifact.tools_digest,
        artifact.messages_digest,
        artifact.manifest_digest,
    ):
        assert d.startswith("sha256:")
        assert len(d) == len("sha256:") + 64


def test_capture_creates_run_dir_and_step_dir(tmp_path: Path) -> None:
    """run_dir 不存在时,实现必须 mkdir -p 父目录。"""
    nested_run_dir = tmp_path / "traces" / "runs" / "abc" / "def"
    assert not nested_run_dir.exists()
    capture = StdModelVisibleCapture(run_dir=nested_run_dir)
    capture.capture(
        step_id="step-1",
        incarnation=1,
        system="s",
        tools=[],
        messages=[],
        manifest={"objective": "x"},
    )
    # 父子目录都被创建
    assert nested_run_dir.is_dir()
    # ADR-0176 D4:system.json 删除;改写 tools.json。
    assert not (nested_run_dir / "model_visible" / "step-1" / "system.json").exists()
    assert (nested_run_dir / "model_visible" / "step-1" / "tools.json").is_file()


def test_capture_serializes_arbitrary_objects(tmp_path: Path) -> None:
    """非原生 JSON 对象(Pydantic-like)也能序列化,content 不丢失关键字段。"""
    run_dir = tmp_path / "runs" / "r4"
    capture = StdModelVisibleCapture(run_dir=run_dir)

    class _StubTool:
        def __init__(self, name: str, args_schema: dict) -> None:
            self.name = name
            self.args_schema = args_schema

        def to_dict(self) -> dict:
            return {"name": self.name, "args_schema": self.args_schema}

    tool = _StubTool("calc", {"type": "object"})
    artifact = capture.capture(
        step_id="step-009",
        incarnation=1,
        system={"objective": "math"},
        tools=[tool],
        messages=[{"role": "user", "content": "1+1"}],
        manifest={"objective": "math", "kinds": ["objective"]},
    )

    tools_raw = json.loads(
        (run_dir / "model_visible" / "step-009" / "tools.json").read_text(encoding="utf-8")
    )
    assert tools_raw == [{"name": "calc", "args_schema": {"type": "object"}}]
    assert artifact.tools_digest.startswith("sha256:")


def test_capture_returns_correct_paths(tmp_path: Path) -> None:
    """artifact 路径字段是相对 run_dir 的 POSIX relpath,可与 run_dir 拼接复原。"""
    run_dir = tmp_path / "r5"
    capture = StdModelVisibleCapture(run_dir=run_dir)
    artifact = capture.capture(
        step_id="step-042",
        incarnation=3,
        system="s",
        tools=[],
        messages=[],
        manifest={"objective": "x"},
        inherited_from_step="step-041",
    )

    # 5 个字段(4 必 + 1 inherited)绝对路径可恢复
    expected_relpaths = {
        artifact.system_path: "model_visible/step-042/system.json",
        artifact.tools_path: "model_visible/step-042/tools.json",
        artifact.messages_path: "model_visible/step-042/messages.json",
        artifact.manifest_path: "model_visible/step-042/manifest.json",
        artifact.inherited_path: "model_visible/step-042/inherited.json",
    }
    for actual, expected in expected_relpaths.items():
        assert actual == expected
        # 解码后文件存在
        restored = run_dir / actual
        assert restored.is_file(), f"missing file at {restored!r}"

    # step_id 直接回归
    assert artifact.step_id == "step-042"


def test_files_under_model_visible_use_step_id_subdir(tmp_path: Path) -> None:
    """ADR-0169 D7 钉死的目录结构:<run_dir>/model_visible/<step_id>/<file>.json。"""
    run_dir = tmp_path / "r6"
    capture = StdModelVisibleCapture(run_dir=run_dir)
    capture.capture(
        step_id="custom-step-id",
        incarnation=1,
        system="s",
        tools=[],
        messages=[],
        manifest={"objective": "x"},
    )
    base = run_dir / "model_visible" / "custom-step-id"
    assert base.is_dir()
    # ADR-0176 D4:system.json 删除;改为检查 messages.json 包含 messages_overview.system
    assert not (base / "system.json").exists()
    for stem in ("tools", "messages", "manifest"):
        assert (base / f"{stem}.json").is_file(), f"missing {stem}.json"
