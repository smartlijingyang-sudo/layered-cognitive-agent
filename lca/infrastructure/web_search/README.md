# web_search —— 浏览器搜索通道（Muse 对齐，手册第 19 章）

## 1. 职责

`SearchRouter` 是唯一搜索入口，按任务路由到搜索、页面抓取或浏览器交互能力。模块提供天气和时间等垂直搜索适配器，并为新闻、体育和金融垂直域保留 provider 接缝。

## 2. 不负责

- 不保证搜索结果真实、完整或适用于法律、医疗、金融等高风险决定；调用方应核对来源和时效。
- 不实现新闻、体育、金融等尚未接入的数据源；当前这些 provider 是 stub。
- 不负责用户账号登录或跨浏览器配置管理；CDP 模式仅连接调用方已配置的 Chrome。

## 3. 三层路由

```text
SEARCH（providers/duckduckgo.py，无 key）
  → FETCH（fetch.py：httpx + trafilatura/readability/raw）
  → BROWSE（browser.py：Playwright 三模式）
```

路由纪律见 `router.py` 模块 docstring。

## 4. 垂直搜索（`verticals/`）

| vertical | 状态 | 数据源 |
|---|---|---|
| weather | 已实现 | api.open-meteo.com，无 key |
| datetime | 已实现 | 本机时钟，纯标准库 |
| news / sports / finance | stub | `stubs.py`，需要接入对应数据源 |

新增垂直 provider 时，实现 `SearchProvider.search(query) -> list[SearchResult]` 并替换 `stubs.py` 中的对应类；router 侧不需改变。

## 5. 浏览器模式（`browser.py`）

- `headless`：无头 Chromium，默认模式。
- `headful-xvfb`：有头浏览器加虚拟显示（`xvfb-run -a`）。
- `cdp-persistent`：连接常驻 Chrome 和其 user-data-dir，可复用该浏览器配置中的登录态。

Playwright 延迟导入。缺少可选浏览器依赖时抛出带安装指引的 `FeatureUnavailableError`。

## 6. 错误与配置

网络请求、页面读取和浏览器操作的错误由各自 provider 显式返回或抛出；可选依赖不可用时不伪装成空搜索结果。未接入垂直域会返回 stub 行为，调用方不得将其解释为已查询真实数据源。

## 7. 副作用

搜索和抓取会发起外部网络请求并读取公开页面。`cdp-persistent` 会使用指定 Chrome 的 user-data-dir，因此可能访问该浏览器已有登录态；测试必须 mock provider，禁止访问真实网络。

## 测试

`tests/infrastructure/web_search/` 的测试全部 mock，不访问真实网络：

```bash
python3 -m pytest tests/infrastructure/web_search/ -q
```
