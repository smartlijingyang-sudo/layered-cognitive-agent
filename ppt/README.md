# LCA Field Note Deck

`index.html` 是一份单文件横向翻页 PPT,基于 [guizang-ppt-skill](https://github.com/op7418/guizang-ppt-skill) 的瑞士国际主义模板生成,主题色 🔵 IKB 克莱因蓝。

## 内容

13 页,13.8 分钟计划时长,主题:企业 Agent 平台的演进路线(Workbuddy → Agent API → Multi-Agent)。每页含:

- `data-slide-id` 稳定 ID(供演讲者模式备注持久化)
- `data-layout="Sxx"`(Swiss 版式登记,`S01/S03/S05/S10/S11/S13/S17/S18/S21/S22`)
- `data-animate="..."` 每页一个语义化 recipe
- 13 条 `SPEAKER_NOTES` 记录(purpose + 3-5 条 talk + transition)

## 本地预览

无需服务器,直接打开:

```bash
# macOS
open ppt/index.html

# Linux
xdg-open ppt/index.html

# 或启动一个静态服务
cd ppt && python3 -m http.server 8000
# 浏览器:http://localhost:8000/
```

## 翻页快捷键

| 键 | 行为 |
|---|---|
| `←` `→` | 翻页 |
| `滚轮` / `触屏滑动` | 翻页 |
| `ESC` | 总览(宫格缩略图) |
| `P` | 演讲者模式(弹出观众屏 + 当前/下一页预览 + 备注) |
| `B` | 静态低功耗(关 WebGL + ASCII + 入场动效) |
| `L` | 激光笔 |
| `C` | 圈选 |
| `B` / `W` | 观众屏黑屏 / 白屏 |
| `F` | 冻结观众屏 |
| `?` | 查看所有快捷键 |

## 文件组织

```
ppt/
├── README.md           # 本文件
├── .gitignore          # 排除 _preview/
├── index.html          # PPT 主文件
├── images/             # 备用槽位(S22 等需要图片的页面使用)
└── _preview/           # 本地视觉验证截图(Git 不入库)
    └── p*.png
```

## 修改流程

1. 编辑 `index.html`(HTML + 内联 CSS + `<script>SPEAKER_NOTES</script>`)
2. 浏览器刷新查看
3. 需要校验时:

```bash
node ~/.agents/skills/guizang-ppt-skill/scripts/validate-swiss-deck.mjs ppt/index.html
node ~/.agents/skills/guizang-ppt-skill/scripts/validate-presenter-mode.mjs ppt/index.html
```
