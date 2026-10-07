"""RA-024: forward-ref 自愈在源头模块；payloads 模块可独立测试。

testability gap 的钉子：fresh interpreter 里只 import
``lca_kernel.events.payloads.model_visible``（不 import 任何消费者），
直接实例化两个 payload 类必须成功。此前只能靠 hook.py / fold_source.py
的 import-time rebuild 副作用 + publisher.py 的 eager import 触发。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

_PROBE = """
from lca_kernel.events.payloads.model_visible import (
    SpineLlmRequestHeaderAssistantPayload,
    SpineLlmRequestHeaderPayload,
)

header = SpineLlmRequestHeaderPayload(
    step_id="step-001",
    incarnation=1,
    config={},
    system="s",
    tools=(),
    messages=(),
    manifest=None,
    reason="initial",
    previous_header_digest=None,
)
assistant = SpineLlmRequestHeaderAssistantPayload(
    step_id="step-001",
    incarnation=1,
    assistant_content="hello",
    tool_calls=(),
    finish_reason="stop",
    usage={"prompt_tokens": 1},
    header_digest="sha256:abc",
)
print("OK", header.step_id, assistant.finish_reason)
"""


def _fresh_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("LLM_API_KEY", "dummy")
    return env


def test_payloads_standalone_in_fresh_interpreter() -> None:
    """Fresh interpreter：只 import payloads 模块即可实例化两类。"""
    proc = subprocess.run(  # noqa: S603 - fixed sys.executable + static probe source
        [sys.executable, "-c", _PROBE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=_fresh_env(),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().startswith("OK")


def test_self_heal_is_idempotent() -> None:
    """模块内自愈可重复跑（消费者不再各自 rebuild 的前提）。"""
    from lca_kernel.events.payloads.model_visible import (
        _self_heal_forward_refs,
    )

    _self_heal_forward_refs()
    _self_heal_forward_refs()
