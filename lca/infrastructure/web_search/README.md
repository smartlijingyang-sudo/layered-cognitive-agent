# web_search —— 浏览器搜索通道（Muse 对齐，手册第 19 章）

## 三层路由

```
SEARCH（providers/duckduckgo.py，无 key）
  → FETCH（fetch.py：httpx + trafilatura/readability/raw）
  → BROWSE（browser.py：playwright 三模式）
```

`router.py` 的 `SearchRouter` 是唯一入口。纪律见 `router.py` 模块 docstring。

## Verticals（`verticals/`）

| vertical | 状态 | 数据源 |
|---|---|---|
| weather | ✅ 已实现 | api.open-meteo.com，无 key |
| datetime | ✅ 已实现 | 本机时钟，纯 stdlib |
| news / sports / finance | 🧱 桩 | `stubs.py`，需 API key 接入 |

桩的接入方式：实现 `SearchProvider.search(query) -> list[SearchResult]` 后替换
`stubs.py` 中的对应类，router 侧零改动（协议已定）。

## BROWSE 三模式（`browser.py`）

- `headless`：无头 Chromium，默认
- `headful-xvfb`：有头 + 虚拟显示（`xvfb-run -a`）
- `cdp-persistent`：常驻 Chrome + user-data-dir，登录态跨次复用

playwright 延迟 import；缺依赖抛 `FeatureUnavailableError`（带安装指引）。

## 测试

`tests/infrastructure/web_search/`：全部 mock，**不许碰真实网络**。
`python3 -m pytest tests/infrastructure/web_search/ -q`
