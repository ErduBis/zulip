# 开发组织数据格式

本目录是开发环境示例组织（`zulip` 组织，`localhost:9991`）和统计图表组织（`analytics`）的中文题材数据。
生成命令读取这些文件，按真实建组织的流程生成开发数据库。**测试数据库不用这些文件**，测试里的 hamlet、
Verona 等名字不受影响。

题材：《西游记》取经团队，写成现代职场。全部内容原创，只引用公有领域文本（例如唐诗）。

## 文件

| 文件                   | 内容                                                                                                   |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| `org.yaml`             | 组织、成员、机器人、资料字段、频道文件夹、频道、用户组、草稿、定时消息、提醒词、链接规则、统计图表组织 |
| `conversations/*.yaml` | 编写好的频道对话，每个文件一个频道；文件名用拼音，如 `qujing-luxian.yaml`                              |
| `direct_messages.yaml` | 编写好的私信和群聊私信                                                                                 |
| `filler.yaml`          | 短句池：消息数量不够时随机抽取                                                                         |

## YAML 注意事项

- 消息正文、描述等较长的文字一律写成块文本 `|-`，里面可以自由使用 Markdown，不需要转义：

  ```yaml
  text: |-
    **大师兄**，前面的路我探过了。
    - 第一条
    - 第二条
  ```

- 以下写法必须加引号，否则会被解析成数字、日期或别的东西：
  - 时间：`"10:00"`（不加引号会变成整数 600）
  - 日期：`"2000-01-01"`
  - 表情名 `"+1"`、`"-1"`
  - 以 `@ * & ! % > | [ { # ? :` 或反引号开头的单行文字，例如 `"@**孙悟空** 收到"`
- 缩进用两个空格，不用 Tab；行尾不留空格。

## 键名（key）

每个成员有一个 `key`：全小写拼音，可含数字，不含空格和符号，例如 `sunwukong`。

- 它就是邮箱前缀：`sunwukong` → `sunwukong@zulip.com`。
- 其他地方引用成员时一律写 `key`（发言人、表情回应、私信成员、用户组成员、资料字段里的「用户」类型等）。
- 消息正文里提及成员时写**显示名**（`@**孙悟空**`），这是 Zulip 的语法，所以显示名在组织内不能重复。

---

## org.yaml

### realm：组织

```yaml
realm:
  name: 取经项目组（示例）
  name_alternatives: # 备选组织名，只供用户挑选，生成时不用
    - 西行事业部（示例）
  description: |- # 组织描述，Markdown，显示在登录页和组织设置里
    ……
  welcome_message_custom_text: |- # 可选：欢迎机器人私信里附加的管理员留言
    ……
```

组织默认语言固定为简体中文，子域名固定为 `zulip`，不在这里配置。

### members：成员

```yaml
members:
  - key: tangseng
    name: 唐僧
    role: owner
    replaces: desdemona
    timezone: Asia/Shanghai
    profile:
      职务: 项目负责人
      生日: "1990-04-08"
```

| 字段            | 必填 | 说明                                                                                      |
| --------------- | ---- | ----------------------------------------------------------------------------------------- |
| `key`           | 是   | 见上文「键名」                                                                            |
| `name`          | 是   | 显示名，不超过 100 个字符，组织内唯一                                                     |
| `role`          | 是   | `owner` 所有者 / `administrator` 管理员 / `moderator` 版主 / `member` 成员 / `guest` 访客 |
| `replaces`      | 否   | 代替现有开发数据里哪个测试用户的用途，见下表                                              |
| `timezone`      | 是   | IANA 时区名，例如 `Asia/Shanghai`、`America/Los_Angeles`                                  |
| `is_staff`      | 否   | 只给代替 iago 的那位设 `true`                                                             |
| `imported_stub` | 否   | `true` 表示「导入后还没登录过」的占位用户，只给代替 imported-user 的那位设                |
| `profile`       | 否   | 自定义资料字段的值，键是字段的 `name`，见下文「custom_profile_fields」                    |

`replaces` 必须恰好覆盖下面 11 个用途，每个用途一人；其余成员不写 `replaces`。

| `replaces`      | 角色   | 用途和要求                                                                                              |
| --------------- | ------ | ------------------------------------------------------------------------------------------------------- |
| `desdemona`     | 所有者 | 组织创建者，走真实的建组织流程（引导话题、欢迎私信、引导弹窗）；默认机器人的所有者                      |
| `iago`          | 管理员 | `is_staff: true`；截图工具 `/screenshot-dev` 的默认登录用户；`/emails` 里的管理员示例；有草稿和定时消息 |
| `shiva`         | 版主   |                                                                                                         |
| `hamlet`        | 成员   | 主力成员，订阅多数频道；`/emails` 里的普通成员示例                                                      |
| `cordelia`      | 成员   | 只订阅少数几个频道，用来看「订阅少」的界面                                                              |
| `othello`       | 成员   |                                                                                                         |
| `prospero`      | 成员   |                                                                                                         |
| `aaron`         | 成员   | 外发 webhook 机器人的所有者                                                                             |
| `zoe`           | 成员   | 接收 webhook 机器人的所有者                                                                             |
| `polonius`      | 访客   | 只能看到自己订阅的频道                                                                                  |
| `imported-user` | 成员   | `imported_stub: true`                                                                                   |

