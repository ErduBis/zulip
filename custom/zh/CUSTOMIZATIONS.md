# 定制清单

记录我们**为实现定制功能而对 Zulip 原有代码做的修改**。新增的文件不必逐个登记，
但如果它挂接到了原有代码（例如在原有的路由表、设置、注册表里加了一行），挂接点要登记。

**用途**：升级 Zulip 版本时，逐条核对这些修改是否还需要、能否干净地重新应用。

由总领在提交时维护。

## 修改清单

| 编号 | 文件                                                                              | 改了什么                                                                              | 为什么必须改原文件                                                                                             | 相关提交                                                |
| ---- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| C1   | `zerver/lib/onboarding.py`                                                        | 欢迎机器人的命令名和列表格式可翻译；识别翻译后的命令；回复使用用户自己的语言          | 命令列表写死英文，中文用户无法使用这些命令                                                                     | i18n: Make hard-coded English strings translatable.     |
| C2   | `zerver/lib/reminders.py`                                                         | 提醒里的 `poll`、`todo list` 标记翻译                                                 | 英文词被插进已翻译的句子里                                                                                     | i18n: Make hard-coded English strings translatable.     |
| C3   | `zerver/models/users.py`                                                          | `EMOJISET_CHOICES` 的 “Plain text” 用 `gettext_lazy`，`emojiset_choices()` 转成 `str` | 设置页的表情主题选项从这里取文字；不产生 migration                                                             | i18n: Make hard-coded English strings translatable.     |
| C4   | `zerver/views/unsubscribe.py`、`templates/zerver/unsubscribe_success.html`        | 邮件类型显示名可翻译；模板改用英文键 `email_type` 判断是否为欢迎邮件                  | 显示名插在退订成功页的句子里；原模板用显示名做判断，翻译后会出错                                               | i18n: Make hard-coded English strings translatable.     |
| C5   | `web/templates/settings/playground_settings_admin.hbs`、`realm_domains_modal.hbs` | 输入框占位符示例标记翻译                                                              | 示例要换成贴近中文用户的写法                                                                                   | i18n: Make hard-coded English strings translatable.     |
| C6   | `zerver/tests/test_tutorial.py`、`zerver/tests/test_signup.py`                    | 新增中文命令、去重和退订欢迎邮件的测试                                                | 覆盖 C1、C4 的行为                                                                                             | i18n: Make hard-coded English strings translatable.     |
| C7   | `zerver/lib/home.py`、`zerver/tests/test_home.py`                                 | 生成首页初始数据前先切换到用户设置的语言；新增测试                                    | 初始数据里有服务器翻译的文字（如表情主题名），原来按浏览器 cookie 里的旧语言生成，改语言后第一次刷新会显示英文 | i18n: Build the home page state in the user's language. |

## 自定义 API 接口

| 接口 | 方法 | 用途 | 引入提交 |
| ---- | ---- | ---- | -------- |
|      |      |      |          |

## 自定义数据库 migration

| migration | 内容 | 引入提交 |
| --------- | ---- | -------- |
|           |      |          |
