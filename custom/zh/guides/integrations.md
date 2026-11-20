# 集成与品牌指南

给「集成与品牌」角色：incoming webhook 集成（`zerver/webhooks/`）、机器人、品牌素材（`static/images/`）。
中文翻译另见 `custom/zh/guides/translation.md`。

## 一个 incoming webhook 集成由哪些文件组成

以 `<name>`（全小写，例如 `mywebhook`）为名，照着 `zerver/webhooks/helloworld/` 做：

| 文件                                                | 内容                                            |
| --------------------------------------------------- | ----------------------------------------------- |
| `zerver/webhooks/<name>/__init__.py`                | 空文件                                          |
| `zerver/webhooks/<name>/view.py`                    | 处理函数 `api_<name>_webhook`                   |
| `zerver/webhooks/<name>/fixtures/*.json`            | 第三方真实发送的 payload，测试和截图都用        |
| `zerver/webhooks/<name>/tests.py`                   | 测试                                            |
| `zerver/webhooks/<name>/doc.md`                     | 用户配置说明，显示在 `/integrations/doc/<name>` |
| `static/images/integrations/logos/<name>.svg`       | 正方形 logo（没有 SVG 时用 `.png`）             |
| `static/images/integrations/bot_avatars/<name>.png` | 由 logo 生成的机器人头像                        |
| `static/images/integrations/<name>/001.png`         | 文档页上的示例消息截图                          |

**注册**：在 `zerver/lib/integrations.py` 的 `INCOMING_WEBHOOK_INTEGRATIONS` 里加一条，
URL `/api/v1/external/<name>` 就会指向 `zerver.webhooks.<name>.view.api_<name>_webhook`。
这个文件是 Zulip 原有文件，改动只限新增的这一条。列表必须按名字字母序
（`zerver/tests/test_integrations.py` 的 `test_sorting` 会检查）：

```python
IncomingWebhookIntegration(
    "helloworld", ["misc"], [WebhookScreenshotConfig("hello.json")], display_name="Hello World"
),
```

- 第二个参数是分类，取值是同文件 `CATEGORIES` 的键。
- `WebhookScreenshotConfig` 指定生成文档截图用的 fixture（还可设 `bot_name`、`channel`、
  `custom_headers`、`extra_params` 等）。
- `url_options`：生成集成 URL 的弹窗里给用户的选项。`WebhookUrlOption(name, label, input_type)`，
  `input_type` 为 `checkbox`（勾选才带参数）、`checkbox_enabled`（默认勾选）、`text`；
  或用预设 `WebhookUrlOption.build_preset_config(PresetUrlOption.BRANCHES)`
  （另有 `IGNORE_PRIVATE_REPOSITORIES`、`CHANNEL_MAPPING`），定义在 `zerver/lib/webhooks/common.py`。
- 改名时用 `legacy_names` 保留旧 URL。

## 写处理函数

1. **先抓 fixture**：用 Zulip 的 JSON 集成、webhook.site 之类抓第三方真实发出的 payload，
   或用第三方 API 文档里的示例。fixture 原样保存、只收测试需要的；按事件命名，snake_case，
   如 `issue_created_with_assignee.json`。抓之前在第三方用逼真的项目名、人名，尽量与
   `zerver/webhooks/fixtureless_integrations.py` 里的示例人物一致（它们会出现在文档截图里）。
2. **`view.py`** 照 `zerver/webhooks/helloworld/view.py`：
   - `@webhook_view("ServiceName")` + `@typed_endpoint`。名字按第三方自己的拼写写成驼峰、首字母大写
     （`GitHub`、`HelloWorld`），会出现在统计页。第三方用 HTTP Basic 认证时改用
     `@authenticated_rest_api_view(webhook_client_name="ServiceName")`。
   - 参数 `payload: JsonBodyPayload[WildValue]`，取值 `payload["key"].tame(check_string)`。
     payload 缺字段抛出的 `KeyError` 由服务器统一处理。
   - 发送：`check_send_webhook_message(request, user_profile, topic_name, body, event_type)`，
     返回 `json_success(request)`。URL 带 `stream` 时发到该频道，否则私信给机器人的所有者。
