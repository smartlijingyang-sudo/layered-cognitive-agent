# Agent Note: 一个群体一份页面，索引由这些页面重写

Status: implemented

## Problem

助理记住的群体如果只是 `MEMORY.md` 里的一句话，后来无法按群体打开、覆盖和列出。

## Decision

`GroupsDirectory` 经 `PageDirectory` 把一个群体写成一页 Markdown。人物页走同一个写入器。页是记录。每次写入后按名称重写索引。名字必须是单个路径段。空名称或空正文不写入。索引写失败时，刚落下的页面留在磁盘上。默认目录和索引名是 `layout.toml` 的 `groups_dir` 与 `groups_index`。助理主目录的 `memory/contextfiles.toml` 可以覆盖这些字段。写坏的覆盖文件被忽略。`group_note` 读合并后的布局再写入。写入发布 `GroupRecorded`。索引标题是「群体」。

## Alternatives considered

### 为什么不复制一份人物目录类？

人物和群体的路径规则、索引重写和写入失败语义是同一件事。两份类会让这些规则分叉。

### 为什么不把群体放进 semantic.json？

群体页要能直接打开和手改。结构化记忆仍负责事实、偏好和取代链。人物页已经留在 Markdown，群体页沿用那条边界。

### 为什么不做每小时的关系整理？

这条写入路径上没有调度器。`group_note` 和 `person_note` 一样，在调用时写一页并重写索引。亲近度排序仍留在 ADR-0254 的后续。

## Verification

`tests/infrastructure/memory/test_groups_directory.py` 覆盖覆盖同一群体、索引按名称排列、标题为群体，以及工具写到助理主目录。`tests/infrastructure/memory/test_context_layout.py` 覆盖主目录改群体目录，以及服务代码不写死 `memory/groups`。
