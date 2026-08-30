from pathlib import Path
from zipfile import ZipFile


def main() -> None:
    wheel = next(Path("/tmp/lca-dist").glob("*.whl"))
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        print(f"wheel={wheel.name}")
        print(f"files={len(names)}")
        for prefix in ("lca/", "gateway/", "skills/", "roles/", "profiles/", "tests/"):
            print(f"{prefix}{sum(name.startswith(prefix) for name in names)}")
        unexpected = [
            name
            for name in names
            if name.startswith(("skills/", "roles/", "profiles/", "tests/", "vendor/"))
        ]
        if unexpected:
            raise SystemExit(f"unexpected package files: {unexpected[:5]}")


if __name__ == "__main__":
    main()
