# lca/infrastructure/skills

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `13` 个公开模块 + `78` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：14 个显式 __all__ 条目； 78 个定义符号中，55 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
—

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `ActivatedSkill`
- `DiskSkillPackageStore`
- `HttpSkillImporter`
- `OFFICECLI_SKILL_ID`
- `activated_skills_scope`
- `build_skill_exec_code`
- `ensure_bundled_skills`
- `get_activated_skills`
- `get_newly_activated`
- `register_activated`
- `resolve_skill_for_exec`
- `resolve_skill_importer`
- `resolve_skill_store`
- `skill_mount_dir`

**模块清单**:

- `lca/infrastructure/skills/activation_scope.py`
- `lca/infrastructure/skills/bundled.py`
- `lca/infrastructure/skills/disk_store.py`
- `lca/infrastructure/skills/exec_bootstrap.py`
- `lca/infrastructure/skills/factory.py`
- `lca/infrastructure/skills/format_routing.py`
- `lca/infrastructure/skills/frontmatter.py`
- `lca/infrastructure/skills/http_importer.py`
- `lca/infrastructure/skills/market_auth.py`
- `lca/infrastructure/skills/marketplace.py`
- `lca/infrastructure/skills/settings.py`
- `lca/infrastructure/skills/url_sources.py`
- `lca/infrastructure/skills/zip_security.py`
