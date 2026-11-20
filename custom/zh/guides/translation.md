# 中文翻译指南

给维护 `locale/zh_Hans/` 的「集成与品牌」角色。基本三步见开发规范「中文翻译」，这里讲文件格式、
容易出错的地方和术语。

## 两个翻译文件

| 文件                                   | 覆盖的文字                                                                                       | 何时生效                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| `locale/zh_Hans/translations.json`     | 网页应用：`web/src/` 里的 `$t` / `$t_html`，`web/templates/*.hbs` 里的 `{{t}}` / `{{#tr}}`       | 刷新浏览器即可（每次加载页面时读取）        |
| `locale/zh_Hans/LC_MESSAGES/django.po` | 服务端：Python 的 `_()` / `gettext_lazy`（含 API 错误信息）、Jinja2 页面（登录注册等）、邮件模板 | `./manage.py compilemessages` 生成 `.mo` 后 |

- `translations.json`：键是英文原文（一字不差），值是中文；值为 `""` 表示未翻译，界面显示英文。
  文件由 `makemessages` 重写（键排序、两格缩进），手改时保持这个格式。
  加载路径：`zerver/lib/home.py` → `zerver/lib/i18n.py` 的 `get_language_translation_data`。
- `django.po`：`#:` 注释写着字符串来自哪个文件；长字符串分多行写，各行首尾相接。
  `.mo` 是生成文件，不进 git，每次改完 `.po` 都要重新编译。
- 英文原文有错（拼写、大小写、措辞）：找改源码的角色改英文，再重新 `makemessages`，不要动 JSON 的键。

## makemessages 做了什么

`./manage.py makemessages -l zh_Hans` 同时更新两个文件：

- 代码里新出现的字符串加进来，值为空；已有译文保持不变。
- 代码里已经没有的字符串被删掉。**英文原文改了一个字，旧译文就跟着丢了**，要对照新原文重新翻。
- `django.po` 里，gettext 会给新字符串猜一个相近的旧译文并标 `#, fuzzy`。**fuzzy 条目不会被编译进界面**：
  逐条核对、改正 `msgstr`，再删掉 `#, fuzzy` 和 `#| msgid ...` 两类注释行。

找待办：

```bash
jq -r 'to_entries[] | select(.value == "") | .key' locale/zh_Hans/translations.json   # 前端未翻译
msgattrib --untranslated --no-obsolete locale/zh_Hans/LC_MESSAGES/django.po            # 后端未翻译
msgattrib --only-fuzzy --no-obsolete locale/zh_Hans/LC_MESSAGES/django.po              # 后端待核对
```

只处理本次任务涉及的字符串（以交互方案的「文案」为准）；改完用 `git diff locale/zh_Hans/` 确认没有多余改动。

## 占位符和标签

- `{name}`、`{count}` 原样保留，可以挪位置，花括号里的词不翻译。
- `<z-link>…</z-link>`、`<z-user></z-user>` 这类 `z-` 自定义标签：标签原样保留，只翻译标签之间的文字，
  可以调整位置。不能新增标签。
- 简单标签只允许 `b`、`code`、`em`、`i`、`kbd`、`p`、`strong`，不带属性（`web/src/i18n.ts` 的
  `default_html_elements`）。
- `django.po` 里的 `%(name)s`（`python-format`）和 `{name}`（`python-brace-format`）原样保留；
  `<a href="%(url)s">` 这类 HTML 属性一个字符都不改。`compilemessages` 会检查 `%(name)s` 是否一致，
  报错时多半是占位符写错了；单独检查：`msgfmt --check-format -o /dev/null locale/zh_Hans/LC_MESSAGES/django.po`。
- `translations.json` 是 JSON：引号写 `\"`。中文里一律用全角引号“”，就不会碰到转义；
  也不要用半角单引号 `'`，它在 ICU 消息格式里是转义符。

## 复数和选择

前端用 ICU 消息格式：

```json
{
  "At least {count, plural, one {# message} other {# messages}} will be moved.": "至少会移动 {count, plural, one {# 条消息} other {# 条消息}}。"
}
```

