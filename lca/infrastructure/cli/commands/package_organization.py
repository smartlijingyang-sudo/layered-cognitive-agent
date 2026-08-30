"""Phase D CI gate runner: ``diagnose package-organization``.

Runs every ``scripts/check_*.py`` Phase-D gate in sequence and
returns a non-zero exit code if any one fails. Used by both the
``lca-ops diagnose package-organization`` CLI and the CI ``package-
organization`` job.

Each gate script is a thin wrapper that imports a single lca check
function. ``main(argv)`` returns 0 on success / non-zero on violation.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

SCRIPTS_DIR = Path(__file__).resolve().parents[4] / "scripts"

GATES: list[tuple[str, Path]] = [
    ("package-size",          SCRIPTS_DIR / "check_package_size.py"),
    ("no-barrel-glob",        SCRIPTS_DIR / "check_no_barrel_glob.py"),
    ("no-utility-modules",    SCRIPTS_DIR / "check_no_utility_modules.py"),
    ("package-noun",          SCRIPTS_DIR / "check_package_noun.py"),
    ("known-abbrev",          SCRIPTS_DIR / "check_known_abbrev.py"),
    ("package-integrity",     SCRIPTS_DIR / "check_package_integrity.py"),
    ("tests-layout",          SCRIPTS_DIR / "check_tests_layout.py"),
    ("readme-filled",         SCRIPTS_DIR / "check_readme_filled.py"),
]


def register(app: typer.Typer) -> None:
    """Register ``diagnose package-organization`` on the typer app."""

    @app.command(name="diagnose-package-organization")
    def diagnose_package_organization(
        gate: list[str] = typer.Option(
            None,
            "--gate",
            help="Limit to specific gate names; default = run all",
        ),
        verbose: bool = typer.Option(
            False, "--verbose", "-v", help="Print full gate output, not just summary"
        ),
    ) -> None:
        """Run every Phase-D package-organization CI gate.

        Exit code: 0 if all gates pass, 1 if any fails. Stdout shows a
        per-gate pass/fail; --verbose includes the full output of
        each gate.
        """
        targets = GATES if not gate else [
            g for g in GATES if g[0] in gate
        ]
        if not targets:
            print(f"Unknown gate(s): {gate}. Known: {[g[0] for g in GATES]}")
            raise typer.Exit(2)

        failures: list[str] = []
        for name, script in targets:
            if not script.exists():
                print(f"  ✗ {name}: missing {script}")
                failures.append(name)
                continue
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"  ✓ {name}")
            else:
                print(f"  ✗ {name}")
                if verbose:
                    print(result.stdout)
                    print(result.stderr, file=sys.stderr)
                failures.append(name)

        total = len(targets)
        if failures:
            print(
                f"package-organization: {len(failures)}/{total} gate(s) failed: "
                f"{', '.join(failures)}"
            )
            raise typer.Exit(1)
        print(f"package-organization: {total}/{total} gates passed.")