另外建议加两三位不写 `replaces` 的成员，用来检查界面：一位英文名同事（中英文混排），一位很长的显示名（截断）。
时区以 `Asia/Shanghai` 为主，至少两人用其他时区，用来检查时区显示。

### bots：机器人

机器人邮箱是固定的，代码和开发工具按邮箱找它们，**只改显示名**。下面 6 个都要写，不能增减：

```yaml
bots:
  - email: default-bot@zulip.com
    name: 筋斗云助手
    owner: tangseng
```

| `email`                      | 类型         | `owner` 应当是        |
| ---------------------------- | ------------ | --------------------- |
| `default-bot@zulip.com`      | 普通机器人   | 代替 desdemona 的成员 |
| `webhook-bot@zulip.com`      | 接收 webhook | 代替 zoe 的成员       |
| `outgoing-webhook@zulip.com` | 外发 webhook | 代替 aaron 的成员     |
| `commit-bot@zulip.com`       | 普通机器人   | 代替 desdemona 的成员 |
| `trac-bot@zulip.com`         | 普通机器人   | 代替 desdemona 的成员 |
| `nagios-bot@zulip.com`       | 普通机器人   | 代替 desdemona 的成员 |

欢迎机器人、通知机器人等系统机器人的名字来自翻译文件，不在这里写。

### custom_profile_fields：自定义资料字段

```yaml
custom_profile_fields:
  - name: 职务
    type: short_text
    hint: 你在团队里负责什么？
  - name: 常用兵器
    type: dropdown
    options: [金箍棒, 九齿钉耙, 降妖宝杖]
```

| `type`             | 含义                     | 成员 `profile` 里的值                      |
| ------------------ | ------------------------ | ------------------------------------------ |
| `short_text`       | 短文本                   | 字符串                                     |
| `paragraph`        | 段落，支持 Markdown      | 字符串，可用 `\|-` 多行                    |
| `dropdown`         | 下拉选择，需要 `options` | `options` 中的一项原文                     |
| `date`             | 日期                     | `"YYYY-MM-DD"`，要加引号                   |
| `url`              | 链接                     | `https://` 开头的地址                      |
| `user`             | 选择成员                 | 成员 `key` 的列表，例如 `[tangseng]`       |
| `external_account` | 外部账号，只支持 GitHub  | GitHub 用户名；字段 `name` 固定写 `GitHub` |
| `pronouns`         | 称谓                     | 字符串，例如 `他`                          |

每种 `type` 至少有一个字段，界面上每种字段都要能看到。`hint` 可选。

### channel_folders：频道文件夹

```yaml
channel_folders:
  - name: 取经事务
    description: 西行路上的正事
```

### channels：频道

**「全员」「沙盒」「Zulip」三个频道由建组织流程自动创建**（名字和描述来自翻译文件，所有成员自动订阅），
这里不要再声明。对话和私信里可以直接用这三个名字。

```yaml
channels:
  - name: 取经路线
    description: 路线规划、通关文牒和每日行程
    folder: 取经事务
    creator: tangseng
    subscribers: members
```

| 字段               | 必填 | 说明                                                                                                        |
| ------------------ | ---- | ----------------------------------------------------------------------------------------------------------- |
| `name`             | 是   | 不超过 60 个字符，组织内唯一                                                                                |
| `description`      | 是   | 不超过 1024 个字符，支持 Markdown                                                                           |
| `folder`           | 否   | `channel_folders` 里的 `name`                                                                               |
| `creator`          | 否   | 成员 `key`，不能是访客或导入占位用户；创建者自动订阅这个频道                                                |
| `private`          | 否   | `true` 为私有频道，默认 `false`                                                                             |
| `web_public`       | 否   | `true` 为「网络公开」：没有账号的人也能看（组织已开启）。和「访客」角色无关；不能和 `private` 同时为 `true` |
| `admins_only_post` | 否   | `true` 为仅管理员可以发言（公告类频道）                                                                     |
| `default_channel`  | 否   | `true` 表示以后新加入的成员自动订阅                                                                         |
| `subscribers`      | 是   | `everyone`（所有真人成员，含访客和导入占位用户）/ `members`（除访客外的所有真人成员）/ 成员 `key` 的列表    |

