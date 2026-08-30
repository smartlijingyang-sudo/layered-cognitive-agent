"""weather tool module — simulated weather query."""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.infrastructure.tools.builder import build_tools_from_manifest

IDENTIFIER = "weather"
_SIMULATED_LATENCY_S = 0.05

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="getWeather",
            description="查询指定城市的天气（温度、天气状况）",
            parameters={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名（中英文均可，如 '北京'、'tokyo'）",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位，默认 celsius",
                    },
                },
                "required": ["city"],
            },
            is_idempotent=True,
        ),
    ),
    meta=ToolMeta(avatar="🌤️", title="Weather", description="Query city weather (simulated)"),
)


class WeatherExecutor:
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

    async def getWeather(self, params: dict[str, Any]) -> Observation:  # noqa: N802
        start = time.monotonic()
        raw_city = (
            str(params.get("city") or params.get("location") or params.get("name") or "")
            .strip()
            .lower()
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

        await asyncio.sleep(_SIMULATED_LATENCY_S)
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

        unit = str(params.get("unit", "celsius")).lower()
        temp_c = data["temp_c"]
        temp = temp_c if unit == "celsius" else temp_c * 9 / 5 + 32

        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "city": city,
                "temperature": round(temp, 1),
                "unit": unit,
                "condition": data["condition"],
            },
            latency_ms=latency_ms,
        )


def build_tools() -> list[Tool]:
    return build_tools_from_manifest(MANIFEST, WeatherExecutor())
