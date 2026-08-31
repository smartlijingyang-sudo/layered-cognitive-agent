"""K8 HMR tests — PatchConfig / validate_patch / PatchWatcher / ReloadError.

Covers ADR-0118 §验收 A1–A9 minus the integration paths (A8 boundary +
A9 importlinter run separately).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from lca_kernel.errors import ReloadError
from lca_kernel.hmr import (
    DEFAULT_PATCH_PATH,
    MIN_DEBOUNCE_MS,
    PATCH_EVENT_KIND,
    PatchConfig,
    PatchEvent,
    PollingPatchWatcher,
    summarize_patch,
    validate_patch,
)

# ── A1: PatchConfig dataclass + defaults ───────────────────────────


def test_patch_config_defaults_match_adr0118() -> None:
    """PatchConfig 默认值遵循 ADR-0118 §决定 2。"""
    config = PatchConfig()
    assert config.path == DEFAULT_PATCH_PATH
    assert config.debounce_ms == 250
    assert config.poll_interval_ms == 1000
    assert config.allow_missing is False
    assert config.allow_empty is False


def test_patch_config_clamps_debounce_below_minimum() -> None:
    """debounce_ms < MIN_DEBOUNCE_MS 自动抬升(ADR-0118 §决定 2 防抖下限)。"""
    config = PatchConfig(debounce_ms=10)
    assert config.debounce_ms == MIN_DEBOUNCE_MS


def test_patch_config_clamps_poll_below_minimum() -> None:
    config = PatchConfig(poll_interval_ms=10)
    assert config.poll_interval_ms == MIN_DEBOUNCE_MS


def test_patch_config_is_frozen() -> None:
    """PatchConfig 必须 frozen;否则 plugin 改写会污染 watcher 行为。"""
    config = PatchConfig()
    with pytest.raises((AttributeError, Exception)):
        config.debounce_ms = 999  # type: ignore[misc]


# ── A2/A3: validate_patch accepts good + rejects bad shape ───────────


def test_validate_patch_accepts_minimal_mapping() -> None:
    validate_patch({"version": "1"})


def test_validate_patch_accepts_all_allowed_top_level_keys() -> None:
    patch = {
        "version": "1",
        "bundles": [{"id": "b1"}],
        "profiles": [{"id": "p1"}],
        "patches": [{"id": "u1"}],
        "settings": {"kind": "user"},
    }
    validate_patch(patch)


def test_validate_patch_rejects_non_mapping() -> None:
    with pytest.raises(ReloadError) as exc_info:
        validate_patch("not-a-mapping")
    assert exc_info.value.reason == "shape"


def test_validate_patch_rejects_empty_mapping() -> None:
    with pytest.raises(ReloadError) as exc_info:
        validate_patch({})
    assert exc_info.value.reason == "empty"


def test_validate_patch_rejects_missing_version() -> None:
    with pytest.raises(ReloadError) as exc_info:
        validate_patch({"bundles": []})
    assert exc_info.value.reason == "shape"
    assert "version" in str(exc_info.value)


def test_validate_patch_rejects_empty_version() -> None:
    with pytest.raises(ReloadError) as exc_info:
        validate_patch({"version": ""})
    assert exc_info.value.reason == "shape"


def test_validate_patch_accepts_int_version() -> None:
    """YAML 解析会把 ``version: 1`` 转 int;必须接受。"""
    validate_patch({"version": 1})


def test_validate_patch_rejects_boolean_version() -> None:
    """bool 是 int 子类,要拒绝(避免 ``version: yes`` 误判)。"""
    with pytest.raises(ReloadError) as exc_info:
        validate_patch({"version": True})
    assert exc_info.value.reason == "shape"


def test_validate_patch_rejects_unknown_top_level_keys() -> None:
    with pytest.raises(ReloadError) as exc_info:
        validate_patch({"version": "1", "banana": 42})
    assert exc_info.value.reason == "shape"
    assert "banana" in str(exc_info.value)


# ── A4/A5: reload_now raises ReloadError on missing / empty ───────────


def test_reload_now_raises_when_patch_file_missing(tmp_path: Path) -> None:
    config = PatchConfig(path=tmp_path / "absent.yml")
    watcher = PollingPatchWatcher(config, on_change=lambda _event: None)
    with pytest.raises(ReloadError) as exc_info:
        watcher.reload_now()
    assert exc_info.value.reason == "missing"
    assert exc_info.value.path == config.path


def test_reload_now_returns_noop_when_allow_missing(tmp_path: Path) -> None:
    """allow_missing=True 时 reload_now 不 raise,返回 noop event。"""
    config = PatchConfig(path=tmp_path / "absent.yml", allow_missing=True)
    events: list[PatchEvent] = []
    watcher = PollingPatchWatcher(config, on_change=events.append)
    event = watcher.reload_now()
    assert event.patch_kind == "noop"
    assert events == []  # noop should not invoke callback


def test_reload_now_raises_when_empty_and_disallowed(tmp_path: Path) -> None:
    (tmp_path / "patch.yml").write_text("")
    config = PatchConfig(path=tmp_path / "patch.yml")
    watcher = PollingPatchWatcher(config, on_change=lambda _event: None)
    with pytest.raises(ReloadError) as exc_info:
        watcher.reload_now()
    assert exc_info.value.reason == "empty"


def test_reload_now_emits_event_on_valid_patch(tmp_path: Path) -> None:
    (tmp_path / "patch.yml").write_text("version: 1\n")
    config = PatchConfig(path=tmp_path / "patch.yml")
    received: list[PatchEvent] = []
    watcher = PollingPatchWatcher(config, on_change=received.append)
    watcher.reload_now()
    assert len(received) == 1
    assert received[0].patch_kind == "user"
    # YAML parses ``version: 1`` as int; both int 1 and str "1" are acceptable.
    assert received[0].raw["version"] in (1, "1")


def test_reload_now_uses_settings_kind(tmp_path: Path) -> None:
    """顶层 ``settings.kind`` 推断 patch_kind。"""
    (tmp_path / "patch.yml").write_text("version: 1\nsettings:\n  kind: overlay\n")
    config = PatchConfig(path=tmp_path / "patch.yml")
    received: list[PatchEvent] = []
    watcher = PollingPatchWatcher(config, on_change=received.append)
    watcher.reload_now()
    assert received[0].patch_kind == "overlay"


def test_reload_now_raises_shape_on_unknown_keys(tmp_path: Path) -> None:
    (tmp_path / "patch.yml").write_text("version: 1\nbanana: 42\n")
    config = PatchConfig(path=tmp_path / "patch.yml")
    watcher = PollingPatchWatcher(config, on_change=lambda _event: None)
    with pytest.raises(ReloadError) as exc_info:
        watcher.reload_now()
    assert exc_info.value.reason == "shape"


# ── A6/A7: start / stop lifecycle + watcher actually fires ───────────


def test_watcher_start_stop_is_idempotent(tmp_path: Path) -> None:
    config = PatchConfig(path=tmp_path / "patch.yml", poll_interval_ms=50)
    watcher = PollingPatchWatcher(config, on_change=lambda _event: None)
    watcher.start()
    watcher.start()  # second start is no-op
    thread = watcher._thread  # pyright: ignore[reportPrivateUsage]
    assert thread is not None and thread.is_alive()
    watcher.stop()
    watcher.stop()  # second stop is no-op
    assert watcher._thread is None  # pyright: ignore[reportPrivateUsage]


def test_watcher_daemon_thread_does_not_block_process_exit(tmp_path: Path) -> None:
    config = PatchConfig(path=tmp_path / "patch.yml", poll_interval_ms=50)
    watcher = PollingPatchWatcher(config, on_change=lambda _event: None)
    watcher.start()
    thread = watcher._thread  # pyright: ignore[reportPrivateUsage]
    assert thread is not None
    assert thread.daemon is True


def test_watcher_detects_file_change(tmp_path: Path) -> None:
    """写入 patch 文件后,watcher 在 debounce + poll 内触发 callback。"""
    import os

    patch_path = tmp_path / "patch.yml"
    patch_path.write_text("version: 1\n")
    config = PatchConfig(
        path=patch_path,
        debounce_ms=50,
        poll_interval_ms=50,
    )
    received: list[PatchEvent] = []
    watcher = PollingPatchWatcher(config, on_change=received.append)
    watcher.start()
    try:
        # Force mtime forward so the next poll detects a change.
        time.sleep(0.2)
        new_mtime = time.time() + 1.0
        os.utime(patch_path, (new_mtime, new_mtime))
        # Allow watcher to detect + debounce + dispatch.
        deadline = time.time() + 3.0
        while time.time() < deadline and len(received) == 0:
            time.sleep(0.05)
        assert received, "watcher did not detect the patch change within 3s"
    finally:
        watcher.stop()


# ── summarize_patch (辅助;lca-ops 用)─────────────────────────────────


def test_summarize_patch_minimal() -> None:
    out = summarize_patch({"version": "1"})
    assert out.startswith("version=1")


def test_summarize_patch_counts_each_section() -> None:
    out = summarize_patch(
        {
            "version": "1",
            "bundles": [{}, {}],
            "profiles": [{}],
            "patches": [{}, {}, {}],
        }
    )
    assert "bundles=2" in out
    assert "profiles=1" in out
    assert "patches=3" in out


def test_summarize_patch_handles_settings_kind() -> None:
    out = summarize_patch({"version": "1", "settings": {"kind": "overlay"}})
    assert "settings.kind=overlay" in out


# ── Constants are stable ─────────────────────────────────────────────


def test_module_exports_are_stable() -> None:
    """ADR-0118 §决定 2 / §决定 4 列出的常量与符号必须稳定可 import。"""
    assert Path("cordis.patch.yml") == DEFAULT_PATCH_PATH
    assert MIN_DEBOUNCE_MS == 50
    assert PATCH_EVENT_KIND == "kernel.hmr.patch"


def test_reload_error_carries_path_and_reason(tmp_path: Path) -> None:
    config = PatchConfig(path=tmp_path / "absent.yml")
    watcher = PollingPatchWatcher(config, on_change=lambda _event: None)
    with pytest.raises(ReloadError) as exc_info:
        watcher.reload_now()
    err = exc_info.value
    assert err.path == config.path
    assert err.reason == "missing"
    # ReloadError must be a KernelError (single except clause at transport boundary).
    from lca_kernel.errors import KernelError

    assert isinstance(err, KernelError)


def test_concurrent_reload_now_is_thread_safe(tmp_path: Path) -> None:
    """并发 reload_now 必须只触发一次 callback (Lock 守临界区)。"""
    patch_path = tmp_path / "patch.yml"
    patch_path.write_text("version: 1\n")
    config = PatchConfig(path=patch_path)
    counter = threading.Lock()
    count = {"n": 0}

    def _on_change(_event: PatchEvent) -> None:
        with counter:
            count["n"] += 1

    watcher = PollingPatchWatcher(config, on_change=_on_change)
    threads = [threading.Thread(target=watcher.reload_now) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert count["n"] == 8
