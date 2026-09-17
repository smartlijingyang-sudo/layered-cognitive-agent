# Agent Note: 沙箱 CJK 是环境事实

Status: implemented

## Problem

用户要一份带中文的可视化报告。模型把 `font.sans-serif` 设成提示里的 WenQuanYi Zen Hei / Noto Sans CJK。工作器上没有这两个 family。matplotlib 回落到 DejaVu Sans，中文缺字。模型再 `fc-list`，把 300s 墙钟花在改字体上。`executeCode` 每次是新解释器，上一轮变量不在内存里，整份出图脚本重写一遍。

## Decision

CJK 画图是 guest 环境事实，不是提示购物清单。

`execute()` 在 Python 用户代码前插入 `apply_matplotlib_cjk`。它注册工作器上真实存在的字体文件，并包装 `pyplot.savefig`：当前 `font.sans-serif` 都不在 font manager 里时，恢复可用 family。Harvest stub 不插入这段。

`cloud_sandbox_system_role` 不列出 Zen Hei / Noto。它写明不要设 `font.sans-serif`、不要 `fc-list`。PDF 仍用 reportlab `STSong-Light`。`executeCode` 的 schema 写明每次是新解释器。`matplotlibrc` 把 WenQuanYi Micro Hei 放进回退链。Harvest scanner 对超限文件打印诊断。

## Alternatives considered

### Why not 把墙钟从 300s 调到 900s？

超时是后果。模型仍会覆盖字体、仍会当 REPL 用。加时间不修交付。

### Why not 只改提示，告诉模型用 Micro Hei？

同一条提示已经写过 Zen Hei「系统有」。模型照抄覆盖了 matplotlibrc 的回退。文本失败过，不再加一条字体名。

### Why not 启用 SkillRouter / 强制 pdf skill？

那是 Profile 拓扑。这次失败发生在 executeCode 画图路径上，图表本来就该走 matplotlib。

## Consequences

有 Micro Hei 或 Droid Sans Fallback 的 guest 上，模型覆盖缺失 family 后 `savefig` 仍出中文。模型少一轮 `fc-list`。每次 executeCode 的 schema 说明新解释器。Harvest 失败可见。镜像仍建议装 `fonts-wqy-zenhei`；缺它也能回退。

## Verification

`tests/infrastructure/sandbox/test_matplotlib_cjk_guest.py`：无 bootstrap 时缺字；有 bootstrap 时同一段覆盖代码不再缺字。

`tests/infrastructure/sandbox/test_cjk_bootstrap_prepend.py`：用户 execute 带 bootstrap，harvest stub 不带。

`tests/cognition/test_cloud_sandbox_cjk_policy.py`：角色提示不含缺失 family 名；executeCode schema 含新解释器。
