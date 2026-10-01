"""Regression: a listFiles directory listing must not count as created files.

``run_28aa7eb3261b`` 的 ``listFiles`` 返回带 ``isDirectory`` 的目录条目，
``_extract_files_created`` 把 ``payload["files"]`` 当产出文件，journal 因此
写成「写出 20 个文件」，doctor 和 artifact_closure 跟着把助手 home 目录
当成这次 run 的产物。带 ``isDirectory`` 键的条目是目录/文件清单，
不是 harvest 的 A2A 文件元数据（``mimeType`` / ``attachmentId``）。
"""

from __future__ import annotations

from lca.cognition.body.executor.safe_executor import _extract_files_created
from lca.cognition.convergence.payload import payload_files_created
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation

_LISTING = [
    {"name": "dreams", "isDirectory": True, "path": "/home/u/dreams"},
    {"name": "memory", "isDirectory": True, "path": "/home/u/memory"},
    {"name": "USER.md", "isDirectory": False, "path": "/home/u/USER.md"},
    {"name": "MEMORY.md", "isDirectory": False, "path": "/home/u/MEMORY.md"},
]


def _listing_observation() -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"stdout": _LISTING, "files": _LISTING},
        extra={"invocation_id": "toolu_list", "files": _LISTING},
    )


def test_listing_entries_are_not_files_created() -> None:
    obs = _listing_observation()
    # 目录和文件清单都不能算作「本次写出的文件」
    assert _extract_files_created(obs) == ()
    assert payload_files_created(obs.payload or {}) == ()


def test_plain_string_entries_still_work() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"files_created": ["report.md"]},
    )
    assert _extract_files_created(obs) == ("report.md",)


def test_harvest_entries_still_work() -> None:
    harvested = [
        {
            "name": "chart.png",
            "mimeType": "image/png",
            "sizeBytes": 20481,
            "url": "/files/att_chart",
            "previewable": True,
            "attachmentId": "att_chart",
        }
    ]
    obs = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"files": harvested},
        extra={"files": harvested},
    )
    assert _extract_files_created(obs) == ("chart.png",)