---
name: agy-login-sop
description: >
  Log into the Antigravity CLI (`agy`) on this machine from a headless SSH session using the manual Google OAuth code flow. Covers fixing the Playwright driver/browser (Microsoft CDN is dead; use npmmirror mirror) when login fails with "token exchange failed", and managing multiple accounts with isolated data directories (agy follows $HOME). Use when the user asks to 登录 agy / log in to agy / antigravity 登录 / fix agy login / agy token exchange failed / agy 授权 / 多个 agy 账号切换 / agy 双账户.
---

# agy 登录 SOP (Antigravity CLI, headless SSH)

## 环境事实

- agy 二进制: `~/.local/bin/agy`;数据目录 `~/.gemini/antigravity-cli/`;日志在 `~/.gemini/antigravity-cli/log/`;token 文件 `~/.gemini/antigravity-cli/antigravity-oauth-token`
- **agy 的数据目录跟随 `$HOME`**:用 `HOME=/path/to/isolated-home agy` 启动,会在该 HOME 下创建全新的 `.gemini/antigravity-cli/`,token/历史/配置完全隔离 → 这是多账户并存的根基
- 本机**无显示器**(SSH 登录),代理/TUN 开启,国内网络;微软 Playwright CDN (`playwright.azureedge.net`) 已废弃,返回 404,必须用 npmmirror 镜像
- agy 的 OAuth `redirect_uri` 是远程的 `https://antigravity.google/oauth-callback`(不是 localhost),因此用户可以在**任意设备**的浏览器完成授权,然后粘贴 code
- 登录流程超时约 2-3 分钟,授权码有效期更短 → **必须尽快粘贴**

## 症状与根因

- 日志反复出现 `consumerOAuth: token exchange failed` / `gcpOAuth: token exchange failed` / `You are not logged into Antigravity`
- 根因链: Playwright driver 下载 404 → 浏览器无法打开 → 拿不到授权码 → 超时报 "token exchange failed"。
- 注意: token 端点本身网络是通的(可达),失败几乎总是"没有及时粘贴有效 code",不是网络问题。

## Step 1: 修复 Playwright driver + 浏览器(仅当 token exchange failed)

```bash
bash ~/.grok/skills/agy-login-sop/scripts/fix-playwright-driver.sh
```

- 作用: 从 npmmirror 下载 `playwright-1.57.0-linux.zip` 解压到 `~/.cache/ms-playwright-go/1.57.0/`,并用镜像源安装 Chromium v1200。
- 验证: 脚本输出 `Version 1.57.0`,且 `~/.cache/ms-playwright/chromium-1200` 存在。

## Step 2: 在 tmux 里启动 agy 并提取授权 URL

```bash
tmux kill-session -t agylogin 2>/dev/null
tmux new-session -d -s agylogin -x 400 -y 50 'cd /home/lichao/layered-cognitive-agent && agy'
sleep 8
tmux send-keys -t agylogin Enter   # 选择 "Google OAuth"
sleep 6
tmux capture-pane -t agylogin -p | sed 's/\x1b\[[0-9;]*m//g' > /tmp/agy-pane.txt
```

然后用 Python 拼接面板里换行的完整 URL:

```python
lines = open('/tmp/agy-pane.txt').read().splitlines()
url_lines = []
for i, l in enumerate(lines):
    if 'accounts.google.com' in l:
        for l2 in lines[i:]:
            s = l2.strip()
            if s.startswith('https://accounts.google.com') or (url_lines and s and '=' in s and not s.startswith(('After','─','(','shift'))):
                url_lines.append(s)
            elif url_lines:
                break
        break
print(''.join(url_lines))
```

- 屏幕提示是 `Open the URL below in your browser:`;URL 以 `state=...` 结尾。
- 把完整 URL 发给用户,让他在自己电脑浏览器打开并授权。

## Step 3: 用户授权后取回 code

