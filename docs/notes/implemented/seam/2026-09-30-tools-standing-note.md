# Agent Note: 新建助理时写入工具备忘

Status: implemented

## Problem

常驻名单里有工具备忘，新建的助理主目录里却没有这个文件。装配只读磁盘上已有的正文，模型看不到这个位置。

## Decision

`render_template` 写入 `TOOLS.md`。名字取自包内布局里那些既不是配置面文件、也不是投影文件的常驻名。模板放在 `lca/plugins/assistant/templates/TOOLS.md`，六个角色共用。文件不进入 `CONFIG_FACE_FILES`，`compute_digests` 不摘要它。改这份备忘不改变 `manifest_digest`。`MEMORY.md` 是投影文件，创建时不写。布局点名的其余常驻文件如果没有模板，创建失败。

## Alternatives considered

### 为什么不把工具备忘放进配置面摘要？

配置面摘要变化会让下一轮重新编译助理。设备别名和工具坑是活笔记，和投影一样留在磁盘上，由常驻装配重读。

### 为什么不在创建时写 MEMORY.md？

那份文件由活跃语义记录整文件替换。创建时放一份空页，会让它看起来像记录真值。配置面也明确不摘要它。

### 为什么不继续让这个文件缺席？

缺席和空白对装配是同一结果，常驻块不会出现。模型也就没有地方记下这一家环境的工具情况。

## Verification

`tests/plugins/assistant/test_templates.py` 覆盖每个角色模板都渲染 `TOOLS.md`，且不渲染 `MEMORY.md`。`tests/plugins/assistant/test_catalog.py` 覆盖创建后磁盘上有工具备忘、摘要里没有它，改写这份备忘后仍能读到助理，并且仍然没有 `MEMORY.md`。
