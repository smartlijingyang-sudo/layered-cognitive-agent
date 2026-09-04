"""StandardCursor —— 零 token 确定性回放(ADR-0167 D10 + ADR-0185 PR-3/PR-4)。

读取 ``traces/runs/<run_id>/journal.json`` + ``<run_id>.spine.jsonl`` fold 重建：

- ``messages``: 走 fold 路径(``spine.llm.request.header`` payload
  原文,ADR-0185 §3.7);fold 缺失时由 ``journal.json`` 推导并标
  ``inferred=True``。
- ``actions``: 直接读 step 的 ``tool_calls[]`` + ``tool_results[]``,已为
  事实记录。
- ``digest_verified``: fold 路径 = True(fold canonical header 字节级稳定);
  journal 推导路径 = False。

``with_override(...)`` 仅返回 diff；**绝不私自执行工具**。
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any

from lca.contracts.observability.replay import StepContextAt


class StandardCursor:
    """默认 ReplayCursor 实现（ADR-0167 D10）。"""

    def __init__(self, traces_root: Path) -> None:
        self._root = Path(traces_root)

    def at(self, *, run_id: str, step_index: int) -> StepContextAt:
        from lca.infrastructure.observability.journal.step.reader import (
            read_step_document,
        )
        from lca.infrastructure.observability.replay.fold_source import (
            SOURCE_FOLD,
            fold_model_visible,
        )

        run_dir = self._root / "runs" / run_id
        journal_path = run_dir / "journal.json"
        if not journal_path.exists():
            raise FileNotFoundError(f"journal.json not found: {journal_path}")
        doc = read_step_document(journal_path)
        step = doc.step_by_index(step_index)
        if step is None:
            raise IndexError(f"step_index={step_index} not in {journal_path}")

        # ADR-0185 PR-4:fold 路径是唯一重建入口;fold 缺失时退化为
        # journal 推导(inferred=True)。
        folded = fold_model_visible(
            run_dir=run_dir,
            run_id=run_id,
            step_id=step.step_id,
        )
        if folded is not None:
            # fold 命中:header 来自 canonical fold,messages/tools/manifest 来自
            # 最近一条 request/header payload 原文。
            return StepContextAt(
                step_index=step_index,
                step_id=step.step_id,
                request_header=self._header_dict_from_fold(folded),
                messages=folded.messages,
                tool_schemas=folded.tool_schemas,
                context_manifest=folded.manifest or {},
                actions=self._actions_from_step(step),
                source=SOURCE_FOLD,
                inferred=False,
                digest_verified=folded.digest_verified,
            )

        # fold 缺失:由 journal 推导（inferred=True）
        messages = self._infer_messages(step)

        return StepContextAt(
            step_index=step_index,
            step_id=step.step_id,
            request_header=None,
            messages=tuple(messages),
            tool_schemas=(),
            context_manifest={},
            actions=self._actions_from_step(step),
            source="replayed",
            inferred=True,
            digest_verified=False,
        )

    def with_override(
        self,
        *,
        run_id: str,
        step_index: int,
        tool_args_overrides: dict[str, Any],
    ) -> StepContextAt:
        """仅算 diff —— 禁止私自执行（ADR-0167 D10 / D12 I-VIEW3）。

        形态：clone ctx，把 ``actions[i].data.arguments`` 替换为 overrides；
        不调 tool；返回新 ctx。调用方决定是否 ``lca-ops journal rerun``。
        """
        ctx = self.at(run_id=run_id, step_index=step_index)
        new_actions: list[Any] = []
        for act in ctx.actions:
            new_act = dict(act)
            data_obj = new_act.get("data")
            tool_name = getattr(data_obj, "name", None) or getattr(data_obj, "tool_name", None)
            if tool_name and tool_name in tool_args_overrides and hasattr(data_obj, "arguments"):
                new_act["data"] = dc_replace(data_obj, arguments=tool_args_overrides[tool_name])
            new_actions.append(new_act)
        return StepContextAt(
            step_index=ctx.step_index,
            step_id=ctx.step_id,
            request_header=ctx.request_header,
            messages=ctx.messages,
            tool_schemas=ctx.tool_schemas,
            context_manifest=ctx.context_manifest,
            actions=tuple(new_actions),
            source=ctx.source,
            inferred=ctx.inferred,
            digest_verified=ctx.digest_verified,
        )

    # ── helpers ─────────────────────────────────────────

    @staticmethod
    def _actions_from_step(step: Any) -> tuple[Any, ...]:
        """step → actions 序列;fold 路径与 journal 推导路径共用。"""
        actions: list[Any] = []
        if step.tool_call is not None:
            actions.append({"kind": "tool_call", "data": step.tool_call})
        if step.tool_result is not None:
            actions.append({"kind": "tool_result", "data": step.tool_result})
        return tuple(actions)

    @staticmethod
    def _header_dict_from_fold(folded: Any) -> dict[str, Any]:
        """``FoldedModelVisible`` → ``request_header`` dict。

        ``header_digest`` 字段提供 fold canonical sha256,viewer 可用其
        对位 publisher ``previous_header_digest``。
        """
        header = folded.header
        if header is None:
            return {}
        out: dict[str, Any] = {
            "system": header.system or "",
            "tools": list(header.tools or ()),
            "config": dict(header.config) if header.config is not None else None,
            "adapter_defaults": (
                dict(header.adapter_defaults) if header.adapter_defaults is not None else None
            ),
            "header_digest": folded.header_digest,
            "source": folded.source,
        }
        return out

    @staticmethod
    def _infer_messages(step: Any) -> list[dict[str, Any]]:
        """journal 不带 messages 时按 thinking/tool_call 推导骨架（inferred）。"""
        msgs: list[dict[str, Any]] = []
        if step.context_before is not None:
            msgs.append({"role": "system", "content": step.context_before.objective})
        if step.thinking is not None:
            msgs.append(
                {
                    "role": "assistant",
                    "content": (step.thinking.raw_response_preview or step.thinking.decision),
                }
            )
        if step.tool_call is not None:
            msgs.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": step.tool_call.invocation_id,
                            "function": {
                                "name": step.tool_call.name,
                                "arguments": step.tool_call.arguments,
                            },
                        }
                    ],
                }
            )
        if step.tool_result is not None:
            msgs.append(
                {
                    "role": "tool",
                    "content": (step.tool_result.stdout_head or step.tool_result.delta_summary),
                }
            )
        return msgs


__all__ = ["StandardCursor"]