3. **事件类型**：
   - 事件类型放在 HTTP 头里时：`get_event_header(request, "X-Event-Key", "ServiceName")`；
     fixture 文件名写成 `<头的值>__<子类型>.json`，并在 `view.py` 里定义
     `fixture_to_headers = default_fixture_to_headers("HTTP_X_EVENT_KEY")`。
   - 不支持的事件：`raise UnsupportedWebhookEventTypeError(event_type)`（`zerver/lib/exceptions.py`）。
   - 支持事件过滤：`@webhook_view(..., all_event_types=ALL_EVENT_TYPES)`，每条消息都传
     `complete_event_type`；不该被过滤的提示类消息显式传 `complete_event_type=None`。
     事件名会写进用户的 URL，发布后不再改名；用 `git.pullrequest.created` 这样的层级名，
     用户就能写 `git.pullrequest.*`。
4. **常用工具**（都在 `zerver/lib/webhooks/common.py`）：第三方发来的测试 payload 用
   `get_setup_webhook_message` 生成标准提示；外部用户名用 `guess_zulip_user_from_external_account`
   转成 Zulip 用户的静默提及。
5. **消息内容**：用 Zulip Markdown；同一对象（同一个 bug、同一个服务）的消息放同一话题；
   第三方名称的大小写按对方品牌写。消息正文作为消息内容存储，不走翻译文件；
   返回给调用方的错误用 `JsonableError(_("..."))`，会被翻译。

## 测试

- `tests.py` 里类名 `<Name>HookTests(WebhookTestCase)`。URL 默认是
  `/api/v1/external/<目录名>?stream=<目录名>&api_key=...`，一般不用设置。
- 每种事件、每个分支一个测试：`self.check_webhook("fixture名", 期望话题, 期望正文, content_type=...)`。
- 私信给所有者：`send_and_test_private_message`；带 URL 参数：`self.url = self.build_webhook_url(topic="...")`；
  期望报错：`self.client_post(self.url, ...)` + `self.assert_json_error(result, "...")`。
- 声明了事件类型的集成，发消息时没带或带了未声明的 `complete_event_type`，`WebhookTestCase` 会让测试失败。
- 运行：`./tools/test-backend zerver/webhooks/<name>`；改了注册或图片后再跑
  `./tools/test-backend zerver.tests.test_integrations zerver.tests.test_docs`（检查排序、截图配置、logo、文档页）。

## 手动试

先在 **设置 → 机器人** 建一个 **Incoming webhook** 类型的机器人，复制它的 API key。

- 界面：`http://localhost:9991/devtools/integrations/`，选机器人、集成、fixture 后点 **Send!**。
- 命令行：

  ```bash
  ./manage.py send_webhook_fixture_message \
      --fixture=zerver/webhooks/<name>/fixtures/<fixture>.json \
      '--url=http://localhost:9991/api/v1/external/<name>?api_key=<key>&stream=<频道>' \
      --custom-headers='{"X-Event-Key": "issue_created"}'
  ```

- URL 参数：`api_key`（必填）、`stream`（频道 ID 或 URL 编码的频道名）、`topic`、
  `only_events` / `exclude_events`（如 `["issue_*"]`，支持 `*` 通配）。

## 文档页与图片

- **`doc.md`**：复制 `zerver/webhooks/basecamp/doc.md` 改。结构：一句话介绍 → `{start_tabs}` 里的编号步骤
  → `{end_tabs}` → `{!congrats.md!}` → 截图 `![](/static/images/integrations/<name>/001.png)`
  → 支持过滤时加 `{!event-filtering-additional-feature.md!}` → `### Related documentation` +
  `{!webhooks-url-specification.md!}`。
- 宏在 `templates/zerver/integrations/include/`，常用：`create-an-incoming-webhook.md`、
  `generate-webhook-url-basic.md`、`generate-webhook-url-with-branch-filtering.md`、`create-channel.md`。
  需要自己写 URL 时用 `{{ api_url }}`，不写死域名。
