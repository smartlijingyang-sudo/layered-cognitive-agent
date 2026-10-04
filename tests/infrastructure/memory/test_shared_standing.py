"""Three-tier standing architecture: platform / protected / projection.

- Tier 1 (platform): always injected whole, outside any budget, zero truncation.
- Tier 2 (protected): assembled by markdown section (whole in / whole dropped,
  never cut mid-section) within its own budget; drops log a warning.
- Tier 3 (projection): assembled by section within the remaining budget.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import (
    layout_for_home,
    packaged_layout,
    read_layout,
)
from lca.infrastructure.memory.contextfiles.domain.standing import (
    StandingTruncationError,
    assemble_standing,
    pack_sections,
    render_injected,
    split_sections,
)
from lca.infrastructure.memory.contextfiles.service.assembly import (
    read_platform_documents,
    read_standing_documents,
    refresh_standing_backstory,
)
from lca.infrastructure.memory.contextfiles.service.compaction import (
    preserve_standing_sections,
)
from lca.plugins.assistant.persona.persona import persona_from_home

_REPO = Path(__file__).resolve().parents[3]


def _write(root: Path, name: str, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    target.write_text(text, encoding="utf-8")
    return target


# ------------------------------------------------------------------ layout
def test_packaged_layout_declares_three_tiers() -> None:
    layout = packaged_layout()
    assert layout.platform_files == ("PLATFORM.md",)
    assert "{name}" in layout.platform_heading
    assert layout.protected_files == (
        "CONSTITUTION.md",
        "SOUL.md",
        "IDENTITY.md",
        "USER.md",
    )
    assert layout.protected_budget_chars == 32000
    assert layout.backstory_budget_chars == 36000
    assert set(layout.protected_files) <= set(layout.standing_files)
    assert not set(layout.platform_files) & set(layout.standing_files)


def test_home_override_keeps_tiers_when_absent(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _write(home / "memory", "contextfiles.toml", 'people_dir = "notes/people"\n')
    layout = layout_for_home(str(home))
    assert layout.platform_files == ("PLATFORM.md",)
    assert layout.protected_files == packaged_layout().protected_files
    assert layout.protected_budget_chars == 32000
    assert layout.people_dir == "notes/people"


def test_home_override_can_opt_out_of_platform(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _write(home / "memory", "contextfiles.toml", "platform_files = []\n")
    assert layout_for_home(str(home)).platform_files == ()


def test_broken_override_keeps_packaged_tiers(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _write(home / "memory", "contextfiles.toml", "platform_files = [unclosed\n")
    layout = layout_for_home(str(home))
    assert layout.platform_files == ("PLATFORM.md",)
    assert layout.protected_budget_chars == 32000


def test_read_layout_rejects_platform_overlap() -> None:
    text = (_REPO / "lca" / "infrastructure" / "memory" / "contextfiles" / "layout.toml").read_text(
        encoding="utf-8"
    )
    broken = text.replace('platform_files = ["PLATFORM.md"]', 'platform_files = ["SOUL.md"]')
    with pytest.raises(ValueError):
        read_layout(broken)


def test_read_layout_rejects_protected_outside_standing() -> None:
    text = (_REPO / "lca" / "infrastructure" / "memory" / "contextfiles" / "layout.toml").read_text(
        encoding="utf-8"
    )
    broken = text.replace('"CONSTITUTION.md", "SOUL.md"', '"CONSTITUTION.md", "NOPE.md"')
    with pytest.raises(ValueError):
        read_layout(broken)


def test_read_layout_rejects_protected_budget_above_total() -> None:
    text = (_REPO / "lca" / "infrastructure" / "memory" / "contextfiles" / "layout.toml").read_text(
        encoding="utf-8"
    )
    broken = text.replace("protected_budget_chars = 32000", "protected_budget_chars = 99999")
    with pytest.raises(ValueError):
        read_layout(broken)


# ------------------------------------------------------------------ sections
def test_split_sections_preamble_and_headings() -> None:
    body = "# Title\nintro\n\n## A\na1\na2\n\n### B\nb1\n"
    sections = split_sections(body)
    assert [h for h, _ in sections] == [None, "## A", "### B"]
    assert sections[0][1] == "# Title\nintro"
    assert sections[1][1] == "## A\na1\na2"
    assert sections[2][1] == "### B\nb1"


def test_split_sections_flat_file_is_one_section() -> None:
    assert split_sections("just text\nmore") == [(None, "just text\nmore")]
    assert split_sections("   \n") == []


# ------------------------------------------------- tier 1: platform
def test_platform_files_ignore_budget_entirely(tmp_path: Path) -> None:
    # 5000 chars of platform rules exceed every budget; they still land whole.
    platform_root = tmp_path / "lca_home"
    big_rules = "规则" * 2500
    _write(platform_root, "PLATFORM.md", big_rules)
    home = tmp_path / "asst"
    home.mkdir()

    out = refresh_standing_backstory(str(home), fallback="old", platform_root=platform_root)
    assert big_rules in out


def test_platform_comes_before_everything(tmp_path: Path) -> None:
    platform_root = tmp_path / "lca_home"
    _write(platform_root, "PLATFORM.md", "平台铁律")
    home = tmp_path / "asst"
    _write(home, "CONSTITUTION.md", "## 身份\n宪法正文")
    _write(home, "MEMORY.md", "## 记忆\n投影正文")

    out = refresh_standing_backstory(str(home), fallback="old", platform_root=platform_root)
    assert out.index("平台铁律") < out.index("宪法正文") < out.index("投影正文")


def test_missing_platform_file_keeps_old_behavior(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _write(home, "SOUL.md", "私人人设")
    layout = packaged_layout()
    docs = read_standing_documents(str(home), layout, platform_root=tmp_path / "nope")
    assert [name for name, _ in docs] == list(layout.standing_files)
    assert (
        refresh_standing_backstory(
            str(tmp_path / "nohome"), fallback="old", platform_root=tmp_path / "nope"
        )
        == "old"
    )


def test_read_platform_documents_stamps_heading(tmp_path: Path) -> None:
    platform_root = tmp_path / "lca_home"
    _write(platform_root, "PLATFORM.md", "平台铁律")
    docs = read_platform_documents(packaged_layout(), platform_root)
    assert docs[0][0] == "PLATFORM.md"
    assert "平台共享规则" in docs[0][1]
    assert "平台铁律" in docs[0][1]
    assert read_platform_documents(packaged_layout(), tmp_path / "nope") == []


# ------------------------------------------------- tier 2: protected
def _constitution_three_sections() -> str:
    return (
        "## Alpha\n" + "a" * 100 + "\n\n## Beta\n" + "b" * 100 + "\n\n## Gamma\n" + "c" * 100 + "\n"
    )


def test_protected_sections_never_cut_midsection() -> None:
    body = _constitution_three_sections()
    # Budget fits Alpha + Beta whole, but not Gamma.
    out = assemble_standing(
        [("CONSTITUTION.md", body)],
        budget_chars=10000,
        order=["CONSTITUTION.md"],
        protected_files=["CONSTITUTION.md"],
        protected_budget_chars=2
        * (len(render_injected("CONSTITUTION.md", "## Alpha\n" + "a" * 100)) + 2),
    )
    assert "## Alpha" in out and "a" * 100 in out
    assert "## Beta" in out and "b" * 100 in out
    # Gamma is either whole or fully absent — never a half section.
    assert "## Gamma" not in out
    assert "c" * 50 not in out


def test_protected_drop_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    body = _constitution_three_sections()
    with caplog.at_level(logging.WARNING):
        assemble_standing(
            [("CONSTITUTION.md", body)],
            budget_chars=10000,
            order=["CONSTITUTION.md"],
            protected_files=["CONSTITUTION.md"],
            protected_budget_chars=10,
        )
    assert any("standing section dropped" in r.message for r in caplog.records)


def test_protected_drop_strict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LCA_STRICT_STANDING", "1")
    with pytest.raises(StandingTruncationError):
        assemble_standing(
            [("CONSTITUTION.md", _constitution_three_sections())],
            budget_chars=10000,
            order=["CONSTITUTION.md"],
            protected_files=["CONSTITUTION.md"],
            protected_budget_chars=10,
        )


def test_persona_from_home_uses_tiers(tmp_path: Path) -> None:
    platform_root = tmp_path / "lca_home"
    _write(platform_root, "PLATFORM.md", "平台铁律")
    home = tmp_path / "asst"
    _write(home, "CONSTITUTION.md", "## 身份\n宪法正文")

    persona = persona_from_home(str(home), platform_root=platform_root)
    assert "平台铁律" in persona.backstory
    assert "宪法正文" in persona.backstory
    assert persona.backstory.index("平台铁律") < persona.backstory.index("宪法正文")


# ------------------------------------------------- tier 3: projection
def test_projection_drops_whole_sections_over_budget() -> None:
    body = "## M1\n" + "m" * 200 + "\n\n## M2\n" + "n" * 200 + "\n"
    out = assemble_standing(
        [("MEMORY.md", body)],
        budget_chars=300,
        order=["MEMORY.md"],
    )
    # No tier args: MEMORY.md is projection; one section fits, the other drops whole.
    assert "## M1" in out
    assert "## M2" not in out
    assert "n" * 20 not in out


def test_projection_drop_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    # ADR-0284 decision 2: projection drops warn (name + heading only), like tier 2.
    body = "## M1\n" + "m" * 500 + "\n"
    with caplog.at_level(logging.WARNING):
        assemble_standing([("MEMORY.md", body)], budget_chars=10, order=["MEMORY.md"])
    assert any("standing projection section dropped" in r.message for r in caplog.records)
    assert not any("m" * 20 in r.message for r in caplog.records)  # never logs content


def test_pack_sections_counts_wrapper_overhead() -> None:
    # A section that fits the raw budget but not with the injected markers is dropped.
    body = "## S\n" + "x" * 90
    wrapped_len = len(render_injected("F.md", "## S\n" + "x" * 90))
    blocks, _ = pack_sections([("F.md", body)], wrapped_len - 1)
    assert blocks == []
    blocks, _ = pack_sections([("F.md", body)], wrapped_len)
    assert len(blocks) == 1


# ------------------------------------------------- compaction entry
def test_preserve_standing_sections_refreshes_platform_block(tmp_path: Path) -> None:
    platform_root = tmp_path / "lca_home"
    _write(platform_root, "PLATFORM.md", "新平台规则")
    home = tmp_path / "asst"
    home.mkdir()

    text = render_injected("PLATFORM.md", "旧平台规则")
    out = preserve_standing_sections(text, DiskFileStore(home), platform_root=platform_root)
    assert "新平台规则" in out
    assert "旧平台规则" not in out


def test_preserve_standing_sections_platform_first(tmp_path: Path) -> None:
    platform_root = tmp_path / "lca_home"
    _write(platform_root, "PLATFORM.md", "平台铁律")
    home = tmp_path / "asst"
    _write(home, "MEMORY.md", "用户住在杭州")

    # A prompt assembled with the platform tier has PLATFORM.md first;
    # refresh replaces it in place and keeps the order.
    text = (
        render_injected("PLATFORM.md", "旧平台规则")
        + "\n\n"
        + render_injected("MEMORY.md", "旧记忆")
    )
    out = preserve_standing_sections(text, DiskFileStore(home), platform_root=platform_root)
    assert "平台铁律" in out
    assert "旧平台规则" not in out
    assert "用户住在杭州" in out
    assert out.index("平台铁律") < out.index("用户住在杭州")


# --------------------------------- decision 1: seed template + boot check
def test_platform_file_seeded_from_template(tmp_path: Path) -> None:
    # A fresh lca_home without PLATFORM.md gets it from the packaged seed template.
    from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout

    root = tmp_path / "lca_home"
    root.mkdir()
    layout = packaged_layout()
    docs = read_platform_documents(layout, root)
    assert (root / "PLATFORM.md").is_file()
    body = dict(docs)["PLATFORM.md"]
    assert "URL \u94c1\u5f8b" in body
    assert "\u51ed\u8bb0\u5fc6\u6216\u53c2\u6570\u77e5\u8bc6\u62fc\u88c5 URL" in body


def test_platform_file_seed_never_overwrites(tmp_path: Path) -> None:
    from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout

    root = tmp_path / "lca_home"
    _write(root, "PLATFORM.md", "## custom\ncustom rules")
    read_platform_documents(packaged_layout(), root)
    assert (root / "PLATFORM.md").read_text(encoding="utf-8") == "## custom\ncustom rules"


def test_missing_platform_files_lists_absent(tmp_path: Path) -> None:
    from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
    from lca.infrastructure.memory.contextfiles.service.assembly import (
        missing_platform_files,
    )

    root = tmp_path / "lca_home"
    root.mkdir()
    assert missing_platform_files(root, packaged_layout()) == ["PLATFORM.md"]
    _write(root, "PLATFORM.md", "x")
    assert missing_platform_files(root, packaged_layout()) == []


def test_boot_warns_on_missing_platform_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lca_kernel.boot.boot as boot_mod

    events: list[tuple[str, dict]] = []

    class _Log:
        def warning(self, event: str, **kw: object) -> None:
            events.append((event, kw))

    monkeypatch.setattr(boot_mod, "_log", _Log())
    monkeypatch.setattr(
        "lca.infrastructure.path.locator.get_lca_home",
        lambda: str(tmp_path / "empty_home"),
    )
    boot_mod._warn_missing_platform_files()
    assert any(e == "boot.platform_file_missing" for e, _ in events)

    (tmp_path / "empty_home").mkdir()
    _write(tmp_path / "empty_home", "PLATFORM.md", "x")
    events.clear()
    boot_mod._warn_missing_platform_files()
    assert events == []
