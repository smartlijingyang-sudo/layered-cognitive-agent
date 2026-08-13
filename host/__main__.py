"""python -m host — attach this machine to the local gateway."""

from __future__ import annotations

import asyncio

from host.client import run_forever
from host.settings import HostSettings


def main() -> None:
    asyncio.run(run_forever(HostSettings()))


if __name__ == "__main__":
    main()
