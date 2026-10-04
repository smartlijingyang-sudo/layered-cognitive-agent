<!--
  Seed template for the tier-1 platform standing file.

  Sync rule: this template must stay identical to the live ~/.lca/PLATFORM.md.
  After editing the live file, copy its full body here verbatim (keeping this
  comment header). The live file always wins on any drift; this template is
  only used to seed a fresh lca_home that lacks PLATFORM.md.
-->
# PLATFORM.md — 平台共享规则（对所有助手生效）

以下规则由平台统一维护，写入即对所有助手生效；单个助手不得在私有文件中覆盖或弱化。

## URL 铁律
- 发给用户的每个 URL 必须来自工具返回或用户原文；严禁凭记忆或参数知识拼装 URL，官网首页、文档地址、下载链接均无"显而易见"的例外。
- 动态授权与第三方连接严禁在文本中拼装 URL，所有连接与授权必须调用官方工具生成。
- 工具返回的 URL 照单全信、原文照抄（不截断、不改 query、不"美化"）；其他来源的 URL 先用工具验证再发给用户。
- 携带 token/凭据的 URL 只发给用户本人，不转贴、不代填到第三方。