建议覆盖：一个私有频道（只有部分成员订阅）、一个网络公开频道、一个仅管理员发言的公告频道、
一个所有成员都订阅的闲聊频道、一个让访客也能参与的频道。频道名定稿后，`/emails` 页面的
示例代码会写死其中一个公开频道的名字，之后改名要通知后端同步修改。

### user_groups：用户组

```yaml
user_groups:
  - name: 取经团队
    description: 师徒四人
    members: [tangseng, sunwukong]
    subgroups: [] # 可选，其他用户组的 name
```

组名不能和系统组重名（所有者、管理员、版主、成员、访客、所有人等）。消息里可以用 `@*取经团队*` 提及。

### drafts：草稿

```yaml
drafts:
  - owner: sunwukong
    to: {channel: 取经路线, topic: 过火焰山}
    text: |-
      ……
```

`to` 有三种写法：`{channel: 频道名, topic: 话题名}`、`{direct: [成员 key, …]}`，或者省略（还没选收件人的草稿）。
代替 iago 的成员至少两条草稿。

### scheduled_messages：定时消息

```yaml
scheduled_messages:
  - from: sunwukong
    to: {channel: 取经路线, topic: 过火焰山}
    deliver_in_days: 30
    text: |-
      ……
```

`to` 的写法同草稿，但不能省略。`deliver_in_days` 是从生成时起多少天后发送（正整数）。
代替 iago 的成员至少一条发往频道、一条发给自己（`direct: [自己的 key]`）。

### alert_words：提醒词

```yaml
alert_words: [妖怪, 师父, 斋饭, 通关文牒]
```

一个词池，每位成员随机分到其中 4 个。至少 8 个词，最好在对话和短句里出现过。

### linkifiers：链接规则（可选）

```yaml
linkifiers:
  - pattern: "文牒#(?P<id>[0-9]+)"
    url_template: "https://example.com/wendie/{id}"
```

`pattern` 是正则表达式，`url_template` 用 `{名字}` 引用正则里的命名分组。地址只用 `example.com`，不要用真实网站。

### analytics：统计图表组织

`/stats` 页面演示用的另一个组织，只有两个用户和一个频道，消息数据是随机生成的计数。

```yaml
analytics:
  realm_name: 天庭数据司（示例）
  owner: {key: taibaijinxing, name: 太白金星} # 代替 Shylock，所有者
  guest: {key: tudigong, name: 土地公} # 代替 Bassanio，访客
  channel: 全天庭
```

这两个成员的邮箱是 `<key>@analytics.ds`。

---

## conversations/\*.yaml：频道对话

每个文件写一个频道里的若干话题。

```yaml
channel: 取经路线
topics:
  - topic: 过火焰山
    start: {days_ago: 3, time: "09:30"}
    resolved: true
    resolved_by: sunwukong
    messages:
      - from: tangseng
        text: |-
          ……
      - from: sunwukong
        after: 5m
        text: |-
          ……
        reactions:
          "+1": [tangseng]
          tada: [tangseng, zhubajie]
```

`channel` 是 `org.yaml` 里声明过的频道，或者「全员」「沙盒」「Zulip」之一。

### 话题字段

| 字段          | 必填 | 说明                                                                        |
| ------------- | ---- | --------------------------------------------------------------------------- |
| `topic`       | 是   | 话题名，不超过 60 个字符；同一频道内唯一；不要自己加 `✔`                    |
| `start`       | 是   | 第一条消息的时间，见下文「时间」                                            |
| `resolved`    | 否   | `true` 表示已解决：生成时按真实操作标记，话题名会带上 `✔`，并有一条系统通知 |
| `resolved_by` | 否   | 标记已解决的成员 `key`；省略时用最后一位发言人                              |
| `messages`    | 是   | 按顺序的发言，至少一条                                                      |

### 消息字段（频道对话、私信共用）

| 字段        | 必填 | 说明                                                                                                    |
| ----------- | ---- | ------------------------------------------------------------------------------------------------------- |
| `from`      | 是   | 发言人的成员 `key`，必须订阅了这个频道（私信里必须是私信成员之一）                                      |
| `after`     | 否   | 距上一条消息的时间，如 `30s`、`5m`、`1h30m`、`2d`；省略时为 `2m`；第一条消息忽略此项                    |
| `text`      | 是   | 消息正文，Markdown，不超过 10000 个字符                                                                 |
| `reactions` | 否   | 表情回应：键是表情名，值是回应者的成员 `key` 列表；回应者必须订阅了这个频道（私信里必须是私信成员之一） |

### 时间

`start` 有两种写法：

- `{days_ago: 3, time: "09:30"}`：生成那天往前 3 天的 09:30（北京时间）。`days_ago` 至少为 1。
  这类话题整段对话必须在当天 23:59 前结束，否则可能排到生成时刻之后。
- `{hours_ago: 2}`：生成时刻往前 2 小时。整段对话的总时长必须小于 `hours_ago`。

