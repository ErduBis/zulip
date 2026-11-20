# 决策记录

每条记录：日期、决定了什么、为什么。被推翻的决定不删除，标注「已废止」并指向新决定。

## D1 基于稳定版 13.2 开发（2026-11-20）

定制分支 `custom/13.x` 从标签 `13.2` 开出。

**原因**：最终要上线使用，稳定版可以直接部署，后续 13.x 小版本合并顺畅。14.0 发布后整体升级。

## D2 开发环境：WSL2 + SSH（2026-11-20）

开发环境是 WSL2 里的 Ubuntu 24.04（装在 `D:\WSL\Ubuntu`），代码在 `/home/codyli/zulip`。
执行会话通过 Claude 桌面应用的 SSH 连接「WSL」直接运行在 WSL 里
（`127.0.0.1:2222`，仅本机、仅密钥登录）。WSL 设为开机后台启动并保持运行。

**原因**：Zulip 只支持 Linux。从 Windows 侧访问 WSL 文件太慢（全仓库搜索超过 20 秒超时，
WSL 内 `git grep` 约 0.2 秒），所以会话要跑在 WSL 里。

## D3 多会话共用一个目录，只有总领提交（2026-11-20）

执行会话共用 `/home/codyli/zulip`，按路径划分归属；所有 git 写操作由总领完成。

**原因**：用户选择共用目录。git 暂存区是共用的，
多个会话同时 `add`/`commit` 会互相把对方的改动提交进去。

## D4 自定义 API 的文档方式（2026-11-20，暂定）

自定义接口写进 `zerver/openapi/zulip.yaml`，不改 `API_FEATURE_LEVEL`，
并登记在 `CUSTOMIZATIONS.md`。

**原因**：Zulip 的测试强制要求每个接口都有 OpenAPI 文档；而 feature level 是上游的版本号，
混入我们的改动会在升级时冲突。

## D5 文档中英双版本（2026-11-20）

我们自己的文档都放在 `custom/` 下，按语言分为 `custom/zh/` 和 `custom/en/`，同名文件内容一致，
以中文版为准。AI 会话通过根目录 `CLAUDE.md` 只加载中文版开发规范。

**原因**：用户要求所有文档都有中英两版；两版都加载会重复占用会话上下文。

## D6 中文翻译流程（2026-11-20）

前端、后端只写英文源文本并标记翻译；集成与品牌负责 `locale/zh_Hans/` 的中文译文，用
`./manage.py makemessages -l zh_Hans` 和 `./manage.py compilemessages` 更新；总领合并上游时核对译文。

**原因**：`makemessages` 不加 `-l` 时会改动所有语言的文件；只改 `zh_Hans` 能让我们的改动
集中、便于升级时核对。实测 `-l zh_Hans` 只改动 `locale/zh_Hans/` 下的文件。

## D7 按角色分篇的开发指南（2026-11-20）

Zulip 开发知识写在 `custom/zh/guides/` 和 `custom/en/guides/`，每个角色一篇（测试、部署各一篇），
路径和函数名都对照 13.2 的代码核实。`docs/` 只保留 `docs/THIRDPARTY`（第三方许可证清单：`NOTICE`
引用它，`tools/check-thirdparty` 检查它）。

**原因**：执行会话需要的是贴合我们分工、与当前代码一致的要点；按角色分篇，每个会话只读自己那篇。

## D8 数据库 migration 与上游共存（2026-11-20）

- **新表**放进我们自己的 Django 应用 `zcustom/`（模型和 migration 都在里面，用外键关联 `Realm`、
  `UserProfile` 等）。第一次需要时由后端创建，在 `zproject/computed_settings.py` 的 `INSTALLED_APPS`
  加一行 `"zcustom"`，并登记到 `CUSTOMIZATIONS.md`。
- **给 Zulip 原有表加字段**（例如要接入组织设置的 `property_types` 框架）才写 `zerver` 的 migration，
  文件名用 `<编号>_custom_<说明>.py`，编号接在当时最后一个 migration 之后。
- 合并上游后 `zerver` 出现多个叶子 migration 时：
  - 我们的 migration 还没部署到任何服务器：用 `./tools/renumber-migrations` 把它们挪到上游之后。
  - 已经部署过：保持原名，用 `./manage.py makemigrations --merge zerver` 生成合并 migration，
    改名为 `<编号>_custom_merge_<上游版本>.py`。