- 保留 `{count, plural, ...}` 结构和 `one`、`other` 这些关键字，只翻译花括号里的文字；`#` 代表数字。
- 中文只用到 `other` 分支（数字为 1 时也走 `other`），所以 `other` 一定要写对；`one` 写成同样的文字即可。
  `=0 {…}` 这类精确匹配分支照常生效，要单独翻。
- `{x, select, a {…} other {…}}`：同样只翻译各分支里的文字。
- `django.po` 的复数：文件头是 `nplurals=1`，只填 `msgstr[0]`。

## 在界面上检查

- 网页应用：`/screenshot-dev --lang zh-hans`，或把测试用户的语言设成简体中文。
- 未登录页面：在路径前加语言前缀，如 `http://localhost:9991/zh-hans/login/`。
- 邮件：开发环境发出的邮件在 `http://localhost:9991/emails/` 查看。
- 看什么：译文是否截断、换行是否难看、占位符是否被替换（界面上出现 `{name}` 就是写错了）、
  按钮宽度是否被撑开。`compilemessages` 后后端译文没变化时，请总领让用户重启 `run-dev`。

## 文风

- 称呼用户用“您”；英文里的 “we” 多数不译，改写成无主语句或直接说动作（“Still no email? We can resend
  it” → “仍然没有收到邮件？点击重新发送”）。
- 句末标点跟英文走：英文有句号就用“。”，按钮、菜单项、标题、标签不加标点。英文感叹号在中文里语气偏重，
  一般改成“。”。
- 标点用全角：，。？：；“”（）。
- 中文与英文单词、数字、占位符之间加一个半角空格：“{count} 条消息”“API Key 无效”。
- 量词要配对：条消息、个话题、位用户、个频道。
- 意译优先，读起来像中文软件的说法；设置项里的 “I want …” 不直译，写成“开启……”。
- 后端发出的消息（欢迎机器人、通知等）：单个换行会被替换成空格，在中文里变成多余的空格，所以每段写成一行，段落之间空一行。
- `#**频道>话题**`、`@**用户**` 这类语法前面要有空格或换行，紧跟在全角标点（如“：”）后面不会生效。

## 术语表

以现有译文中最常用的写法为准；新译文照表写。遇到和本表不一致的旧译文，只在本次任务涉及的界面里统一，
并在汇报里列出。

| 英文                                  | 中文                       | 英文                                | 中文              |
| ------------------------------------- | -------------------------- | ----------------------------------- | ----------------- |
| channel                               | 频道                       | message                             | 消息              |
| private / public / web-public channel | 私人 / 公开 / 网络公开频道 | topic                               | 话题              |
| direct message, DM                    | 私信                       | resolved topic                      | 已解决的话题      |
| organization                          | 组织                       | user                                | 用户              |
| owner / administrator / moderator     | 所有者 / 管理员 / 版主     | member / guest                      | 成员 / 访客       |
| user group                            | 用户组                     | bot / integration                   | 机器人 / 应用整合 |
| subscribe / unsubscribe               | 订阅 / 取消订阅            | subscriber                          | 订阅者            |
| mute / muted                          | 静音 / 已静音              | follow / followed                   | 关注 / 已关注     |
| mention                               | 提及                       | alert word                          | 提醒词            |
| starred messages                      | 星标消息                   | reaction                            | 回应              |
| emoji / custom emoji                  | 表情 / 自定义表情          | drafts / scheduled messages         | 草稿 / 定时消息   |
| Inbox / Recent conversations          | 收件箱 / 近期对话          | Combined feed                       | 综合信息          |
| deactivate / reactivate               | 停用 / 重新激活            | archive / archived                  | 归档 / 已归档     |
| invalid                               | 无效                       | linkifier                           | 链接器            |
| settings / personal settings          | 设置 / 个人设置            | organization settings               | 组织设置          |
| Save changes / Discard / Cancel       | 保存修改 / 放弃 / 取消     | API key                             | API Key           |
| Views (left sidebar heading)          | 视图                       | code playground                     | 代码运行平台      |
| demo organization                     | 演示组织                   | permanent organization              | 永久组织          |
| general chat                          | 综合聊天                   | default channels: general / sandbox | 全员 / 沙盒       |

“Narrow to …” 按语境译成“搜索……”或“筛选……”。