生成时所有消息按时间统一排序后再发送，所以不同话题可以交错进行。**最近 24 小时内的消息生成后是未读状态**，
更早的是已读；想让收件箱里有未读内容，就安排几个 `hours_ago` 或 `days_ago: 1` 的话题。
时间跨度建议在 30 天以内，大部分在最近一周。

### 正文里可以用的写法

- 提及：`@**孙悟空**`（通知对方）、`@_**孙悟空**`（不通知）、`@*取经团队*`（用户组）。名字必须存在。
- 频道和话题链接：`#**取经路线**`、`#**取经路线>过火焰山**`。必须存在；不要链接到 `resolved: true` 的话题
  （标记已解决后话题名会变，旧链接就失效了）。
- 表情：`:monkey:`、`:+1:` 等 Zulip 自带表情名，以及组织自定义表情 `:green_tick:`。
- 引用：`> 一行`，或 ` ```quote ` 块（引用古诗文注明出处）。
- 代码：行内 `` `代码` ``，或 ` ```python ` 代码块。
- 数学公式：`$$E=mc^2$$`。
- 列表、粗体、斜体、删除线、链接（只用 `example.com` 或公开文档）。
- 图片：只能引用仓库里已有的图片，用 Markdown 链接语法，地址写站内路径，例如
  `/static/images/characters/seahorse.png`，开发环境离线也能显示。
- 时间：`<time:2024-01-01T10:00:00+08:00>`。
- 投票和待办清单：消息**第一行**以 `/poll` 或 `/todo` 开头时，生成后显示为投票或待办清单控件，和在界面上
  发送的效果一样（`/poll` 有测试验证，`/todo` 走同一段代码）。但生成时不会替任何人投票或勾选，控件是空的。

  ```yaml
  text: |-
    /poll 今晚住哪？
    客栈
    寺庙
  ```

  ```yaml
  text: |-
    /todo 出发前准备
    通关文牒: 找师父盖章
    斋饭
  ```

  `/todo` 的每一行是一项任务，`: ` 后面是可选的说明。

内容建议：自然的中英文混排（API、PR、bug、KPI），长短不一，有几条很长的消息检查折叠，
有一两条只有表情。每个频道 2 到 5 个话题，每个话题 3 到 15 条消息，全部对话合计约 300 条。

## direct_messages.yaml：私信和群聊私信

```yaml
- members: [tangseng, sunwukong]
  start: {days_ago: 2, time: "21:00"}
  messages:
    - from: tangseng
      text: |-
        ……
```

`members` 两人为一对一私信，三人以上为群聊私信，只有一人为发给自己的私信（备忘）。
访客也可以参与私信。消息字段和时间写法同频道对话。建议一对一私信 4 到 6 段，群聊私信 2 到 3 段。

## filler.yaml：短句池

生成命令的 `-n` 参数是频道和私信消息的总数（`tools/rebuild-dev-database` 用 `-n400`），编写好的对话不够
这个数时，从这里随机抽取短句补足。抽取的短句会随机加上粗体、引用、表情等修饰，由能在该频道发言的成员随机
发到列出的话题里，时间随机分布在组织创建之后。随机话题和编写好的已解决话题同名时，标记解决之后的短句会发到
带 `✔` 的话题里。

```yaml
topics: # 每个频道可用的随机话题名；没列出的频道不发随机消息
  取经路线: [问路, 化缘, 天气]
sentences:
  - 收到，我这就去办。
  - |-
    今天的进度：
    - 翻过两座山
    - 化到三份斋饭
```

建议至少 150 条，长度从几个字到几行不等，内容不针对具体话题，放到哪个话题里都说得通。

## 校验

改完数据后运行下面的命令检查，它只读数据文件，不碰数据库：

```bash
./manage.py populate_dev_zh --check
```

`--data-dir <目录>` 可以检查放在别处的草稿。后端测试 `zerver.tests.test_zcustom_dev_realm` 也会检查本目录的数据。
检查的内容：

- 所有 `key`、显示名、频道名、组名、话题名不重复；所有引用都存在；
- `replaces` 恰好覆盖 11 个用途，角色符合上表；6 个机器人齐全，所有者符合上表；
- 每种资料字段类型都有；代替 iago 的成员有足够的草稿和定时消息；提醒词至少 8 个；
- 长度上限；时间写法和「不会排到生成时刻之后」的约束；
- 发言人能在对应频道发言（订阅了，公告频道还要是管理员）；回应者订阅了对应频道；
- 正文里的提及、用户组、频道和话题链接、图片路径、表情名都存在。

检查不通过时会列出每个问题所在的文件、位置和原因；格式类错误（例如时间没加引号）的说明是英文的，
位置写法如 `topics.0.start.DaysAgoStart.time`，表示第 1 个话题的 `start.time`。