- 用户打开链接 → Google 登录 → 点 **Allow / 同意**。
- 授权后浏览器跳到 `https://antigravity.google/oauth-callback?code=...&state=...`(页面可能 404,没关系,code 在地址栏)。
- 让用户把 **code 值**(`4/0...` 开头那串)发回来,或把整个回调 URL 发回来提取 `code=`。

## Step 4: 粘贴 code 并验证登录

```bash
tmux send-keys -t agylogin '<用户给的code>' Enter
sleep 8
tmux capture-pane -t agylogin -p   # 顶部应显示已登录邮箱
```

验证日志:

```bash
grep -iE "authenticated successfully|token acquired" $(ls -t ~/.gemini/antigravity-cli/log/*.log | head -1)
```

成功标志: `consumerOAuth: authenticated successfully as <email>`;token 文件已生成。

## 多账户隔离与切换

agy 数据目录跟随 `$HOME`,因此**每个账户一个隔离 HOME** 即可并存,token 互不覆盖,可同时运行。

### 已配置的在用账户 (Active Accounts)

数据源 SSOT 为 `~/.agy-accounts/accounts.json`，可通过 `agy-switch` 实时查看看板。

| 账户 | 登录邮箱 | 启动命令 | tmux 会话 | 注册/接入时间 | 登录与管理环境 | 状态与特征说明 |
|:---:|:---|:---:|:---:|:---:|:---|:---|
| **A** | `kuaikuaibaby@gmail.com` | `agy-a` | `agylogin` | 2026-09-20 | 任意环境 / 通用设备 | 稳定老号，无异地风控，兼兼容默认 `~/.gemini/` |
| **B** | `smartlijingyangbrother@gmail.com` | `agy-b` | `agylogin-b` | 2026-09-20 | 任意环境 / 通用设备 | 主力核心账号，作为新账号克隆基准模板 |
| **C** | `noqadanum01@gmail.com` | `agy-c` | `agylogin-c` | 2026-09-20 | 任意环境 / 通用设备 | 稳定老号，日常无限制使用 |
| **E** | `boistromspritio@gmail.com` | `agy-e` | `agylogin-e` | 2026-09-23 | **家里 Opera 浏览器** | 家里 Opera 登录管理，已激活 Google Cloud Shell 建立开发者信任 |
| **F** | `kolpasfasnuio@gmail.com` | `agy-f` | `agylogin-f` | 2026-09-23 | **家里 Opera 浏览器** | 家里 Opera 登录管理，首次授权已就绪 Starter Quota |
| **I** | `moretunrewial@gmail.com` | `agy-i` | `agylogin-i` | 2026-09-24 | 通用/扩展浏览器 | 第九账号，已完成初始化与 Superpowers 接入 |
| **M** | `crystalloverchen@gmail.com` | `agy-m` | `agylogin-m` | 2026-09-25 | 通用/扩展浏览器 | 第十三账号，Starter 缓冲额度，待升级 Google AI Pro |
| **N** | `peterpetrelee@gmail.com` | `agy-n` | `agylogin-n` | 2026-09-25 | 通用/扩展浏览器 | 第十四账号，Starter 缓冲额度，已就绪 |
| **O** | `jingjingthequee@gmail.com` | `agy-o` | `agylogin-o` | 2026-09-25 | 通用/扩展浏览器 | 第十五账号，Starter 缓冲额度，已就绪 |
| **P** | `johnyangbro@gmail.com` | `agy-p` | `agylogin-p` | 2026-09-25 | 通用/扩展浏览器 | 第十六账号，Starter 缓冲额度，满血就绪 |

### 废弃池子 (Deprecated Pool)

