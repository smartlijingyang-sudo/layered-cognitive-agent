"""WeatherTool —— 查询城市天气（内置假数据，无需外部网络）。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

from lca.contracts.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.decision import Observation
from lca.contracts.ids import new_id
from lca.contracts.protocols import Tool

_SIMULATED_LATENCY_S = 0.05


class WeatherTool(Tool):
    """实现 Tool 的天气查询工具。

    内置假数据，避免依赖外部网络，专注测试 tool 调度本身。
    """

    name = "get_weather"
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    _FAKE_DB: ClassVar[dict[str, dict[str, Any]]] = {
        "tokyo": {"temp_c": 27, "condition": "cloudy"},
        "beijing": {"temp_c": 31, "condition": "sunny"},
        "san francisco": {"temp_c": 18, "condition": "foggy"},
        "new york": {"temp_c": 24, "condition": "clear"},
        "london": {"temp_c": 19, "condition": "rainy"},
    }
    _CITY_ALIASES: ClassVar[dict[str, str]] = {
        "东京": "tokyo",
        "東京": "tokyo",
        "北京": "beijing",
        "旧金山": "san francisco",
        "纽约": "new york",
        "伦敦": "london",
    }

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        raw_city = (
            str(args.get("city") or args.get("location") or args.get("name") or "").strip().lower()
        )
        city = self._CITY_ALIASES.get(raw_city, raw_city)

        if not city:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="missing required arg: city",
                latency_ms=latency_ms,
            )

        await asyncio.sleep(_SIMULATED_LATENCY_S)  # 模拟网络 IO

        data = self._FAKE_DB.get(city)
        if data is None:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"unknown city: {city}",
                latency_ms=latency_ms,
            )

        unit = str(args.get("unit", "celsius")).lower()
        temp_c = data["temp_c"]
        temp = temp_c if unit == "celsius" else temp_c * 9 / 5 + 32

        result = {
            "city": city,
            "temperature": round(temp, 1),
            "unit": unit,
            "condition": data["condition"],
        }
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=result,
            latency_ms=latency_ms,
        )
