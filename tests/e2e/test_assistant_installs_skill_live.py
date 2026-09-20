"""ADR-0247 流程测试补强：创建后的 agent 自主安装 skill 到自己的 skills/ 目录。

场景：新建助理 → 用户只给方向（安装一个技能，给出网络来源）→ agent 调用
``create_assistant_skill(source_url=...)`` → skill 经 0067 三闸验证后落盘到
``{home}/skills/<skill_id>/`` → 可被 ``activate``。

标记 ``real_llm``：需要 LLM_API_KEY 且 kernel 运行在 127.0.0.1:8765，
默认从 pytest 排除（pyproject ``addopts = -m 'not real_llm'``）。
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

import pytest

pytestmark = pytest.mark.real_llm

_BASE = os.environ.get("LCA_OPS_BASE_URL", "http://127.0.0.1:8765")
_SKILL_URL = os.environ.get(
    "LCA_TEST_SKILL_URL",
    "https://raw.githubusercontent.com/anthropics/skills/main/skills/docx/SKILL.md",
)


def _kernel_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{_BASE}/health", timeout=3) as resp:  # noqa: S310
            return resp.status == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _has_llm_key() -> bool:
    return bool(os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _create_assistant() -> dict[str, str]:
    body = json.dumps(
        {"name": "技能安装测试员", "description": "验证 agent 自主安装 skill 到 Home"}
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        f"{_BASE}/v1/assistants",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=body,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _create_run(assistant_id: str, user_text: str) -> str:
    body = json.dumps(
        {
            "profile": "web-assistant",
            "assistant_id": assistant_id,
            "mode": "solo",
            "messages": [{"role": "user", "content": user_text}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        f"{_BASE}/runs",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=body,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        return str(json.loads(resp.read().decode("utf-8")).get("run_id", ""))


def _wait_for_skill(home_path: str, skill_id: str, timeout_s: int = 180) -> str | None:
    """轮询 Home manifest，直到 skill 以 verified 状态出现。"""
    manifest_path = os.path.join(home_path, "manifest.json")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            skills = manifest.get("skills", {})
            entry = skills.get(skill_id)
            if isinstance(entry, dict) and entry.get("artifact_state") == "verified":
                return str(entry.get("artifact_state"))
        except (OSError, ValueError):
            pass
        time.sleep(5)
    return None


def test_agent_installs_skill_into_own_home() -> None:
    if not _has_llm_key():
        pytest.skip("LLM_API_KEY not set; install/load .env to run real_llm cases")
    if not _kernel_ready():
        pytest.skip(f"LCA kernel not reachable at {_BASE}")

    assistant = _create_assistant()
    assistant_id = assistant["assistant_id"]
    home_path = assistant["home_path"]
    assert assistant_id and home_path

    user_text = (
        "给自己安装一个技能。来源是 "
        f"{_SKILL_URL} 。"
        "用 create_assistant_skill 安装到你的技能目录，安装完报告 skill_id。"
    )
    run_id = _create_run(assistant_id, user_text)
    assert run_id, "run creation returned no run_id"

    # 等待 agent 自主完成安装（LLM 决定调用工具 + 0067 三闸）。
    state = _wait_for_skill(home_path, "docx")
    assert state == "verified", (
        f"skill docx not installed/verified in {home_path} within timeout; run={run_id}"
    )
