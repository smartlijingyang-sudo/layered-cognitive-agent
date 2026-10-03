"""Tests for verticals: openmeteo / datetime_local / stubs.

全部 mock，不碰真实网络.
"""

import pytest

from lca.infrastructure.web_search.errors import ProviderNotConfigured
from lca.infrastructure.web_search.providers.base import SearchProvider
from lca.infrastructure.web_search.verticals import build_default_handlers
from lca.infrastructure.web_search.verticals.datetime_local import now
from lca.infrastructure.web_search.verticals.openmeteo import get_weather
from lca.infrastructure.web_search.verticals.stubs import (
    FinanceProviderStub,
    NewsProviderStub,
    SportsProviderStub,
)
from lca.contracts.models.cognition.web_search import SearchRequest, Vertical


class _FakeResp:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self._status = status_code
        self.calls: list = []

    def get(self, url: str, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        return _FakeResp(self._payload, self._status)


_PAYLOAD = {
    "latitude": 28.2,
    "longitude": 112.9,
    "timezone": "Asia/Shanghai",
    "current": {"time": "2026-10-03T08:00", "temperature_2m": 17.5, "weather_code": 63},
    "hourly": {
        "time": ["2026-10-03T08:00", "2026-10-03T09:00"],
        "temperature_2m": [17.5, 18.0],
        "precipitation_probability": [80, 75],
    },
}


def test_openmeteo_parses_report() -> None:
    client = _FakeClient(_PAYLOAD)
    r = get_weather(28.2, 112.9, http_client=client)
    assert r.latitude == 28.2
    assert r.longitude == 112.9
    assert r.timezone == "Asia/Shanghai"
    assert r.observed_at == "2026-10-03T08:00"
    assert r.temperature_c == 17.5
    assert r.weather_code == 63
    assert r.weather_desc == "中雨"
    assert len(r.hourly) == 2
    assert r.hourly[0].precipitation_probability == 80
    assert r.source == "open-meteo.com"
    # 发到了正确的 endpoint，带经纬度
    assert client.calls[0]["url"].startswith("https://api.open-meteo.com/")
    assert client.calls[0]["params"]["latitude"] == 28.2


def test_openmeteo_unknown_code() -> None:
    payload = dict(_PAYLOAD)
    payload["current"] = dict(payload["current"], weather_code=999)
    r = get_weather(0, 0, http_client=_FakeClient(payload))
    assert r.weather_desc == "未知"


def test_openmeteo_non_200() -> None:
    from lca.infrastructure.web_search.errors import ProviderError

    with pytest.raises(ProviderError):
        get_weather(0, 0, http_client=_FakeClient({}, status_code=500))


def test_openmeteo_network_error_wraps() -> None:
    from lca.infrastructure.web_search.errors import ProviderError

    class _Boom:
        def get(self, *a, **k):
            raise ConnectionError("nope")

    with pytest.raises(ProviderError):
        get_weather(0, 0, http_client=_Boom())


def test_datetime_local_fields() -> None:
    t = now("Asia/Shanghai")
    assert t.tz_name == "Asia/Shanghai"
    assert t.utc_offset == "+08:00"
    assert len(t.date) == 10 and t.date[4] == "-" and t.date[7] == "-"
    assert t.weekday in ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
    assert t.iso.startswith(t.date)


def test_stubs_raise_not_configured() -> None:
    for stub in (NewsProviderStub(), SportsProviderStub(), FinanceProviderStub()):
        assert isinstance(stub, SearchProvider)  # 桩也满足协议
        with pytest.raises(ProviderNotConfigured) as e:
            stub.search("anything")
        assert "API" in str(e.value) or "key" in str(e.value).lower()


def test_default_handlers_cover_weather_datetime() -> None:
    handlers = build_default_handlers()
    assert set(handlers) == {Vertical.WEATHER, Vertical.DATETIME}


def test_weather_handler_missing_coords_fails_fast() -> None:
    # 缺经纬度时直接 ValueError，不发任何网络请求
    handlers = build_default_handlers()
    with pytest.raises(ValueError):
        handlers[Vertical.WEATHER](SearchRequest(query="天气", vertical=Vertical.WEATHER))


def test_weather_handler_verified(monkeypatch) -> None:
    import lca.infrastructure.web_search.verticals as verticals_mod
    from lca.infrastructure.web_search.verticals.openmeteo import (
        HourlyPoint,
        WeatherReport,
    )
    from lca.contracts.models.cognition.web_search import Verdict

    fake = WeatherReport(
        latitude=28.2,
        longitude=112.9,
        timezone="Asia/Shanghai",
        observed_at="2026-10-03T08:00",
        temperature_c=17.5,
        weather_code=63,
        weather_desc="中雨",
        hourly=(HourlyPoint(time="2026-10-03T08:00", temperature_c=17.5,
                            precipitation_probability=80),),
    )
    monkeypatch.setattr(verticals_mod, "get_weather", lambda *a, **k: fake)
    handlers = build_default_handlers()
    req = SearchRequest(query="长沙天气", vertical=Vertical.WEATHER,
                        vertical_params={"latitude": 28.2, "longitude": 112.9})
    outcome = handlers[Vertical.WEATHER](req)
    assert outcome.verdict is Verdict.VERIFIED  # 实时通道直连数据源
    assert "17.5" in outcome.page_text
    assert "中雨" in outcome.page_text
    assert "2026-10-03T08:00" in outcome.page_text  # timestamp 维度


def test_datetime_handler_verified() -> None:
    from lca.contracts.models.cognition.web_search import Verdict

    handlers = build_default_handlers()
    req = SearchRequest(query="现在几点", vertical=Vertical.DATETIME,
                        vertical_params={"tz": "Asia/Shanghai"})
    outcome = handlers[Vertical.DATETIME](req)
    assert outcome.verdict is Verdict.VERIFIED
    assert "Asia/Shanghai" in outcome.page_text
