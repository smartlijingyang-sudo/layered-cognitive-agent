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

### 已配置的账户(本机现状与台账)

数据源 SSOT 为 `~/.agy-accounts/accounts.json`，可通过 `agy-switch` 实时查看看板。

| 账户 | 登录邮箱 | 启动命令 | tmux 会话 | 注册/接入时间 | 登录与管理环境 | 状态与特征说明 |
|:---:|:---|:---:|:---:|:---:|:---|:---|
| **A** | `kuaikuaibaby@gmail.com` | `agy-a` | `agylogin` | 2026-09-20 | 任意环境 / 通用设备 | 稳定老号，无异地风控，兼兼容默认 `~/.gemini/` |
| **B** | `smartlijingyangbrother@gmail.com` | `agy-b` | `agylogin-b` | 2026-09-20 | 任意环境 / 通用设备 | 主力核心账号，作为新账号克隆基准模板 |
| **C** | `noqadanum01@gmail.com` | `agy-c` | `agylogin-c` | 2026-09-20 | 任意环境 / 通用设备 | 稳定老号，日常无限制使用 |
| **D** | `huersebuied@gmail.com` | `agy-d` | `agylogin-d` | 2026-09-22 | **公司 Opera 浏览器** | 公司机 Opera 保持登录态，用于日常授权与维护 |
| **E** | `boistromspritio@gmail.com` | `agy-e` | `agylogin-e` | 2026-09-23 | **家里 Opera 浏览器** | 家里 Opera 登录管理，已激活 Google Cloud Shell 建立开发者信任 |
| **F** | `kolpasfasnuio@gmail.com` | `agy-f` | `agylogin-f` | 2026-09-23 | **家里 Opera 浏览器** | 家里 Opera 登录管理，首次授权已就绪 Starter Quota |

- 账户 A / B / C / D / E / F 的隔离 HOME: `~/.agy-accounts/{a,b,c,d,e,f}/`, 其中 `.cache/ms-playwright-go` 符号链接到 `~/.cache/ms-playwright-go`, 复用浏览器驱动
- 切换工具(已安装到 `~/.local/bin/`):
  - `agy-a` → 用 `HOME=/home/lichao/.agy-accounts/a` 启动 agy (账户 A)
  - `agy-b` → 用 `HOME=/home/lichao/.agy-accounts/b` 启动 agy (账户 B)
  - `agy-c` → 用 `HOME=/home/lichao/.agy-accounts/c` 启动 agy (账户 C)
  - `agy-d` → 用 `HOME=/home/lichao/.agy-accounts/d` 启动 agy (账户 D)
  - `agy-e` → 用 `HOME=/home/lichao/.agy-accounts/e` 启动 agy (账户 E)
  - `agy-f` → 用 `HOME=/home/lichao/.agy-accounts/f` 启动 agy (账户 F)
  - `agy-switch [a|b|c|d|e|f]` → 查看/切换不同账户会话; 多会话并存时直接 `tmux attach -t agylogin[-b|-c|-d|-e|-f]` 即可
  - Web 可视化管理平台: 局域网访问 `http://10.36.6.252:1888` (密码: `lichao12`)，提供实时额度雷达、数据分析与 Web 终端控制台

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
- 旧的默认 HOME 里若残留不合格账户(如 `noqadanum01@gmail.com`)的 token,直接删除 `~/.gemini/antigravity-cli/antigravity-oauth-token` 即可,或先备份到 `/tmp/`

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
python3 -c "
import json, urllib.request, urllib.parse
data = json.load(open('/home/lichao/.agy-accounts/<account-letter>/.gemini/antigravity-cli/antigravity-oauth-token'))
body = urllib.parse.urlencode({
    'client_id': '<AGY_GOOGLE_CLIENT_ID>',
    'client_secret': '<AGY_GOOGLE_CLIENT_SECRET>',
    'grant_type': 'refresh_token',
    'refresh_token': data['token']['refresh_token'],
}).encode()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}))
resp = opener.open(urllib.request.Request('https://oauth2.googleapis.com/token', data=body))
data['token']['access_token'] = json.load(resp)['access_token']
json.dump(data, open('/home/lichao/.agy-accounts/<account-letter>/.gemini/antigravity-cli/antigravity-oauth-token', 'w'))
print('Token refreshed successfully!')
"
```

## 注意事项

- 若上一次流程已超时/退出,直接重新执行 Step 2(会生成新的 URL 和 state,旧 code 作废)。
- 用户在同意页复制的是 `accounts.google.com/signin/oauth/consent?...` 时,提醒他先点 Allow,再复制跳转后的回调 URL。
- agy 的 TUI 提示可能是 "paste the URL" 或 "paste the authorization code",两种都给 `code=` 的值即可。
- 本机 sshd 已开 `X11Forwarding yes` 且装有 xauth,但 headless 下手动 code 流程更可靠,优先用本 SOP。
- 清理: 登录完成后可 `tmux kill-session -t agylogin`,删除 `/tmp/agy-pane.txt`。