- 步骤写法：祈使句；动作按发生顺序（“Under **Webhooks**, click **Add Webhook**.”）；第三方界面元素加粗，
  去掉末尾标点；「找到页面」「填表并保存」各算一步；补充说明放 `!!! tip ""`，问题提醒放 `!!! warn ""`。
- **Logo**：放好 SVG 后运行 `./tools/setup/optimize-svg`（不带参数时压缩全部 logo 并重新生成全部机器人头像），
  再用 `git status static/images/integrations` 确认只有自己的文件变了。
- **截图**：`./tools/screenshots/generate-integration-docs-screenshot --integration <name>`。
  它向正在运行的开发服务器发送 fixture，会在开发库里建机器人和频道，然后截图到
  `static/images/integrations/<name>/001.png`。

## 机器人

- **Outgoing webhook 机器人**：在频道里被 @提及（`trigger` 为 `mention`）或收到私信（`direct_message`）时，
  服务器把消息 POST 到机器人配置的 URL。格式有 Zulip 格式和 Slack 兼容格式，字段见
  `zerver/openapi/zulip.yaml` 的 `/zulip-outgoing-webhook` 和 `api_docs/outgoing-webhook-payload.md`。
  对方返回 JSON：`content` 作为回复发出，`response_not_required: true` 表示不回复。超时
  `OUTGOING_WEBHOOK_TIMEOUT_SECONDS`（默认 10 秒），失败时通知机器人所有者。
  实现在 `zerver/lib/outgoing_webhook.py`、`zerver/worker/outgoing_webhooks.py`（后端的路径）。
- **生产环境访问内网服务**：服务器的出站请求经过 Smokescreen 代理，默认拒绝内网 IP；目标在内网时，
  由环境与运维在 `/etc/zulip/zulip.conf` 的 `[http_proxy]` 下加 `allow_addresses = <IP>` 并重新执行
  `zulip-puppet-apply`。开发环境不经过代理。
- **嵌入式机器人**：在服务器进程里运行，列表是 `zerver/lib/integrations.py` 的 `EMBEDDED_BOTS`，
  代码来自 `zulip_bots` 包，由 `zerver/worker/embedded_bots.py` 调度。
- 测试里对外 HTTP 请求用 `responses` 库模拟，例子：`git grep responses.add`。

## 品牌素材

替换时保持文件名和尺寸不变，先 `git grep <文件名>` 找出所有引用。

| 显示位置                   | 文件                                                  | 关联文件（归属）                                                                                          |
| -------------------------- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| 浏览器标签图标             | `static/images/favicon.svg`、`favicon.png`            | 带未读数的版本 `web/templates/favicon.svg.hbs`；`templates/zerver/base.html` 里的 `?v=4` 缓存参数（前端） |
| 组织没上传 logo 时的左上角 | `static/images/logo/zulip-org-logo.svg`               | `zerver/lib/realm_logo.py`                                                                                |
| 链接预览图                 | `static/images/logo/zulip-icon-128x128.png`           | `templates/zerver/meta_tags.html`                                                                         |
| iOS 主屏图标               | `static/images/logo/apple-touch-icon-precomposed.png` | `templates/zerver/app/index.html`                                                                         |
| 邮件顶部 logo              | `static/images/emails/email_logo.png`                 | `templates/zerver/emails/`                                                                                |
| 默认头像                   | `static/images/default-avatar.png`                    | `zerver/lib/avatar.py`                                                                                    |
| 登录等未登录页面的 logo    | `templates/zerver/portico-header.html` 里的内联 SVG   | 前端                                                                                                      |

- 换 favicon 要和前端一起改：两份 favicon、`favicon.svg.hbs` 和 `?v=` 参数同步更新，经总领协调。
- 不改代码的替换办法（服务器设置，生产环境写在 `/etc/zulip/settings.py`，由环境与运维配置）：
  `CUSTOM_LOGO_URL`（未登录页面 logo）、`DEFAULT_LOGO_URI`（组织默认 logo）、`DEFAULT_AVATAR_URI`（默认头像）。
- 组织 logo 和图标由管理员在组织设置里上传，属于数据。
