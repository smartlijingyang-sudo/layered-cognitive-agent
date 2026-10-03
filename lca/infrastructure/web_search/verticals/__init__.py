"""实时 verticals：weather / datetime 已实现，news / sports / finance 为桩."""

from lca.contracts.models.cognition.web_search import (
    SearchOutcome,
    SearchRequest,
    SearchTier,
    Verdict,
    Vertical,
)
from lca.infrastructure.web_search.verticals.datetime_local import LocalTime, now
from lca.infrastructure.web_search.verticals.openmeteo import WeatherReport, get_weather
from lca.infrastructure.web_search.verticals.stubs import (
    FinanceProviderStub,
    NewsProviderStub,
    SportsProviderStub,
)


def _weather_handler(request: SearchRequest) -> SearchOutcome:
    """Weather vertical：直连 open-meteo，结果记 VERIFIED（实时数据源）."""
    p = request.vertical_params
    try:
        lat = float(p["latitude"])
        lon = float(p["longitude"])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(
            "weather vertical 需要 vertical_params.latitude/longitude（十进制度）"
        ) from e
    report = get_weather(lat, lon)
    text = (
        f"[{report.source} @ {report.observed_at}]\n"
        f"位置 ({report.latitude}, {report.longitude}) {report.timezone}\n"
        f"实况 {report.temperature_c}°C，{report.weather_desc}\n"
        + "\n".join(
            f"{h.time}: {h.temperature_c}°C，降水概率 "
            f"{h.precipitation_probability if h.precipitation_probability is not None else '?'}%"
            for h in report.hourly[:24]
        )
    )
    return SearchOutcome(
        results=(),
        tier_reached=SearchTier.SEARCH,
        verdict=Verdict.VERIFIED,
        citations=(),
        notes=("vertical 实时通道直连数据源，非索引快照",),
        page_text=text,
        page_url="https://api.open-meteo.com/v1/forecast",
    )


def _datetime_handler(request: SearchRequest) -> SearchOutcome:
    """Datetime vertical：本机时钟，结果记 VERIFIED."""
    tz = request.vertical_params.get("tz")
    t = now(tz)
    text = f"{t.iso}（{t.weekday}，{t.tz_name}，UTC{t.utc_offset}）"
    return SearchOutcome(
        results=(),
        tier_reached=SearchTier.SEARCH,
        verdict=Verdict.VERIFIED,
        citations=(),
        notes=("vertical 实时通道：本机时钟",),
        page_text=text,
        page_url="",
    )


def build_default_handlers() -> dict:
    """router 可用的 vertical handlers：WEATHER/DATETIME 已实现，其余为桩."""
    return {
        Vertical.WEATHER: _weather_handler,
        Vertical.DATETIME: _datetime_handler,
    }


__all__ = [
    "FinanceProviderStub",
    "LocalTime",
    "NewsProviderStub",
    "SportsProviderStub",
    "WeatherReport",
    "build_default_handlers",
    "get_weather",
    "now",
]