以下账号均因需要手机验证/扫码但当初手机无法使用导致 OAuth Token 失效，或 Starter 体验额度到期转入 SUBSCRIPTION_REQUIRED 无法恢复使用，已归档并在看板与命令中停用：
- **原 G**: `zandermarhanse@gmail.com` (浏览器会话过期触发扫码/手机验证，无法验证导致吊销)
- **D**: `huersebuied@gmail.com` (需手机二次验证，原手机无法接码，`invalid_grant`)
- **现 G**: `janniferarjune@gmail.com` (需手机二次验证，原手机无法接码，`invalid_grant`)
- **H**: `copelandmanuley@gmail.com` (需手机二次验证，原手机无法接码，`invalid_grant`)
- **Q**: `sarayangirl@gmail.com` (授权后触发 Google 风控拦截，OAuth 端点返回 `invalid_grant`，已清理废弃)
- **L**: `annayangirl@gmail.com` (并发刷新导致 OAuth Refresh Token 被 Google 吊销 `invalid_grant` 401，已清理废弃)
- **J**: `berrishecameilla@gmail.com` (Starter 体验配额到期且触发异地扫码风控，转入 SUBSCRIPTION_REQUIRED #3501 废弃)
- **K**: `jimiyangbro@gmail.com` (高强度消耗完 Starter 配额后触发设备二验扫码阻断，转入 SUBSCRIPTION_REQUIRED #3501 废弃)

- 在用账户 A / B / C / E / F / I / M / N / O / P 的隔离 HOME: `~/.agy-accounts/{a,b,c,e,f,i,m,n,o,p}/`
- 切换工具(已安装到 `~/.local/bin/`):
  - `agy-a` → 用 `HOME=/home/lichao/.agy-accounts/a` 启动 agy (账户 A)
  - `agy-b` → 用 `HOME=/home/lichao/.agy-accounts/b` 启动 agy (账户 B)
  - `agy-c` → 用 `HOME=/home/lichao/.agy-accounts/c` 启动 agy (账户 C)
  - `agy-e` → 用 `HOME=/home/lichao/.agy-accounts/e` 启动 agy (账户 E)
  - `agy-f` → 用 `HOME=/home/lichao/.agy-accounts/f` 启动 agy (账户 F)
  - `agy-i` → 用 `HOME=/home/lichao/.agy-accounts/i` 启动 agy (账户 I)
  - `agy-m` → 用 `HOME=/home/lichao/.agy-accounts/m` 启动 agy (账户 M)
  - `agy-n` → 用 `HOME=/home/lichao/.agy-accounts/n` 启动 agy (账户 N)
  - `agy-o` → 用 `HOME=/home/lichao/.agy-accounts/o` 启动 agy (账户 O)
  - `agy-p` → 用 `HOME=/home/lichao/.agy-accounts/p` 启动 agy (账户 P)
  - `agy-switch [a|b|c|e|f|i|m|n|o|p]` → 查看/切换不同账户会话; 多会话并存时直接 `tmux attach -t agylogin[-b|-c|-e|-f|-i|-m|-n|-o|-p]` 即可
  - Web 可视化管理平台: 局域网访问 `http://10.36.6.252:1888` (密码: `lichao12`)，提供实时额度雷达、全景任务看板、数据分析与 Web 终端控制台

### 新增账号的流程 (以账号 D 为例)

```bash
# 1. 基础缓存与浏览器驱动
mkdir -p ~/.agy-accounts/d/.cache
ln -sfn ~/.cache/ms-playwright-go ~/.agy-accounts/d/.cache/ms-playwright-go
ln -sfn ~/.cache/ms-playwright ~/.agy-accounts/d/.cache/ms-playwright
ln -sfn ~/.agents ~/.agy-accounts/d/.agents

# 2. 同步 Superpowers 技能与全局配置 (必须在启动前或启动后补齐，否则无 superpowers)
mkdir -p ~/.agy-accounts/d/.gemini/config
cp -r ~/.gemini/skills ~/.agy-accounts/d/.gemini/skills
cp -r ~/.gemini/antigravity ~/.agy-accounts/d/.gemini/antigravity
cp -r ~/.gemini/config/skills ~/.agy-accounts/d/.gemini/config/skills
cp ~/.gemini/GEMINI.md ~/.agy-accounts/d/.gemini/ 2>/dev/null || true
cp ~/.gemini/settings.json ~/.agy-accounts/d/.gemini/ 2>/dev/null || true
cp -r ~/.agent ~/.agy-accounts/d/.agent 2>/dev/null || true
cp -r ~/.agent-presets ~/.agy-accounts/d/.agent-presets 2>/dev/null || true

# 3. 创建启动脚本 ~/.local/bin/agy-d 并 chmod +x
cat << 'EOF' > ~/.local/bin/agy-d
#!/usr/bin/env bash
export HOME=/home/lichao/.agy-accounts/d
exec /home/lichao/.local/bin/agy "$@"
EOF
chmod +x ~/.local/bin/agy-d

# 4. 在 tmux 里启动并提取授权 URL
tmux kill-session -t agylogin-d 2>/dev/null
tmux new-session -d -s agylogin-d -x 400 -y 50 'cd /home/lichao/layered-cognitive-agent && HOME=/home/lichao/.agy-accounts/d agy'
sleep 8
tmux send-keys -t agylogin-d Enter
sleep 6
tmux capture-pane -t agylogin-d -p | sed 's/\x1b\[[0-9;]*m//g' > /tmp/agy-pane-d.txt
```

- 用同样方法拼接 `/tmp/agy-pane-d.txt` 中的完整授权 URL(见 Step 2 的 Python 片段),发给用户
- 收到 code 后 `tmux send-keys -t agylogin-d '<code>' Enter`
- 首次登录会进入初始化向导,需要按键走完:
  1. **Choose your color scheme**:默认 `terminal`,直接 Enter
  2. **Terms of Service**:checkbox 默认 `[x]`,按 **Tab 两次**(焦点从 checkbox → Previous → Done),再 Enter 确认。⚠️ 只按一次 Tab 焦点会落在 Previous,回车会退回配色页
  3. **Do you trust this folder?**:默认 `> Yes, I trust this folder`,直接 Enter
  4. 完成后顶部显示 `Welcome to Antigravity CLI!` + 登录邮箱
- 5. 补齐 CLI 权限配置并更新 `agy-switch`:
  ```bash
  cat ~/.agy-accounts/b/.gemini/antigravity-cli/settings.json > ~/.agy-accounts/d/.gemini/antigravity-cli/settings.json
  ```
- 验证:`grep -iE "authenticated successfully" $(ls -t ~/.agy-accounts/d/.gemini/antigravity-cli/log/*.log | head -1)`

### 多账户注意事项

- 不要对两个账户共用同一个 HOME,否则 token 文件互相覆盖,后登录的会踢掉先登录的
- 若某个账户的 token 过期/被撤销,只需重新走 Step 2–4(针对该账户的隔离 HOME),不影响另一个账户
## ⚠️ 账号维护血泪经验与避坑铁律 (Session Expired 防废号法则)

### 事故复盘（一）：原 G 账号废号根因
原 G 账号（`zandermarhanse@gmail.com`）在完成授权后，因管理环境中的**浏览器关闭退出 / 浏览器会话过期（Session Expired）**，导致触发了 Google 账号的安全重新登录与扫码验证。在境外代理/无固定设备指纹的开发环境下，突发 Session 失效引发的重新登录与重新扫描会直接联动 Google 身份安全中心将先前的 OAuth Refresh Token 撤销，本地 agy 报出：
`UNAUTHENTICATED (code 401): Request had invalid authentication credentials. Expected OAuth 2 access token...`（底层返回 `invalid_grant`），致使本地绑定的 CLI 凭证彻底报废，只能换号！

### 事故复盘（二）：2026-09-25 anna 暴雷与多账号雪崩连坐根因
2026-09-25 晚间，集群多账号突然接连报出 `403 PERMISSION_DENIED: Verify your account to continue`（典型 Trace 如 `Error ID: 226cf856-f53a-4f6e-8935-44df3a2afd7a-1`），彻底排查后确认了三重叠加根因链：
1. **新号纯闲置触发 24h 首检失效**：L 账号（`annayangirl@gmail.com`）在注册接入后的 24 小时内**完全零实际开发对话交互（调用量纯 0）**。在 Google 视角里，该新号仅有 AWS 机房 IP 在定时发机器心跳，而在原登录设备上却无任何生理活跃轨迹，在到达 24 小时审查关卡时被判定为弃用僵尸会话，下发 `Session Expired` 并联动吊销 Refresh Token（`invalid_grant` 401）。
2. **自动换号脚本（agy-auto）的雪崩放大效应**：L 账号失效后，调度器以 3 秒为间隔狂暴执行自动故障转移，在同一 AWS 机房 IP（`18.181.236.82`）上密集轮流切换 J ➔ E ➔ C ➔ F 发起 API 请求。这直接命中了 Google API 网关的反女巫防刷算法（Anti-Sybil），Google 对该出网 IP 实施了**短时全员连坐阻断**，导致老号和 Pro 号被误伤挂起。
3. **同账号双实例并发与系统资源击穿**：调度器在 tmux 已有常驻会话的情况下再次启动同账号子进程，双进程并发读写同一个 Keyring 与 Token，并击穿了 Linux 内核默认 `fs.inotify.max_user_instances=128`，导致文件监听和凭证读写彻底紊乱。

### 核心规程与铁律：
1. **【绝对红线一·整机并发限制】绝对不可多开超过 2 或 3 个 agy 会话或进程**：
   - 全机并发上限硬指标：任何时刻整台机器上运行的 `agy` 进程数**严禁超过 2~3 个**（日常仅保留 **1 个主力 B 账号**，极端交接/排错最多启动 1 个 A 账号）。
   - 严禁在多个 tmux、后台子 shell 或并发 agent 中随意拉起新 agy 实例，防止出网 IP 并发连接瞬间暴增触发 Google 防火墙并发拦截。
2. **【绝对红线二·调用频率限制】一定不能高频调用 Google API / Antigravity 端点**：
   - 保持真实人类开发节奏：阅读、思考、排查、调试与验证之间需有自然间隙。**严禁编写脚本对 agy 接口自动化轰炸、无限循环压力测试或秒级高频触发**。
   - 严禁自动化高频配额探测：已彻底停用任何在后台定时高频轮询 Google 配额/Token 的监控程序。
   - 单会话适度重构：单个会话步骤过长（> 40 步）或上下文过大时，主动 `/exit` 重启新会话，避免每次生成向 Google 发送超大 payload 触发深度审计。
3. **【铁律三】绝对不要主动退出浏览器或清理浏览器会话 (Session)**：
   - 凡是登录并管理过 agy 账号的浏览器（如公司电脑 Opera、家里电脑 Opera、专用 Profile 等），**严禁主动退出浏览器程序、清理 Cookie / 浏览历史，严禁点击 Google 账号“退出登录”**！
   - 浏览器窗口与后台 Session 必须**长期常驻保持在线态**。
4. **【铁律四】防止 Session Expired 连锁反应**：
   - Google 会定期对长时间无活动或网络 IP 突变的会话进行 Session 失效处理。若出现 Session Expired 提示重新登录/扫码，**千万不要在多变 IP 或随意的新设备上盲目重新扫码**。
   - 盲目操作极易被判定为异地盗号风控，导致 OAuth Refresh Token 被吊销。
5. **【铁律五】遇重登或风控提示，第一步先开 Cloud Shell 刷信任**：
   - 若浏览器出现重新登录或验证提示，**不要立即去扫 CLI 授权码**。
   - 优先在当前常驻浏览器内直接打开 👉 **`https://shell.cloud.google.com/`**，借助 Google 官方云端开发者环境刷新会话可信度，等 Cloud Shell 终端加载正常后再继续操作。
6. **【铁律六】固定设备、固定 Profile，坚决不交叉混用**：
   - 各组账号严格绑定独立浏览器环境，严格执行物理/环境隔离，避免多账号在同一未隔离的普通浏览器环境中来回切换。
7. **【铁律七】严禁编写与运行多账号秒级自动切号脚本（防连坐铁律）**：
   - 严禁任何在遇到 429/401 后自动秒级轮换唤醒下一账号的程序（如已被物理删除的 `agy-auto`）。
   - 单账号遇到限额或异常时必须立即停止，切忌向整个账号池顺序传导压力，避免因单点故障引爆整机房 IP 连坐风控。
8. **【铁律八】新账号接入必执行“破冰会话”（破冰法则）**：
   - 新号（特别是 Starter 冷号）接入后，**严禁 24 小时纯闲置挂机**！
   - 必须在接入后的首个 24 小时内，主动在终端发起 1~2 轮真实代码问答或任务交互，在 Google 后台打上真实开发者活跃标记（Token 消费记录），安全度过 24h 审查点。
9. **【铁律九】单账号严格单一实例，严禁并发双开（单实例法则）**：
   - 每个账号在系统内有且仅有一个专属的 tmux 常驻会话（`agylogin-<id>`）；
   - 日常交互统一使用 `tmux attach -t <会话名>` 或 `agy-switch` 接入，启动脚本内置 `EXISTING_PID` 进程级守护，严禁通过外部命令再次并发启动相同 HOME 目录的新 `agy` 进程，防止文件锁与 Token 竞态冲突。
10. **【铁律十】数据独立与物理隔离，严禁再次创建跨账号共享软链接**：
    - 2026-09-26 已全面拆除共享大脑 (`shared_memory`)。各账号必须保持独立的 `brain`、`conversations`、`history.jsonl` 与 `conversation_summaries.db`，杜绝任何会话指纹跨账号交叉暴露。
11. **【铁律十一】Per-Account 代理网络分流**：
    - 主力 B 账号走 `:7891` (`aws-ljy-reality`, `18.181.236.82`)；
    - 备用 A 账号走 `:7892` (`smartljy-reality`, `45.76.169.192`)；
    - 冷备 E 账号走 `:7893` (`smartljy-hy2`, `45.76.169.192`)；
    - 绝不同时使用相同出口 IP 刷新多账号凭证，避免 Anti-Sybil 连坐。

## 账号资格与风控拦截排查 (Eligibility & Security SOP)

在新账号登录或换号时，常见由于订阅状态、年龄设置或异地代理导致的三大类问题及解决办法：

### 1. 资格未满足: `Eligibility check failed: Your current account is not eligible for Antigravity`

- **根因 A (未开通 Google AI Pro)**:
  - Antigravity CLI 针对个人 Google 账号**必须拥有 Google AI Pro**（即 Google One AI Premium / Gemini Advanced）订阅或试用资格。
  - 普通免费个人 Google 账号调用后端 `daily-cloudcode-pa.googleapis.com` 会返回 `UNSUPPORTED_CLIENT` 错误。
  - **解决**: 在浏览器登录该账号，打开 `https://one.google.com/explore-plan/gemini-advanced` 开通 1 个月免费试用或付费订阅。开通成功后，账号 banner 才会显示 `(Google AI Pro)`。
- **根因 B (账号年龄未成年/未填生日)**:
  - Google Cloud 对 AI 开发者功能限制严格，未满 18 岁或未设置生日的账号会被拒绝。
  - **解决**: 访问 `https://myaccount.google.com/birthday`，将出生年份设置为 2000 年或更早（确保 >= 18 岁）。

### 2. 异地代理风控拦截与资格异常: `403 PERMISSION_DENIED: Verify your account to continue` (`al_alert` / `VALIDATION_REQUIRED`)

- **现象**: CLI 报 `Eligibility check failed: Your current account is not eligible for Antigravity. Verify your account to continue.`，后台日志出现 `PERMISSION_DENIED (code 403): Verify your account to continue.`，附带 `https://accounts.google.com/signin/continue?sarp=1&scc=1&continue=...` 链接，即便手机扫码仍可能反复被拒。
- **【核心根治方案】直接开通 Google Cloud Shell（实测最终靠此彻底解决，首推必做）**:
  - **操作**: 在浏览器中确保登录目标账号，直接打开并激活一次 Google Cloud Shell：
    👉 **`https://shell.cloud.google.com/`**
  - **核心原理（为什么必须靠它）**:
    普通扫码验证只完成了 Google 账号层面的基础放行，但在异地/海外代理环境下请求 Antigravity 后端（`daily-cloudcode-pa.googleapis.com`）时，GCP 开发者网关仍会因缺乏可信开发者上下文而判定为高风险环境阻断服务。**激活一次 Cloud Shell 会在 GCP 端完整初始化该账号的合法开发者环境与项目信任**，Google 会自动将该账号在开发者环境下的风控放行，瞬间消除 `VALIDATION_REQUIRED` 与 `Eligibility check failed` 阻断！
- **辅助验证流程与避坑要点（如果配合使用验证链接）**:
  - **避坑点 1 (防止浏览器账号串号)**: Google 的验证链接默认带 `&authuser`，如果直接在常用浏览器打开，会误拿默认主账号通过验证，导致新账号实际未过。必须使用**无痕窗口 / 隐身窗口**打开，或在链接末尾拼接 `&login_hint=<目标邮箱>` 强行锁定新账号。
  - **避坑点 2 (必须点击最终跳转按钮)**: 手机扫码或输入密码后，页面提示绿色对勾“身份验证成功”**并不代表流程结束**。**必须点击右下角蓝色的【继续】(Continue) 按钮**，直到浏览器地址栏真正跳转到 `https://developers.google.com/gemini-code-assist/auth/auth_success_gemini`（显示 Authentication successful），Google 后台才算真正记录放行。

### 3. Token 强制刷新与生效

网页端完成验证或开通 AI Pro 后，旧的 `access_token` 不会自动更新 claims。可使用下面的 Python 命令快速刷新并持久化：

```bash
# 注意代理端口与账号对应关系：B 账号用 7891，A 账号用 7892，E 账号用 7893
python3 -c "
import json, urllib.request, urllib.parse
data = json.load(open('/home/lichao/.agy-accounts/<account-letter>/.gemini/antigravity-cli/antigravity-oauth-token'))
body = urllib.parse.urlencode({
    'client_id': data.get('clientID', ''),
    'client_secret': data.get('clientSecret', ''),
    'grant_type': 'refresh_token',
    'refresh_token': data['token']['refresh_token'],
}).encode()
# 根据账号选择端口: B -> 7891, A -> 7892, E -> 7893
port = 7891 if '<account-letter>' == 'b' else (7892 if '<account-letter>' == 'a' else 7893)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': f'http://127.0.0.1:{port}', 'https': f'http://127.0.0.1:{port}'}))
resp = opener.open(urllib.request.Request('https://oauth2.googleapis.com/token', data=body))
data['token']['access_token'] = json.load(resp)['access_token']
json.dump(data, open('/home/lichao/.agy-accounts/<account-letter>/.gemini/antigravity-cli/antigravity-oauth-token', 'w'))
print(f'Token refreshed successfully via port {port}!')
"
```

## 巡检与健康诊断

随时运行 `agy-health-check` 巡检当前活跃账号状态与日志报警（429、403、`invalid_grant`、未登录风暴）：

```bash
agy-health-check       # 查看最近 500 行日志统计
agy-health-check 2000  # 查看最近 2000 行深入统计
```

## 注意事项

- 若上一次流程已超时/退出,直接重新执行 Step 2(会生成新的 URL 和 state,旧 code 作废)。
- 用户在同意页复制的是 `accounts.google.com/signin/oauth/consent?...` 时,提醒他先点 Allow,再复制跳转后的回调 URL。
- agy 的 TUI 提示可能是 "paste the URL" 或 "paste the authorization code",两种都给 `code=` 的值即可。
- 本机 sshd 已开 `X11Forwarding yes` 且装有 xauth,但 headless 下手动 code 流程更可靠,优先用本 SOP。
- 清理: 登录完成后可 `tmux kill-session -t agylogin`,删除 `/tmp/agy-pane.txt`。