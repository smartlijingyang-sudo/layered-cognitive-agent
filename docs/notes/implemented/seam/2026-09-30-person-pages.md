# Agent Note: 一个人一份页面，索引由这些页面重写

Status: implemented

## Problem

助理记住的人如果只是 `MEMORY.md` 里的一句话，后来无法按人打开、覆盖和列出。

## Decision

`PeopleDirectory` 按上下文布局把一个人写成一页 Markdown。页是记录。每次写入后按姓名重写索引。名字必须是单个路径段。默认目录和索引名在 `lca/infrastructure/memory/contextfiles/layout.toml`。助理主目录的 `memory/contextfiles.toml` 可以覆盖这些字段，也可以覆盖常驻文件名单、回注说明、backstory 预算和投影文件名。写坏的覆盖文件被忽略，装配继续用包内默认。`person_note` 读合并后的布局再写入。写入发布 `PersonRecorded`。

## Alternatives considered

### 为什么不把人物放进 semantic.json？

人物页要能直接打开和手改。结构化记忆仍负责事实、偏好和取代链。人物页不取代那套记录。

### 为什么不把目录和名单写在 Python 里？

换一个主目录的人物目录或常驻文件顺序不需要改代码。包内配置文件是默认值。主目录里的覆盖文件只改这一家。

## Verification

`tests/infrastructure/memory/test_people_directory.py` 覆盖路径名拒绝、覆盖同一人、索引按姓名排列，以及工具写到助理主目录。`tests/infrastructure/memory/test_context_layout.py` 覆盖主目录改人物目录、常驻文件顺序、预算和投影文件名，以及写坏的覆盖文件被忽略。
