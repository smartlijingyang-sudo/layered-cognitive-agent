"""ADR-0169 D7:StdModelVisibleCapture —— 默认实现。

职责:
- 一次性写 5 件套到 ``<run_dir>/model_visible/step_<step_id>/{...}.json``
  (system / tools / messages / manifest / inherited)。
- inherited 文件仅在 ``inherited_from_step`` 非 None 时创建
  (对应 ADR-0169 §9 "checkpoint resume" 用例)。
- 返回 ``ModelVisibleArtifact``,由 LLM adapter 边界调用
  ``cursor.record_request_header(...)`` 时消费。

设计要点(评审 S1 处方 + ADR-0169 D7):
- Capture **不持有** cursor 引用 —— 协议边界不夹带。
  调用方(LLM adapter)在捕获时已持有 cursor.snapshot,
  把 step_id / incarnation 作为参数传入。
- 仅依赖 stdlib:hashlib / json / pathlib。
- 序列化策略:任意可序列化对象用 ``json.dumps(... default=str)`` 保底,
  对 Pydantic / dataclass 实例由 ``__dict__`` 退化为 dict。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lca.contracts.observability.model_visible_capture import (
    ModelVisibleArtifact,
    ModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    relative_posix as _relative_posix,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    to_jsonable as _to_jsonable,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    write_json as _write_json,
)

_log = logging.getLogger(__name__)


class StdModelVisibleCapture(ModelVisibleCapture):
    """默认 ModelVisibleCapture 实现。

    用法::

        capture = StdModelVisibleCapture(run_dir=Path("traces/runs/<run_id>"))
        artifact = capture.capture(
            step_id="step-007",
            incarnation=1,
            system={"role": "system", "content": "..."},
            tools=[{"name": "echo"}, ...],
            messages=[{"role": "user", "content": "hi"}],
            manifest={"objective": "...", "kinds": ["objective"]},
            inherited_from_step="step-006",  # 可选
        )
        cursor.record_request_header(RequestHeader(
            ...,
            system_digest=artifact.system_digest,
            system_path=artifact.system_path,
            ...
        ))

    写入位置(ADR-0169 D7 + ADR-0176 D4):
        <run_dir>/model_visible/<step_id>/tools.json
        <run_dir>/model_visible/<step_id>/messages.json  # messages_overview.system + messages[]
        <run_dir>/model_visible/<step_id>/manifest.json
        <run_dir>/model_visible/<step_id>/inherited.json   # 当 inherited_from_step 非 None
        # 注:system_prompt.json / system_prompt_sections.json 由 StdReasonerPromptCapture 写,
        #   不再由本 Capture 写。system 数据合并到 messages.json 的 messages_overview.system 区段。
    """

    def __init__(self, *, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)

    @property
    def run_dir(self) -> Path:
        """返回注入的 run_dir。"""
        return self._run_dir

    def capture(
        self,
        *,
        step_id: str,
        incarnation: int,
        system: Any,
        tools: list[Any],
        messages: list[Any],
        manifest: Any,
        inherited_from_step: str | None = None,
    ) -> ModelVisibleArtifact:
        # 路径就位:<run_dir>/model_visible/<step_id>/
        step_dir = self._run_dir / "model_visible" / step_id

        # ADR-0176 D4:删除 system.json(系统提示合并到 messages.json 的
        # messages_overview.system 区段);tools / messages / manifest 三个文件保留。
        # NOTE:per-step "manifest.json" 与 run-level RunLocator.manifest_path
        # 不冲突 —— 文件位于不同目录(model_visible/<step_id>/ vs <run_dir>/),
        # 但字面同名有混淆风险;后续 PR 改 per-step artifact 名时统一。
        tools_path = step_dir / "tools.json"
        messages_path = step_dir / "messages.json"
        manifest_path = step_dir / "manifest.json"

        tools_digest = _write_json(tools_path, _to_jsonable(tools))

        # messages.json 现在承载两件事:
        # - messages_overview.system:送入 LLM 的 system 段(原 system.json 数据)
        # - messages:实际发给模型的消息序列
        messages_payload: dict[str, Any] = {
            "incarnation": incarnation,
            "step_id": step_id,
            "messages_overview": {
                "system": _to_jsonable(system),
            },
            "messages": _to_jsonable(messages),
        }
        messages_digest = _write_json(messages_path, messages_payload)

        manifest_with_meta = {
            "incarnation": incarnation,
            "step_id": step_id,
            "body": _to_jsonable(manifest),
        }
        manifest_digest = _write_json(manifest_path, manifest_with_meta)

        # inherited:仅当 inherited_from_step 非 None 时写
        inherited_path: Path | None = None
        if inherited_from_step is not None:
            inherited_path = step_dir / "inherited.json"
            _write_json(
                inherited_path,
                {
                    "inherited_from_step": inherited_from_step,
                    "incarnation": incarnation,
                    "step_id": step_id,
                },
            )

        # ADR-0176 D4:system_path 不再指向独立 system.json,而是 messages.json
        # 的 messages_overview.system 区段;前端 viewer 据此找到完整 system 上下文。
        # COMPAT(delete-when: 所有调用方已迁移到 system_path 指向 messages.json,
        # tracking: ADR-0176 D4)
        return ModelVisibleArtifact(
            step_id=step_id,
            system_path=_relative_posix(self._run_dir, messages_path),
            tools_path=_relative_posix(self._run_dir, tools_path),
            messages_path=_relative_posix(self._run_dir, messages_path),
            manifest_path=_relative_posix(self._run_dir, manifest_path),
            inherited_path=(
                _relative_posix(self._run_dir, inherited_path)
                if inherited_path is not None
                else None
            ),
            # system_digest 复用 messages_digest;调用方需要时仍可读 system 段
            # 的 content_digest。本字段保留 Protocol 兼容性。
            system_digest=messages_digest,
            tools_digest=tools_digest,
            messages_digest=messages_digest,
            manifest_digest=manifest_digest,
        )


__all__ = ["StdModelVisibleCapture"]
