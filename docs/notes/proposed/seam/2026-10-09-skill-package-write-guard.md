# Agent Note: 助理 Home 技能包的写入必须经生产路径

Status: proposed

## Problem

已安装技能包在助理 Home 里只有一条生产路径。`create_assistant_skill` 经 `overlay.install`、`edit_assistant_skill` 经 `overlay.edit`,两者都走 staging → ADR-0067 三闸 → 记录 digest → `revision_seq++` → `revisions/` 快照 → EP。通用 `writeFile` 能触达同一批字节,但跳过其中每一步。

`run_755719d1a9d5` 在 `asst_c8b83acb1920` 上实测到这条绕行。模型用 5 次 `writeFile` 替换了 `{home}/skills/psychological-counselor/SKILL.md`,留下:

| 项 | 值 |
|---|---|
| 索引记录的 digest | `sha256:298a2c63…` |
| 磁盘 SKILL.md 实际 sha | `sha256:3be9e508…` |
| `revision_seq` | 仍为 5,无修订记录 |
| `artifact_state` | 仍为 `verified`,而内容从未过闸 |
| SKILL.md 形状 | 以 frontmatter 开头,而 `install_package` 落盘的永远只是 body |
| 其它 | 多出一个空 `resources/`;12 次 `readFile` 指向从未写出的 `references/` 路径 |

没有任何机制会发现它。`compute_digests` 只覆盖 `CONFIG_FACE_FILES` 的 8 个文件,`skills/` 不在其中。`diff_digests` 只报 declared 与 actual 都存在的名字,所以已记录的 `skills/<id>` 键被跳过而不是判失配。`DiskSkillPackageStore.get` 读 `manifest.json` 与 body,不重算哈希。于是一个包可以一边声称 `verified`、一边把未过闸的内容经 `activate_skill` 注入模型上下文。

这与 standing 文件守卫已经关掉的是同一类缺陷。`lca/infrastructure/memory/contextfiles/domain/standing_path.py` 的存在理由就是通用 `writeFile` 曾覆盖 `memory/USER.md`(`run_ab78aeb6eabf`);它按 basename 匹配 `packaged_layout().standing_files`,作用域限定在 `get_lca_home()` 或 `.lca/assistants/` 之下。`SKILL.md` 不在那个集合里,而且该谓词是 basename 形状的,技能包却是一个含多个文件的目录,所以现有谓词够不到它。

skill-creator 的「禁止」段禁的是往全局库 `~/.lca/skills/` 写,没提助理自己的 Home,而实测的写入正落在 Home。提示词层面的禁令也不是控制面:ADR-0243 D1 把 Home `skills/` 定为该助理的权威技能集,这个边界需要与 standing 文件同级的强制。

## Proposal

扩展既有 standing-write 守卫,不新造第二套机制。在 `is_standing_write_path` 旁增加「路径落在某助理 Home 的 `skills/` 包内」的谓词,挂到已经拒绝 standing 路径的同一批调用点,并把 block message 扩展为指明技能内容的生产路径是 `create_assistant_skill` / `edit_assistant_skill`。只拒写,不拒读:`readFile` 读技能包与 `read_skill_reference_once` 都不受影响。

扩展会连带逼出两个决定,需要在落地前定:

- `skills/<id>` digest 是否纳入校验集。把 `skills/` 加进 `compute_digests` 能让 Home digest 覆盖技能内容,但每个助理的 `manifest_digest` 都会变,而 `relink-skills` 本来就在写这些条目,两者的相互作用要先定。
- 检测到漂移时是否降级 `artifact_state`,而不只是拒绝写入。拒绝能阻止新漂移,不能修复已有漂移。

## Alternatives considered

**什么都不做。** 现状下任何拿到通用文件工具的模型都能改写已 verified 的包且不留痕迹,而 `activate_skill` 会把结果注入后续每一轮的上下文。代价是完整性声明长期为假,且下一次发生时无从追溯。

**在 `DiskSkillPackageStore.get` 里读时重算哈希来发现漂移。** 它只报告不阻止,而且给每次技能读取加一次全文哈希;`activate_skill` 与 `search_skill` 都在热路径上。代价是把控制面判断放进读路径,与 ADR-0243 D1「Home 是权威集」的读语义冲突。

**把 `skills/` 加进 `CONFIG_FACE_FILES`,复用既有 digest 校验。** 表面上最省,但 `catalog.get` 在 digest 失配时是自愈 reimport 而不是阻断(`handlers.py` 的 `auto_heal_on_get`),所以这条路径只会把未过闸内容采纳为新基线并记一次修订,恰好把绕行洗白。代价是完整性检查变成漂移的合法化通道。

**只改提示词,把 skill-creator 的「禁止」段扩到助理 Home。** 零代码成本,但提示词不是控制面,同一事故在 standing 文件上已经证明过它挡不住。代价是下次绕行仍然无迹可寻。

## Acceptance criteria

- 模型对 `{home}/skills/<id>/` 下任何文件的 `writeFile` 被拒绝,返回的理由指名 `create_assistant_skill` / `edit_assistant_skill`;同一路径的 `readFile` 仍然成功。
- 工作区里名为 `SKILL.md` 的文件保持可写,拒绝只发生在助理 Home 与 `get_lca_home()` 之下,与 `is_standing_write_path` 现有作用域一致。
- 一次绕行走 `create_assistant_skill` 重装后,索引 digest 与包 `content_hash` 一致、`revision_seq` 增加、`revisions/` 多一份快照、`artifact_state` 为 `verified`。
- 回归测试覆盖:直接 `writeFile` 技能包被拒;`readFile` 不被拒;工作区同名文件不被拒。

## Risks

拒绝写入会把模型的「改进技能」意图变成一次工具失败。若 block message 不够明确,模型可能反复重试或转而向用户报错,而不是改用 `create_assistant_skill`。缓解是消息里直接给出工具名,这与 standing 文件守卫现在的做法一致。

存量漂移不在本提案范围内。本次实测的那个包已经通过正规路径重装修复,但没有任何扫描确认其它 777 个 Home 是否也有历史绕行。若要清点,需要一次性对每个包重算 body 哈希并与索引比对,属于只读诊断,应作为独立动作。

`skills/<id>` digest 若最终纳入校验集,会与 `relink-skills` 写入的 digest 约定相撞:overlay 安装路径记 `_package_digest`(含 frontmatter 全文),而 `_materialize_global_skills` 与 `_copy_inherited_snapshot` 记 `sha256_digest(SKILL.md)`(剥离 frontmatter 的 body)。同一字段两种约定,纳入校验前必须先收敛到一种。