- 部署过的 migration 永远不改名、不删除、不改内容。

**原因**：Django 按「应用 + 名字」记录执行过哪些 migration，也按依赖关系决定顺序。独立应用的
migration 不会和上游的编号冲突，新表也不用登记到 Zulip 的导出表清单（`zerver/lib/export.py` 只检查
`zerver` 等几个应用），少改原有文件；`_custom_` 前缀让合并时一眼认出哪些是我们的。改名会让服务器
把已执行的 migration 当成新的再执行一次，所以部署过的只能用合并 migration。

## D9 服务器从 git 部署（2026-11-20）

服务器从 `https://github.com/ErduBis/zulip.git` 部署：首次安装克隆 `custom/13.x`，在
`/etc/zulip/zulip.conf` 设 `git_repo_url`；之后每次升级运行
`upgrade-zulip-from-git <提交 ID>`，部署已推送到 `origin` 并在预发机验证过的提交。服务器内存选 8 GB。
步骤见 `guides/deployment.md`。

**原因**：用户选择。一条命令完成部署，服务器上的代码目录就是 git 仓库，可以直接核对版本。
前端在服务器上编译，内存不到 4.2 GiB 时升级脚本会先停服再编译，所以服务器内存留足。

## D10 提交信息中英双语（2026-11-20）

- 标题用英文，格式 `子系统: 概述.`。
- 正文先中文、后英文，内容相同：中文第一段是标题的中文版，接着是中文说明；然后是英文说明。
- 中文每行不超过 35 个字，英文每行不超过 70 个字符。
- 最后一行是署名 `Co-Authored-By: …`。

```text
i18n: Make hard-coded English strings translatable.

把写死的英文改成可翻译。

欢迎机器人的命令名等几处文字对中文用户显示为英文。……

Welcome Bot command names and a few other strings were shown in
English to Chinese users. ...

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

**原因**：用户要求提交信息中英双语。标题保持英文，是因为提交信息检查（`.gitlint`）要求冒号后以
大写英文字母开头，上游的提交标题也都是英文，合并上游时便于对照。

## D11 开发数据用独立生成命令（2026-11-20）

开发数据库由我们自己的 `./manage.py populate_dev_zh` 生成：一个自洽的中文组织「取经项目组（示例）」，
题材是《西游记》取经团队写成现代职场。数据放在 `zcustom/dev_data/`（格式见其中的 `README.md`），按真实
建组织的流程创建：组织默认语言为简体中文，有默认频道、引导消息、欢迎私信；只有所有者保留引导步骤。
统计图表组织 `analytics` 也改成中文。成员邮箱用拼音（如 `sunwukong@zulip.com`）。测试数据库仍由上游的
`populate_db --test-suite` 生成，内容不变。

**原因**：用户要求开发环境里的示例组织本身是中文组织，并补上真实建组织的流程。几千个测试依赖 hamlet、
Verona 等名字，测试库不能动；`populate_db.py` 等文件在 `zerver/lib/test_fixtures.py` 的 `IMPORTANT_FILES`
里，改了会让 `provision` 不经提示就清空、重建开发库，上游也常改这个文件。独立命令只需在原有文件里加两处
挂接点。代价是上游以后给开发数据加的新内容不会自动进入我们的组织，合并上游时要对照移植。

## D12 系统机器人用中文名（2026-11-20）

欢迎机器人、通知机器人、邮件网关等系统机器人对所有用户显示中文名。名字存在数据库里，分两条路径写入：
已有的服务器和开发库由 `zcustom/0001_localize_system_bot_names` 在 migrate 时改名；新装的服务器由
`zcustom/apps.py` 在内部组织创建、事务提交后改名。两者都只改仍是上游英文默认名的机器人，测试环境
（`TEST_SUITE`）下都不执行。前端改为按邮箱识别这些机器人。

**原因**：显示名取自数据库，`INTERNAL_BOTS` 里的名字只在创建时用一次；直接改设置会改变开发库的哈希，
`provision` 会不经提示清空开发库，而且改不到已有的服务器。测试库保留英文名，因为上游测试依赖这些名字。
代价是测试模板会多一条 `zcustom` 的 migration 记录（数据不变），改名的效果由单独的测试验证。
