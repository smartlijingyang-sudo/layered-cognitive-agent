"""Regression: an internal non-streaming call must not overwrite the user answer.

``run_28aa7eb3261b`` 的 step-010 先跑用户可见的流式调用，紧接着跑
``memory_extract`` 的非流式调用。fold 对每一步只保留最后一个
``llm.call.end``，于是 25.4 秒的用户回答被 4.4 秒的提取调用覆盖，
journal 里最后一步的 reasoning / response / latency 全变成空的。
EventTranslator 已经丢弃 ``stream=False`` 的调用，fold 必须同样忽略。
"""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def _spine(seq: int, ep: str, payload: dict) -> dict:
    return {
        "event_id": f"run_t:{seq}",
        "category": f"spine.{ep}",
        "channel": "fact",
        "execution_point": ep,
        "payload": payload,
        "ts": f"2026-10-01T08:22:{seq:02d}.000000+00:00",
    }


def test_non_streaming_call_does_not_clobber_user_answer() -> None:
    events = [
        _spine(
            0,
            "llm.request.header",
            {
                "step_id": "step-010",
                "model": "qwen3.7-plus",
                "reason": "initial",
                "system": "sys",
                "messages": [],
                "tools": [],
            },
        ),
        _spine(1, "llm.call.start", {"model": "qwen3.7-plus", "stream": True}),
        _spine(
            2,
            "llm.stream.token",
            {"channel_kind": "reasoning", "text_delta": "用户回答的推理过程"},
        ),
        _spine(
            3,
            "llm.stream.token",
            {"channel_kind": "output", "text_delta": "这是用户看到的最终回答"},
        ),
        _spine(
            4,
            "llm.call.end",
            {
                "model": "qwen3.7-plus",
                "stream": True,
                "latency_ms": 25407,
                "prompt_tokens": 13241,
                "completion_tokens": 1410,
                "outcome": "success",
            },
        ),
        # memory_extract 的非流式调用：没有 token，结束时会清空缓冲
        _spine(
            5,
            "llm.call.start",
            {"model": "qwen3.7-plus", "stream": False, "prompt_preview": "ROLE: memory_extract"},
        ),
        _spine(
            6,
            "llm.call.end",
            {
                "model": "qwen3.7-plus",
                "stream": False,
                "latency_ms": 4418,
                "prompt_tokens": 422,
                "completion_tokens": 190,
                "outcome": "success",
            },
        ),
        _spine(7, "kernel.run.stop", {"outcome": "success", "run_id": "run_t"}),
    ]

    doc = fold_step_tree(events, run_id="run_t")
    assert len(doc.steps) == 1
    step = doc.steps[0]
    thinking = step.thinking
    assert thinking is not None
    # 保留用户可见那次调用的指标与正文，而不是提取调用的
    assert thinking.latency_ms == 25407
    assert thinking.prompt_tokens == 13241
    assert thinking.completion_tokens == 1410
    assert thinking.reasoning == "用户回答的推理过程"
    assert thinking.raw_response_preview == "这是用户看到的最终回答"