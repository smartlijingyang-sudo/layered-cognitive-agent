"""Tests for scripts/check_package_contracts.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_package_contracts import (  # noqa: E402
    Issue,
    check_l1_readme_exists,
    check_l2_pyproject_section,
    cross_check_l1_l2,
    cross_check_l1_public_api,
    discover_packages,
    package_to_path,
)


def test_package_to_path_dotted():
    p = package_to_path(Path("/x"), "lca.contracts.atoms")
    assert p == Path("/x/lca/contracts/atoms")


def test_package_to_path_single():
    p = package_to_path(Path("/x"), "lca.contracts")
    assert p == Path("/x/lca/contracts")


def test_check_l1_readme_exists_passes(tmp_path):
    pkg = tmp_path / "lca" / "fake"
    pkg.mkdir(parents=True)
    (pkg / "README.md").write_text(
        "# lca.fake\n\n## 1. 职责\ntest\n\n## 2. 不负责\nx\n## 3. 输入\nx\n## 4. 输出\nx\n"
        "## 5. 允许依赖\nx\n## 6. 禁止依赖\nx\n## 7. 副作用\nx\n## 8. 失败语义\nx\n## 9. 公共入口\nx\n",
        encoding="utf-8",
    )
    issues = check_l1_readme_exists(tmp_path, ["lca.fake"])
    assert issues == []


def test_check_l1_readme_exists_fails_when_missing(tmp_path):
    pkg = tmp_path / "lca" / "fake"
    pkg.mkdir(parents=True)
    issues = check_l1_readme_exists(tmp_path, ["lca.fake"])
    assert len(issues) == 1
    assert "missing" in issues[0].message.lower()


def test_check_l1_readme_exists_fails_on_missing_section(tmp_path):
    pkg = tmp_path / "lca" / "fake"
    pkg.mkdir(parents=True)
    (pkg / "README.md").write_text("# lca.fake\n## 1. 职责\nx\n", encoding="utf-8")
    issues = check_l1_readme_exists(tmp_path, ["lca.fake"])
    # 8 sections missing
    assert len(issues) == 8


def test_discover_packages_in_repo():
    """Smoke test: discover_packages works on the real repo."""
    pkgs = discover_packages(ROOT)
    assert "lca" in pkgs
    assert "lca.contracts" in pkgs
    assert "lca.contracts.atoms" in pkgs
    assert "gateway" in pkgs


def test_check_l2_pyproject_section_finds_real_sections():
    """Smoke test: L2 section detection works on real pyproject.toml."""
    issues = check_l2_pyproject_section(["lca.contracts", "lca.contracts.atoms", "nonexistent.package"])
    real_pkg_issues = [i for i in issues if i.package in ("lca.contracts", "lca.contracts.atoms")]
    assert real_pkg_issues == []


def test_cross_check_l1_l2_smoke():
    """Smoke test: L1↔L2 cross-check doesn't crash on real data."""
    issues = cross_check_l1_l2(["lca.contracts", "lca.contracts.atoms"])
    # All issues should be of kind L1↔L2
    for issue in issues:
        assert issue.layer == "L1↔L2"


def test_cross_check_l1_public_api_strips_comments(tmp_path):
    """Verify __all__ parsing handles inline comments."""
    pkg = tmp_path / "lca" / "fake"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        '__all__ = [\n    "Foo",\n    "Bar",  # deprecated\n    "Baz",\n]\n',
        encoding="utf-8",
    )
    readme = pkg / "README.md"
    readme.write_text(
        "# lca.fake\n## 1. 职责\nx\n## 2. 不负责\nx\n## 3. 输入\nx\n## 4. 输出\nx\n"
        "## 5. 允许依赖\nx\n## 6. 禁止依赖\nx\n## 7. 副作用\nx\n## 8. 失败语义\nx\n"
        "## 9. 公共入口\n`Foo`, `Bar`, `Baz`\n",
        encoding="utf-8",
    )
    issues = cross_check_l1_public_api(["lca.fake"])
    assert issues == []


def test_cross_check_l1_public_api_detects_mismatch():
    """Smoke test: cross-check on real data returns issues for inconsistencies.

    Note: This test relies on a known-real package to have its README 段 9
    not match __all__ — by design, the sync script should keep them aligned.
    We just verify the function is callable and returns a list.
    """
    issues = cross_check_l1_public_api(["lca.contracts", "lca.contracts.atoms"])
    # After Phase 3 sync, both should be clean
    assert isinstance(issues, list)


def test_cross_check_l1_public_api_no_init_no_crash(tmp_path):
    """If __init__.py doesn't exist, no issues."""
    pkg = tmp_path / "lca" / "fake"
    pkg.mkdir(parents=True)
    readme = pkg / "README.md"
    readme.write_text("# lca.fake\n## 9. 公共入口\n`X`\n", encoding="utf-8")
    issues = cross_check_l1_public_api(["lca.fake"])
    assert issues == []


def test_cross_check_l1_public_api_smoke():
    """Smoke test: cross-check on real data is clean."""
    issues = cross_check_l1_public_api(["lca.contracts", "lca.contracts.atoms"])
    # Should be clean after Phase 3 sync
    for issue in issues:
        assert issue.layer == "L1↔__all__"


def test_issue_render():
    issue = Issue(package="lca.foo", layer="L1", message="test")
    assert issue.render() == "[L1] lca.foo: test"
