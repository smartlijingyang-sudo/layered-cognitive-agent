"""E2E:复刻 ``LcaRunDriver.ts`` 的真实循环 — 派发 → summary → live → 终态收敛。

UI(LobeHub ``LcaRunDriver``,``deploy/lobehub/patches/runtime/LcaRunDriver.ts``
L706-770)的真实调用链:

    POST /runs                              ← 派发,响应里给 live_url
    loop:
      GET /runs/{run_id}/live               ← SSE,断开后用 Last-Event-ID 续传
      GET /runs/{run_id}                    ← summary,看 status 决定退出/重连
      if status ∈ {canceled, completed, failed} ∪ {waiting_input}: break
      sleep 400ms

本测试从纯 HTTP 视角验证三件事:

1. POST /runs 必须 200/202 且 body 含 run_id
2. GET /runs/{id} 必须 200 且 body 含合理 status
3. GET /runs/{id}/live 必须 200 + text/event-stream + 非空 body

不解析 SSE 帧、不依赖 LLM 凭证、不假定时序——只看 HTTP 合约。
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx
import pytest

# LobeHub ``LcaRunDriver`` L37-38:
TERMINAL_STATUSES = frozenset({"canceled", "completed", "failed"})
PAUSED_STATUSES = frozenset({"waiting_input"})

HOST = "127.0.0.1"
PORT = 18775
BASE = f"http://{HOST}:{PORT}"
LOGIN_BOOT_TIMEOUT_S = 90
LIVE_BUDGET_S = 4.0
RESUME_FIRST_BUDGET_S = 4.0
RESUME_SECOND_BUDGET_S = 5.0
SUMMARY_POLL_S = 0.4

# SSE 帧中 ``id: N\n`` 行前导——用于不解析完整 SSE 协议,只看 seq 单调性。
_SEQ_RE = b"id: "


def _live_seq_set(raw: bytes) -> list[int]:
    """轻量提取所有 ``id: N``;不做 SSE 块切分,不要求 event/data 完整。"""
    out: list[int] = []
    i = 0
    pat = _SEQ_RE
    while True:
        j = raw.find(pat, i)
        if j < 0:
            return out
        k = j + len(pat)
        end = k
        while end < len(raw) and raw[end] not in b"\n\r":
            end += 1
        with contextlib.suppress(ValueError):
            out.append(int(raw[k:end]))
        i = end


# ── 子进程 boot ──────────────────────────────────────────────────────


def _boot_kernel(tmp_path: Path) -> tuple[subprocess.Popen, Path]:
    """起一个 kernel 进程;失败时 ``log_path`` 留作 caller 的诊断输出。"""
    log_path = tmp_path / "kernel.log"
    log_fh = log_path.open("w")
    proc = subprocess.Popen(  # noqa: S603 — dev-only invocation 与 test_run_solo_smoke 对齐
        [  # noqa: S607
            "uv",
            "run",
            "python",
            "-m",
            "lca_kernel",
            "serve",
            "--profile",
            "profiles/web-standard.yaml",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--allow-unknown-env",
        ],
        cwd="/home/lichao/layered-cognitive-agent",
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    return proc, log_path


def _wait_ready(timeout_s: int = LOGIN_BOOT_TIMEOUT_S) -> bool:
    """轮询 ``/health``,直到 200 或超时。"""
    for _ in range(timeout_s):
        time.sleep(1)
        with contextlib.suppress(Exception):
            r = httpx.get(f"{BASE}/health", timeout=2.0)
            if r.status_code == 200:
                return True
    return False


def _stop_kernel(proc: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)


# ── 三个端点的客户端原语 ──────────────────────────────────────────────


def _post_runs(messages: list[dict[str, str]], model: str = "solo") -> str:
    resp = httpx.post(
        f"{BASE}/runs",
        json={"messages": messages, "model": model},
        timeout=10.0,
    )
    assert resp.status_code in (200, 202), f"POST /runs returned {resp.status_code}: {resp.text!r}"
    body = resp.json()
    run_id = body.get("run_id")
    assert isinstance(run_id, str) and run_id, f"POST /runs missing run_id: {body!r}"
    # ADR:响应体里的 live_url 必须是同一个 run_id(UI 直接拿来连 SSE)。
    assert body.get("live_url") == f"/runs/{run_id}/live", (
        f"live_url mismatch in POST /runs response: {body!r}"
    )
    return run_id


def _get_summary(run_id: str) -> dict[str, object]:
    resp = httpx.get(f"{BASE}/runs/{run_id}", timeout=5.0)
    assert resp.status_code == 200, f"summary returned {resp.status_code}: {resp.text!r}"
    return resp.json()


def _read_live_raw(
    run_id: str,
    *,
    after: int = 0,
    budget_s: float,
) -> bytes:
    """读 ``/runs/{id}/live`` 直到 ``budget_s`` 用尽;返回 raw bytes。

    只看 HTTP 合约:200 + text/event-stream + 非空 body。
    """
    deadline = time.monotonic() + budget_s
    collected = bytearray()
    with (
        httpx.Client(timeout=None) as client,  # noqa: S113 — SSE 需长读
        client.stream("GET", f"{BASE}/runs/{run_id}/live", params={"after": after}) as r,
    ):
        assert r.status_code == 200, f"live returned {r.status_code}: {r.read()!r}"
        ctype = r.headers.get("content-type", "")
        assert "text/event-stream" in ctype, f"live must be SSE, got content-type={ctype!r}"
        for chunk in r.iter_bytes():
            collected.extend(chunk)
            if time.monotonic() >= deadline:
                break
    return bytes(collected)


# ── 测试 ─────────────────────────────────────────────────────────────


def test_post_runs_returns_run_id_and_live_url(tmp_path: Path) -> None:
    """``POST /runs`` 必须 200/202 且 body 含 ``run_id`` + 匹配的 ``live_url``。"""
    proc, log_path = _boot_kernel(tmp_path)
    try:
        assert _wait_ready(), f"kernel never came up; see {log_path}"
        run_id = _post_runs([{"role": "user", "content": "ping"}])
        assert run_id.startswith("run_"), f"unexpected run_id shape: {run_id!r}"
    finally:
        _stop_kernel(proc)


def test_get_summary_returns_200_with_status_field(tmp_path: Path) -> None:
    """``GET /runs/{id}`` 必须 200 且 body 含 ``status`` 字段。"""
    proc, log_path = _boot_kernel(tmp_path)
    try:
        assert _wait_ready(), f"kernel never came up; see {log_path}"
        run_id = _post_runs([{"role": "user", "content": "ping"}])
        summary = _get_summary(run_id)
        assert summary.get("run_id") in (None, run_id), f"summary.run_id mismatch: {summary!r}"
        status = str(summary.get("status", ""))
        assert status in {
            "queued",
            "running",
            "working",
            *TERMINAL_STATUSES,
            *PAUSED_STATUSES,
        }, f"unexpected status: {status!r}"
    finally:
        _stop_kernel(proc)


def test_get_summary_unknown_run_returns_404(tmp_path: Path) -> None:
    """``GET /runs/{id}`` 不存在时必须 404,与 ``live`` 端的 404 行为一致。"""
    proc, log_path = _boot_kernel(tmp_path)
    try:
        assert _wait_ready(), f"kernel never came up; see {log_path}"
        resp = httpx.get(f"{BASE}/runs/this-run-does-not-exist", timeout=5.0)
        assert resp.status_code == 404
        assert resp.json() == {"error": "run not found"}
    finally:
        _stop_kernel(proc)


def test_live_returns_sse_with_frame_seq_ids(tmp_path: Path) -> None:
    """``GET /runs/{id}/live`` 必须 200 + text/event-stream + 非空 body,frame id 单调正整数。"""
    proc, log_path = _boot_kernel(tmp_path)
    try:
        assert _wait_ready(), f"kernel never came up; see {log_path}"
        run_id = _post_runs([{"role": "user", "content": "ping"}])

        raw = _read_live_raw(run_id, budget_s=LIVE_BUDGET_S)
        assert raw, f"live SSE produced empty body for run {run_id}; see {log_path}"
        # header 块 — SSE 帧都以 ``event: <ClassName>`` 命名(ADR-0163)。
        assert b"event: " in raw, f"no ``event:`` line in live body; head: {raw[:200]!r}"
        assert b"data: " in raw, f"no ``data:`` line in live body; head: {raw[:200]!r}"
        # frame id 单调正整数。
        seqs = _live_seq_set(raw)
        assert seqs, f"no ``id:`` line in live body; head: {raw[:200]!r}"
        assert seqs == sorted(seqs), f"frame ids must be monotonic, got {seqs!r}"
        assert all(s > 0 for s in seqs), f"frame ids must start > 0, got {seqs!r}"
        # 不应出现 OpenAI 风格 sentinel。
        assert b"[DONE]" not in raw, f"live SSE leaked [DONE] sentinel; head: {raw[:200]!r}"
    finally:
        _stop_kernel(proc)


def test_live_unknown_run_returns_404(tmp_path: Path) -> None:
    """``GET /runs/{id}/live`` 不存在时必须 404(契约与 summary 一致)。"""
    proc, log_path = _boot_kernel(tmp_path)
    try:
        assert _wait_ready(), f"kernel never came up; see {log_path}"
        resp = httpx.get(f"{BASE}/runs/this-run-does-not-exist/live", timeout=5.0)
        assert resp.status_code == 404
        assert resp.json() == {"error": "run not found"}
    finally:
        _stop_kernel(proc)


@pytest.mark.real_llm
def test_agent_actually_replies_via_live_sse(tmp_path: Path) -> None:
    """端到端:派发 → live SSE 必须产出 ``StepTextDelta`` 流且 run 落到 ``completed``。

    这是 LcaRunDriver 用户实际看到的事:UI 把 ``POST /runs`` 拿到的 ``run_id``
    喂给 ``GET /runs/{id}/live``,然后看到 ``text_delta`` 字符流进画面。
    本 case 验的就是这个真实链路,不是只验 200。

    凭证条件:pyproject.toml 把 ``real_llm`` marker 默认从 ``addopts`` 排除,
    需要 LLM_API_KEY 才跑;无 key 时 ``_has_llm_key`` 会跳过。
    """
    if not _has_llm_key():
        pytest.skip("LLM_API_KEY not set; install/load .env to run real_llm cases")

    proc, log_path = _boot_kernel(tmp_path)
    try:
        assert _wait_ready(), f"kernel never came up; see {log_path}"
        run_id = _post_runs([{"role": "user", "content": "用一句话回答:1+1=?"}])

        # 读 live 一段时间,期望看到 LLM 完成 + AgentRunFinished。
        raw = _read_live_raw(run_id, budget_s=LIVE_BUDGET_S)
        assert raw, f"live SSE empty for run {run_id}; see {log_path}"

        # 关键 event 名都应出现(LLM 真回了)。
        names = {
            line[len(b"event: ") :].decode("utf-8", errors="replace")
            for line in raw.splitlines()
            if line.startswith(b"event: ")
        }
        for expected in ("LlmCallStarted", "LlmCallCompleted", "StepTextDelta", "AgentRunFinished"):
            assert expected in names, (
                f"missing event {expected!r} from live SSE; got sorted: {sorted(names)!r}"
            )

        # 真实回答必须在 answer 频道出现:把 ``StepTextDelta`` 的 text_delta 拼起来。
        answer_chunks: list[str] = []
        for block in raw.decode("utf-8", errors="replace").split("\n\n"):
            event, data = _parse_sse_block(block)
            if event != "StepTextDelta":
                continue
            try:
                payload = json.loads(data) if data else {}
            except json.JSONDecodeError:  # non-JSON data 不是失败,只是这个 block 不算 text_delta
                continue
            inner = (payload.get("data") or {}) if isinstance(payload, dict) else {}
            if inner.get("channel") == "answer" and isinstance(inner.get("text_delta"), str):
                answer_chunks.append(inner["text_delta"])
        answer = "".join(answer_chunks).strip()
        assert answer, (
            f"no ``StepTextDelta.channel=answer`` text_delta produced; chunks={answer_chunks!r}"
        )

        # summary 必须是 terminal(LLM 跑过 = completed 或 failed,不再是 working)。
        summary = _get_summary(run_id)
        status = str(summary.get("status", ""))
        assert status in TERMINAL_STATUSES or status in PAUSED_STATUSES, (
            f"run {run_id} did not reach terminal/paused within {LIVE_BUDGET_S}s; "
            f"status={status!r}; answer={answer!r}"
        )
    finally:
        _stop_kernel(proc)


def _parse_sse_block(block: str) -> tuple[str, str]:
    """从一个 SSE block 抽出 ``(event, data)``。"""
    event = ""
    data = ""
    for line in block.splitlines():
        if line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("data: "):
            data = line[len("data: ") :]
    return event, data


def _has_llm_key() -> bool:
    """``lca-llm-resolver`` 从 ``.env`` 读 ``LLM_API_KEY``;没 key 跳过。

    优先看测试进程的环境,其次看项目 ``.env`` 里 ``LLM_API_KEY`` 行是否非空
    (kernel 子进程会通过 ``llm_resolver`` 加载这个文件)。
    """
    if os.environ.get("LLM_API_KEY") or os.environ.get("CCS_CODING_API_KEY"):
        return True
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == "LLM_API_KEY" and value.strip():
            return True
    return False


def test_resume_uses_query_after_param(tmp_path: Path) -> None:
    """``?after=N`` 服务端 resume:第二段连产出的所有 frame id 必须 ``> N``。

    ADR-0163 / ``query_endpoints._parse_after``:server 仅从 query string
    解析 ``?after=``,``Last-Event-ID`` header 被忽略(UI 端真 resume 靠
    客户端 dedup——见 ``gatewayEventHandler.ts`` 的
    ``lastTextSnapshotSeq`` 操作单调累加)。
    """
    proc, log_path = _boot_kernel(tmp_path)
    try:
        assert _wait_ready(), f"kernel never came up; see {log_path}"
        run_id = _post_runs([{"role": "user", "content": "ping"}])

        # 第一段:从 0 开始读 ~4 秒。
        first_raw = _read_live_raw(run_id, budget_s=RESUME_FIRST_BUDGET_S)
        first_seqs = _live_seq_set(first_raw)
        assert first_seqs, f"first live read produced 0 frames; head: {first_raw[:200]!r}"
        max_first = max(first_seqs)

        # 第二段:用 ``?after=`` 续传——服务端 resume 的真正入口。
        second_raw = _read_live_raw(run_id, after=max_first, budget_s=RESUME_SECOND_BUDGET_S)
        # 不要求第二段一定有 bytes(短窗口、run 已 terminal、replay gap 都允许);
        # 只在拿到 seq 时验证都 ``> max_first``。
        second_seqs = _live_seq_set(second_raw)
        if second_seqs:
            assert all(s > max_first for s in second_seqs), (
                f"?after={max_first} resume must skip earlier seqs; got {second_seqs!r}"
            )
    finally:
        _stop_kernel(proc)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q", "--no-cov"]))
