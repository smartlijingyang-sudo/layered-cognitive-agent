"""RA-053: ``lca-ops doctor`` is mounted on the REAL root CLI app.

Lesson from RA-053: CLI ``register()`` tests that build a fresh
``typer.Typer()`` never catch "unmounted in the real root app" — the
``doctor`` group lived in ``commands/doctor/profile.py`` for many rounds
without being registered on the entry-point app. This pin goes through
the real ``lca-ops`` root app and asserts the command path is reachable.
"""

from __future__ import annotations

from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app as root_app


class TestDoctorRootMount:
    """The doctor command group is reachable on the real root app."""

    def test_doctor_group_listed_on_root_app(self) -> None:
        runner = CliRunner()
        result = runner.invoke(root_app, ["doctor", "--help"])
        assert result.exit_code == 0, result.output
        assert "profile" in result.output

    def test_doctor_profile_help_reachable_on_root_app(self) -> None:
        runner = CliRunner()
        result = runner.invoke(root_app, ["doctor", "profile", "--help"])
        assert result.exit_code == 0, result.output
        assert "--ci" in result.output
        assert "--json" in result.output
        assert "--skip-plugin-shape" in result.output
