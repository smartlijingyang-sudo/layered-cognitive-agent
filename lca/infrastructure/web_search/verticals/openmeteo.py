"""Weather vertical：api.open-meteo.com，无 key.

返回实时天气 + 预报，自带手册 19.3 要求的五个维度：
source（open-meteo.com）/ timestamp（observed_at）/ location（经纬度+时区）/
entity（weather_code）/ time period（hourly/daily 预报）.
因此 vertical 通道的数据可直接记为 VERIFIED（直连数据源，非索引快照）.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.infrastructure.web_search.errors import ProviderError

ENDPOINT = "https://api.open-meteo.com/v1/forecast"

_WMO_DESC = {
    0: "晴",
    1: "大致晴",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "轻毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "中阵雨",
    82: "大阵雨",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "强雷阵雨伴冰雹",
}


@dataclass(frozen=True, slots=True)
class HourlyPoint:
    """逐小时预报点."""

    time: str  # ISO
    temperature_c: float | None
    precipitation_probability: int | None


@dataclass(frozen=True, slots=True)
class WeatherReport:
    """一次天气查询的完整报告."""

    latitude: float
    longitude: float
    timezone: str
    observed_at: str  # current.time，ISO —— timestamp 维度
    temperature_c: float | None
    weather_code: int | None
    weather_desc: str
    hourly: tuple[HourlyPoint, ...] = ()
    source: str = "open-meteo.com"


def get_weather(
    latitude: float,
    longitude: float,
    *,
    days: int = 3,
    timezone: str = "auto",
    timeout: float = 15.0,
    http_client=None,
) -> WeatherReport:
    """查实时天气 + 预报. ``http_client`` 可注入（测试用 fake）."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
        "hourly": "temperature_2m,precipitation_probability",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": timezone,
        "forecast_days": days,
    }
    try:
        if http_client is not None:
            resp = http_client.get(ENDPOINT, params=params, timeout=timeout)
        else:
            import httpx  # 延迟 import

            resp = httpx.get(ENDPOINT, params=params, timeout=timeout)
    except Exception as e:
        raise ProviderError(f"open-meteo 请求失败: {e}") from e
    if resp.status_code != 200:
        raise ProviderError(f"open-meteo 返回 HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:
        raise ProviderError(f"open-meteo 响应解析失败: {e}") from e

    current = data.get("current") or {}
    hourly_raw = data.get("hourly") or {}
    times = hourly_raw.get("time") or []
    temps = hourly_raw.get("temperature_2m") or []
    probs = hourly_raw.get("precipitation_probability") or []
    hourly = tuple(
        HourlyPoint(
            time=t,
            temperature_c=temps[i] if i < len(temps) else None,
            precipitation_probability=probs[i] if i < len(probs) else None,
        )
        for i, t in enumerate(times)
    )
    code = current.get("weather_code")
    return WeatherReport(
        latitude=float(data.get("latitude", latitude)),
        longitude=float(data.get("longitude", longitude)),
        timezone=str(data.get("timezone", timezone)),
        observed_at=str(current.get("time", "")),
        temperature_c=current.get("temperature_2m"),
        weather_code=code,
        weather_desc=_WMO_DESC.get(code, "未知") if code is not None else "未知",
        hourly=hourly,
    )
