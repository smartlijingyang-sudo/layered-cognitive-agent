"""ADR-0247 流程测试全景验证：助理演化闭环端到端 Live 测试。

场景：
1. Turn 0: 新建演化助理，校验初始 Home 目录布局（SOUL/USER/AGENTS/goals.yaml/skills/memory）
2. Turn 1: 助理自我感知 —— 询问助理自我身份、职责定位与服务对象
3. Turn 2: 对话更新画像 —— 告知用户身份与偏好，验证 AssistantMemory 捕获并经 ProfileBackfill 自动回填 USER.md
4. Turn 3: 跨轮记忆感知 —— 再次提问，验证模型跨 run 感知并复述回填后的用户偏好
5. Turn 4: 自主创建技能 —— 引导模型调用 create_assistant_skill 安装 code-review-helper 并经 0067 三闸落盘 verified
6. Turn 5: 激活使用技能 —— 引导模型使用新技能审查未关闭句柄的代码，验证 activate_skill 调用与 SOP 审查输出

标记 real_llm：需要 LLM_API_KEY 且 kernel 运行在 127.0.0.1:8765。
默认从常规 pytest 中排除（pyproject addopts = -m 'not real_llm'）。
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.real_llm

_BASE = os.environ.get("LCA_OPS_BASE_URL", "http://10.36.6.252:8765")


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
        {
            "name": "全流程演化测试助理",
            "description": "用于验证自感知、记忆知识层与自主技能创建调用的端到端助理",
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        f"{_BASE}/v1/assistants",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=body,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _retire_assistant(assistant_id: str) -> None:
    with contextlib.suppress(Exception):
        req = urllib.request.Request(  # noqa: S310
            f"{_BASE}/v1/assistants/{assistant_id}/retire",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=5):  # noqa: S310
            pass


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


def _wait_for_run(run_id: str, timeout_s: int = 180) -> str:
    """轮询等待 run 结束（通过检查 traces/runs/{run_id}/journal.json 或 GET /runs/{run_id}）。"""
    journal_path = Path("traces") / "runs" / run_id / "journal.json"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if journal_path.is_file():
            try:
                data = json.loads(journal_path.read_text(encoding="utf-8"))
                if data.get("closed_at") or data.get("totals"):
                    return "completed"
            except (OSError, ValueError):
                pass
        with contextlib.suppress(Exception):
            req = urllib.request.Request(f"{_BASE}/runs/{run_id}")  # noqa: S310
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                summary = json.loads(resp.read().decode("utf-8"))
                status = summary.get("status")
                if status in ("completed", "failed", "error", "cancelled"):
                    return str(status)
        time.sleep(3)
    raise TimeoutError(f"Run {run_id} did not finish within {timeout_s}s")


def _get_run_output_text(run_id: str) -> str:
    """从 run 的 spine.jsonl 重建模型输出的文本内容。"""
    spine_path = Path("traces") / "runs" / run_id / f"{run_id}.spine.jsonl"
    if not spine_path.is_file():
        return ""
    deltas: list[str] = []
    with open(spine_path, encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
                if ev.get("execution_point") == "llm.stream.token":
                    payload = ev.get("payload") or {}
                    if payload.get("channel_kind") == "output":
                        deltas.append(payload.get("text_delta", ""))
            except (OSError, ValueError):
                continue
    return "".join(deltas)


def _get_run_tool_calls(run_id: str) -> list[str]:
    """从 spine.jsonl 收集该 run 中发生的所有工具调用名称。"""
    spine_path = Path("traces") / "runs" / run_id / f"{run_id}.spine.jsonl"
    if not spine_path.is_file():
        return []
    tool_names: list[str] = []
    with open(spine_path, encoding="utf-8") as f:
        for line in f:
            if "activate_skill" in line:
                tool_names.append("activate_skill")
            if "create_assistant_skill" in line:
                tool_names.append("create_assistant_skill")
    return tool_names


def _wait_for_user_md_keyword(home_path: str, keyword: str, timeout_s: int = 60) -> bool:
    """轮询 Home 的 USER.md 文件，直到出现特定关键字。"""
    user_md_path = os.path.join(home_path, "USER.md")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if os.path.isfile(user_md_path):
                text = Path(user_md_path).read_text(encoding="utf-8")
                if keyword in text:
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(2)
    return False


def _wait_for_skill_verified(home_path: str, skill_id: str, timeout_s: int = 180) -> str | None:
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
        time.sleep(3)
    return None


def test_assistant_evolution_flow_live() -> None:
    if not _has_llm_key():
        pytest.skip("LLM_API_KEY not set; install/load .env to run real_llm cases")
    if not _kernel_ready():
        pytest.skip(f"LCA kernel not reachable at {_BASE}")

    # ── Turn 0: 创建助理并初始化 Home 结构 ─────────────────────────────────
    assistant = _create_assistant()
    assistant_id = assistant["assistant_id"]
    home_path = assistant["home_path"]
    assert assistant_id and home_path, "创建助理未返回有效 assistant_id 或 home_path"

    try:
        # 断言必要配置面已齐全
        assert os.path.isfile(os.path.join(home_path, "SOUL.md")), "Home 缺失 SOUL.md"
        assert os.path.isfile(os.path.join(home_path, "USER.md")), "Home 缺失 USER.md"
        assert os.path.isfile(os.path.join(home_path, "AGENTS.md")), "Home 缺失 AGENTS.md"
        assert os.path.isfile(os.path.join(home_path, "goals.yaml")), "Home 缺失 goals.yaml"
        assert os.path.isdir(os.path.join(home_path, "skills")), "Home 缺失 skills/ 目录"
        assert os.path.isdir(os.path.join(home_path, "memory")), "Home 缺失 memory/ 目录"

        # ── Turn 1: 助理自我感知验证 ──────────────────────────────────────────
        user_prompt_t1 = (
            "请简要介绍你自己：你是谁？你的定位和职责是什么？你目前知道关于用户的什么信息？"
            "你有哪些可用工具或技能？"
        )
        run_1 = _create_run(assistant_id, user_prompt_t1)
        assert run_1, "Turn 1 创建 run 失败"
        _wait_for_run(run_1)
        out_1 = _get_run_output_text(run_1)
        assert len(out_1.strip()) > 0, f"Turn 1 模型未输出任何内容; run={run_1}"

        # ── Turn 2: 对话修改用户画像并触发 USER.md 自动回填 ──────────────────────
        user_prompt_t2 = (
            "我是系统架构师李超，主要技术栈是 Python 和 Rust。请记住我的身份和偏好："
            "后续所有方案回复都要简洁扼要、优先给出代码示例与架构图，不要客套话。"
        )
        run_2 = _create_run(assistant_id, user_prompt_t2)
        assert run_2, "Turn 2 创建 run 失败"
        _wait_for_run(run_2)

        # 验证 USER.md 被 ProfileBackfill 自动回填
        backfilled = _wait_for_user_md_keyword(home_path, "李超", timeout_s=60)
        assert backfilled, f"USER.md 未在超时内回填用户画像; run={run_2}"
        user_md_text = Path(home_path, "USER.md").read_text(encoding="utf-8")
        assert "李超" in user_md_text
        assert "架构师" in user_md_text or "Python" in user_md_text

        # ── Turn 3: 跨轮记忆感知验证 ──────────────────────────────────────────
        user_prompt_t3 = "你还记得我是谁吗？我的主要技术栈和回答偏好是什么？"
        run_3 = _create_run(assistant_id, user_prompt_t3)
        assert run_3, "Turn 3 创建 run 失败"
        _wait_for_run(run_3)
        out_3 = _get_run_output_text(run_3)
        assert "李超" in out_3 or "架构师" in out_3, f"模型未能感知到用户身份: {out_3}; run={run_3}"

        # ── Turn 4: 助理自主创建并安装 Skill ───────────────────────────────────
        user_prompt_t4 = (
            "请为自己创建一个名为 code-review-helper 的技能，严格遵循 SKILL.md 规范"
            "（frontmatter 必须包含 name 为 code-review-helper，description 说明这是代码审查规范）。"
            "技能正文定义代码审查五步 SOP：1. 检查契约与不变量；2. 检查边界条件与异常；"
            "3. 检查资源释放（强调必须使用 with 语句管理 open 文件句柄，防止句柄泄漏）；"
            "4. 检查日志；5. 给出重构代码。\n"
            "请直接调用 create_assistant_skill 工具（参数填入 skill_md）将其安装到你的技能目录。"
        )
        run_4 = _create_run(assistant_id, user_prompt_t4)
        assert run_4, "Turn 4 创建 run 失败"
        _wait_for_run(run_4)

        # 等待 skill 经 0067 三闸验证落盘并标记为 verified
        skill_state = _wait_for_skill_verified(home_path, "code-review-helper", timeout_s=180)
        assert skill_state == "verified", (
            f"skill code-review-helper 未能在 Home 中验证落盘; run={run_4}"
        )

        # ── Turn 5: 激活并使用新 Skill 审查代码 ───────────────────────────────
        user_prompt_t5 = (
            "请使用刚刚安装的 code-review-helper 技能（调用 activate_skill 激活），"
            "审查以下这段 Python 代码：\n"
            "```python\n"
            "def read_data(filepath):\n"
            "    f = open(filepath)\n"
            "    return f.read()\n"
            "```"
        )
        run_5 = _create_run(assistant_id, user_prompt_t5)
        assert run_5, "Turn 5 创建 run 失败"
        _wait_for_run(run_5)
        out_5 = _get_run_output_text(run_5)
        tool_calls_5 = _get_run_tool_calls(run_5)

        # 验证模型调用了 activate_skill，且输出内容指出了文件句柄泄漏问题
        assert "activate_skill" in tool_calls_5 or any(
            kw in out_5 for kw in ("with", "open", "泄露", "关闭", "句柄", "资源")
        ), f"模型未激活新技能或未能按照 SOP 指出文件句柄泄露风险: {out_5}; run={run_5}"

    finally:
        _retire_assistant(assistant_id)
