# 测试指南

面向写测试、跑测试的会话（后端、前端、集成）：在 `DEVELOPMENT.md`「测试」一节之上，说明怎么选测试、
怎么写测试、失败了怎么查。命令都在 `~/zulip` 下、激活 venv 后运行；路径和函数名已对照当前代码核实。

## 共用目录下跑测试

- `tools/test-backend` 每次运行都从模板库克隆自己的数据库（名字带随机编号），多个会话可以同时跑。
- 下面这些文件所有会话共用，别的会话一跑就会覆盖：
  - `var/last_test_failure.json`：`--rerun` 读它。拿不准上次是不是自己跑的，就直接写测试名。
  - `var/.coverage`、`var/coverage/`（后端覆盖率），`var/node-coverage/`（前端覆盖率）。
  - `var/puppeteer/`：截图和登录凭据。
- `tools/test-js-with-puppeteer`、`tools/test-api`、`tools/test-help-documentation` 和 `/visual-test`
  共用 9981 测试服务器和 `zulip_test` 数据库，启动时会重置它。它们都受「同一时间只能一个会话」限制，
  开始前先问总领。
- 9991 开发服务器用的是用户的开发库 `zulip`。`tools/rebuild-dev-database` 和 `./manage.py populate_db`
  会清空它，需要时先问总领；在 `./manage.py shell`、`./manage.py dbshell` 里只做查询。
- `tools/lint` 和 `tools/run-mypy` 只检查 git 已跟踪的文件，**新建的文件会被静默跳过**。
  新文件用「Lint 和类型检查」里的命令单独检查，并在汇报里列出，由总领 `git add`。

## 后端：`tools/test-backend`

给了测试名就串行运行，不给就并行跑全套：

```bash
./tools/test-backend zerver.tests.test_users       # 模块；也可写 zerver/tests/test_users.py 或 test_users
./tools/test-backend PermissionTest                # 类名，在 zerver/、corporate/、analytics/ 的 tests 里查找
./tools/test-backend PermissionTest.test_role_setters   # 单个测试
./tools/test-backend zerver/webhooks/github        # webhook 测试要显式点名
./tools/test-backend zerver.transaction_tests.test_user_groups   # 事务测试写完整路径
```

| 选项                                                 | 用途                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------------------- |
| `-x` / `--stop`                                      | 第一个失败就停                                                            |
| `--rerun`                                            | 只跑上次失败的（见上文共用文件）                                          |
| `--coverage`                                         | 统计覆盖率；加 `--no-cov-cleanup --no-html-report` 保留数据供分析脚本读取 |
| `--parallel N`                                       | 进程数                                                                    |
| `--verbose`                                          | 打印每个测试名                                                            |
| `--reverse`                                          | 倒序运行，查测试之间的顺序依赖                                            |
| `--ban-console-output`                               | 有多余输出（`print`、未捕获的日志）就失败                                 |
| `--include-webhooks` / `--include-transaction-tests` | 跑全套时带上这两部分（默认跳过）                                          |

- 每次运行先执行 `tools/webpack --test`，并检查测试库是否需要更新（见下一节）。
- 测试里禁止联网：`requests` 等出网调用会抛
  `Outgoing network requests are not allowed in the Zulip tests`。外部 HTTP 用 `responses` 模拟
  （`@responses.activate` 加 `responses.add(...)`，`git grep responses.add` 找例子）。
- 覆盖率强制检查只在跑全套 `--coverage` 时执行：`zerver/`、`zproject/`、`analytics/`、`corporate/`、
  `confirmation/` 等目录下的所有 `.py` 都必须 100% 覆盖，例外清单是 `tools/test-backend` 里的
  `not_yet_fully_covered`。新文件同样要全覆盖。只跑一个模块时，用 `/fix-backend-coverage` 的分析脚本看缺哪些行。
- `tools/coveragerc` 不计入覆盖率的行：带 `# nocoverage` 的行、`raise AssertionError`、
  `raise NotImplementedError`、`raise UnsupportedWebhookEventTypeError`、`@abstractmethod`、`__str__`/`__repr__`。

## 测试数据库与测试数据

- 测试从模板库 `zulip_test_template` 克隆。模板由 `tools/rebuild-test-database` 生成：`migrate` →
  `populate_db --test-suite`（固定、可重复的数据）→ 导出部分表到 `zerver/tests/fixtures/messages.json`
  （生成文件，已被忽略）。
- 模板自动更新：migration 变了就自动 migrate 或重建；`zerver/lib/test_fixtures.py` 的 `IMPORTANT_FILES`
  里的文件（`populate_db.py`、`zerver/lib/generate_test_data.py` 等）变了就自动重建。测试库被弄坏时
  （例如调试 migration 之后）手动运行 `tools/rebuild-test-database`。
- 每个测试在一个事务里运行，结束时回滚；Redis 和 memcached 的键按测试加前缀。所以测试之间互不影响，
  但测试里也看不到事务提交后才发生的事（见「事件、队列和邮件」）。
- 测试用户在 `zulip` 组织里，用 `self.example_user("<名字>")` 取：

| 名字      | 角色   | 测试数据里订阅的频道                    |
| --------- | ------ | --------------------------------------- |
| hamlet    | 成员   | Verona、Denmark、core team 等           |
| cordelia  | 成员   | 只有 Verona                             |
| othello   | 成员   | Verona、Denmark、Scotland               |
| prospero  | 成员   | Verona、Denmark、Scotland、Venice       |
| aaron     | 成员   | 只有 Verona                             |
| iago      | 管理员 | Verona、Denmark、Scotland、core team 等 |
| desdemona | 所有者 | Verona、Denmark、Venice、core team 等   |
| shiva     | 版主   | Verona、Denmark、Scotland               |
| polonius  | 访客   | 只有 Verona                             |

- 机器人：`webhook_bot`、`outgoing_webhook_bot`、`default_bot`。其他组织：`self.lear_user("king")`
  （`lear`）、`self.mit_user("sipbtest")`（`zephyr`）。频道 Rome 是 web-public 频道。
  `self.nonreg_email("alice")` 是未注册的邮箱，测注册流程用。
- 管理员用 iago，普通用户用 hamlet，「其他人」用 cordelia 或 othello。测试需要的数据自己建，
  不依赖消息条数之类的现成数据。

## 写后端测试

```python
from typing_extensions import override

from zerver.lib.test_classes import ZulipTestCase


class WidgetTest(ZulipTestCase):
    @override  # mypy 要求覆盖父类方法时标注
    def setUp(self) -> None:
        super().setUp()
        self.hamlet = self.example_user("hamlet")

    def test_rename_widget(self) -> None:
        self.login("hamlet")
        result = self.client_patch("/json/widgets/1", {"name": "new"})
        self.assert_json_success(result)
        # 再从数据库读一次，确认状态真的变了

        result = self.api_patch(self.example_user("polonius"), "/api/v1/widgets/1", {"name": "x"})
        self.assert_json_error(result, "Insufficient permission")
```

- **请求**：`self.login(name)` 之后用 `client_get/post/patch/put/delete` 访问 `/json/...`；
  `api_get/post/patch/delete(user, "/api/v1/...")` 用 API key 认证，不需要登录。访问其他组织加
  `subdomain="lear"`。
- **参数**：`info` 字典按表单编码；视图里声明为 `Json[...]` 的参数要传 `orjson.dumps(value).decode()`。
- **断言结果**：`assert_json_success(result)` 返回解析后的字典；
  `assert_json_error(result, "完整错误信息", status_code=400)`；`assert_json_error_contains`；
  HTML 页面用 `assert_in_success_response(["文字"], result)`。
- **断言状态**：请求之后 `obj.refresh_from_db()` 或重新查询。
- **准备数据**：`make_stream`、`subscribe`、`unsubscribe`、`send_stream_message`（返回消息 ID）、
  `send_personal_message`、`send_group_direct_message`、`set_user_role`；更多时候直接调用 `zerver/actions/`
  里的 `do_*` 函数，和真实代码走同一条路径。`create_test_bot` 会把客户端登录成传入的用户。
- **其他**：`assert_length(items, n)`、`get_last_message()`；`zerver/lib/test_helpers.py` 里的
  `most_recent_message(user)`、`get_subscription(stream_name, user)`。
- 成功和失败用同一份准备代码，放在同一个测试里依次断言，免得失败用例因为别的原因失败而「碰巧通过」。
- **OpenAPI 校验**：测试客户端（`zerver/lib/test_classes.py` 的 `ZulipClientHandler`）把每个 `/json/`、
  `/api/v1/` 请求和响应与 `zerver/openapi/zulip.yaml` 对照：已文档化接口的响应不符合文档就失败；
  返回 2xx 的请求带了文档里没有的参数也失败，故意测未文档化行为时传 `intentionally_undocumented=True`。
  改接口时先改 `zulip.yaml`，再跑 `zerver.tests.test_openapi`。

## 事件、队列和邮件

- `send_event_on_commit`、`queue_event_on_commit` 和其他 `transaction.on_commit` 回调要等事务提交才执行，
  而测试的外层事务从不提交。验证它们：
  - 实时事件：`with self.capture_send_event_calls(expected_num_events=1) as events:`，再检查
    `events[0]["event"]` 和 `events[0]["users"]`。
  - 其他回调：`with self.captureOnCommitCallbacks(execute=True):`。
- 测试里没有 RabbitMQ：队列事件经过一次 JSON 往返后由对应 worker 同步处理（`zerver/lib/queue.py`）。
  只想断言发了什么，用 `test_helpers.mock_queue_publish("<模块>.queue_event_on_commit")`，它顺带检查事件能
  JSON 序列化。
- 邮件：测试用 Django 内存后端，发出的邮件在 `django.core.mail.outbox`；确认链接用
  `self.get_confirmation_url_from_outbox(email)`。
- 新增或修改事件格式：
  1. `zerver/lib/event_types.py` 定义类型，`zerver/lib/event_schema.py` 加 `check_*` 检查器；
  2. `zerver/tests/test_events.py` 里 `with self.verify_action() as events:` 执行动作，再
     `check_*("events[0]", events[0])`；`verify_action` 同时验证 `apply_events` 的结果和重新拉取的状态一致；
  3. 前端：`web/tests/lib/events.cjs` 加示例事件，`web/tests/dispatch.test.cjs` 测分发；
  4. `./tools/check-schemas` 检查 Python 类型、OpenAPI 和前端示例三者一致。
- 新组织设置加进 `Realm.property_types` 后，`test_events.py` 的 `do_set_realm_property_test` 和
  `test_realm.py` 的 `do_test_realm_update_api` 会自动覆盖；非布尔类型要在两处的 `test_values` 里加测试值。

## Mock、设置、时间和性能

- `mock.patch` 打在**使用处**：模块 `b` 里 `from a import f` 后调用 `f`，就 patch `"b.f"`。
- 断言 mock 用 `assert_called_once_with` 等 `assert_` 开头的方法（lint 检查；`m.called_once_with(...)`
  这种写法什么也不验证）。
- 服务器设置：`with self.settings(NAME=value):` 或 `@override_settings(...)`，只对运行时读取的设置有效。
  组织设置用 `do_set_realm_property` 等 action 修改。
- 测试默认关闭限流；测限流用 `test_helpers.ratelimit_rule(range_seconds, num_requests, domain=...)`。
- 时间：`with time_machine.travel(dt, tick=False):`。
- 日志：`with self.assertLogs("<logger>", level="WARNING") as m:`，断言方式见 `.claude/rules/testing.md`。
- 查询数：`with self.assert_database_query_count(n):`；要看具体 SQL 用 `test_helpers.queries_captured()`；
  缓存访问次数用 `assert_memcached_count(n)`。数字变了，先弄清多出的查询是否必要，再改数字。
- 文件：临时文件放 `settings.TEST_WORKER_DIR` 下（每个测试进程独有，运行结束自动删除）；
  `LOCAL_UPLOADS_DIR` 在每个测试的 `tearDown` 里清空。
- 需要真实提交事务的测试（`select_for_update` 竞争、`transaction.atomic(durable=True)`）继承
  `ZulipTransactionTestCase`，放在 `zerver/transaction_tests/`；测试结束时各表的行必须和开始时完全一致。
- 测试辅助方法返回响应时，类型写 `"TestHttpResponse"`：
  `if TYPE_CHECKING: from django.test.client import _MonkeyPatchedWSGIResponse as TestHttpResponse`。
- LDAP：`self.init_default_ldap_database()` 配合 `override_settings(AUTH_LDAP_...)`，参照
  `zerver/tests/test_auth_backends.py`。

## Webhook 集成测试

- 测试写在 `zerver/webhooks/<名字>/tests.py`，继承 `WebhookTestCase`；载荷放
  `zerver/webhooks/<名字>/fixtures/<fixture>.json`，用真实服务发出的数据。
- 默认以 `webhook-bot@zulip.com` 身份发到与目录同名的频道；URL 格式不同时设 `URL_TEMPLATE`。
- 主要断言：`self.check_webhook("<fixture>", expected_topic_name, expected_message, content_type=...)`，
  额外请求头作为关键字参数传入（如 `HTTP_X_GITHUB_EVENT="push"`）。
- 视图用 `@webhook_view(..., all_event_types=ALL_EVENT_TYPES)` 声明事件类型时，每次调用
  `check_send_webhook_message` 都必须传 `complete_event_type`，且值在列表里，否则测试报错。
- 不支持的事件 `raise UnsupportedWebhookEventTypeError`（不计入覆盖率）。

## 前端：`tools/test-js-with-node`

```bash
./tools/test-js-with-node compose            # web/tests/compose.test.cjs；可以写多个
./tools/test-js-with-node --coverage         # 串行运行；只有跑全套才做覆盖率强制检查
```

- `web/src/` 下每个文件都要 100% 行覆盖，例外清单是 `tools/test-js-with-node` 的 `EXEMPT_FILES`；
  新文件同样要全覆盖。报告在 `var/node-coverage/`，排查方法见 `/debug-node-coverage`。
- `web/tests/*.test.cjs` 自动被发现；`web/src/foo.ts` 的测试写在 `web/tests/foo.test.cjs`。入门读
  `web/tests/example1.test.cjs` 到 `example8.test.cjs`，zjquery 用法读 `web/tests/zjquery.test.cjs`。

```js
"use strict";

const assert = require("node:assert/strict");

const {mock_esm, zrequire} = require("./lib/namespace.cjs");
const {run_test, noop} = require("./lib/test.cjs");
const {$} = require("./lib/zjquery.cjs");

// mock_esm 必须写在 zrequire 之前：它在模块加载时替换依赖
const channel = mock_esm("../src/channel");

const foo = zrequire("foo");

run_test("foo sends a request", ({override}) => {
    override(channel, "get", (opts) => {
        assert.equal(opts.url, "/json/foo");
    });
    foo.load();
});
```

- `zrequire("name")` 加载真实代码（相对 `web/src/`）；`mock_esm("../src/x", {fn: noop})` 把整个模块换成假对象
  （相对 `web/tests/`）。提示「You asked to mock … but we never saw it during compilation」表示被测代码没用到
  这个模块，删掉这个 mock。
- `run_test` 回调拿到的工具，测试结束自动还原：
  - `override(obj, "prop", value)`：替换属性或函数；替换的函数没被调用会报 `never got invoked!`，
    确实可能不调用时传 `{unused: false}`。`disallow(obj, "prop")`：一旦被调用就失败。
  - `override_rewire(mod, "fn", value)`：替换同一模块内部调用的函数。源码里要写成 `export let fn = ...`
    并导出 `rewire_fn`（参照 `web/src/activity.ts` 的 `rewire_send_presence_to_server`）。`disallow_rewire` 同理。
  - `mock_template("path.hbs", false, (data) => …)`：断言传给模板的数据；第二个参数为 `true` 时真的渲染，
    回调还会收到 `html`。
- DOM：jQuery 由 zjquery 模拟，`$("#id")` 返回假元素；`$el.set_find_results(selector, $result)` 设定 `.find()`
  的结果；`$el.get_on_handler("click")` 取出事件处理函数直接调用。报错「You must create a stub for …」或
  「You need to call … set_find_results」时按提示补上。
- blueslip：被测代码调用 `blueslip.warn`/`blueslip.error` 前，测试要先 `blueslip.expect("error", "完整信息")`，
  否则测试失败（`web/tests/lib/zblueslip.cjs`）。
- 造数据：`web/tests/lib/example_user.cjs` 的 `make_user`、`example_stream.cjs` 的 `make_stream`、
  `example_realm.cjs` 的 `make_realm`；当前组织和用户用 `state_data` 的 `set_realm`、`set_current_user` 设置。
- 计时器是假的：`namespace.cjs` 导出的 `clock`，用 `clock.tick(ms)` 推进、`clock.setSystemTime(...)`
  设当前时间；时区固定为 UTC。
- 计数桩：`web/tests/lib/stub.cjs` 的 `make_stub()`（`stub.f`、`stub.num_calls`、`stub.get_args(...)`）。

## 浏览器端到端测试（Puppeteer）

- 测试在 `web/e2e-tests/*.test.ts`，辅助函数在 `web/e2e-tests/lib/common.ts`；运行
  `./tools/test-js-with-puppeteer compose`（按前缀匹配文件名）。受 9981 服务器「同一时间一个会话」限制。
- 能用 node 测试覆盖的用 node 测试；登录跳转、键盘快捷键、复制粘贴这类依赖真实浏览器的行为写端到端测试。
- 每个操作前等界面就绪：`page.waitForSelector(sel, {visible: true})`（不加 `visible`，元素只要在 DOM 里就算等到了）。
- 失败时自动截图到 `var/puppeteer/*.png`；`--loop N` 重复运行 N 遍，检查是否偶发失败。
- 测试数据和后端测试相同（`populate_db --test-suite`），默认登录 desdemona。写法细节见 `/visual-test`。

## Lint 和类型检查

- 只跑部分检查：`./tools/lint --only=mypy,ruff <文件> </dev/null`，或 `--skip=...`、`--groups=backend,frontend`；
  `--list` 列出全部检查项，`--fix` 自动修复格式类问题。
- 单独检查未被 git 跟踪的新文件：

```bash
mypy <file.py>
ruff check <file.py> && ruff format --check <file.py>
node_modules/.bin/eslint <file>
node_modules/.bin/prettier --check <file>
node_modules/.bin/stylelint <file.css>
./tools/run-tsc        # 按 tsconfig.json 检查整个前端，包含未跟踪的文件
```

- mypy 是严格模式（配置在 `pyproject.toml`）：覆盖父类方法加 `@override`（`from typing_extensions import override`）；
  `# type: ignore` 必须写成 `# type: ignore[code] # 原因`；`QuerySet` 带上模型类型，如 `QuerySet[UserProfile]`。
- `tools/linter_lib/custom_check.py` 里和测试相关的规则：用 `assert_length` 代替 `assertEqual(len(...), n)`；
  mock 断言用 `assert_` 开头的方法；`transaction.atomic` 显式传 `durable=True` 或 `savepoint=False`；
  前端测试用 `assert.ok(...)`；测试里的字符串不标记翻译。
- 专项检查：`./tools/check-schemas`（事件格式）、`./tools/test-migrations`（migration 与模型一致）、
  `./tools/check-templates`（模板标签和缩进）、`./tools/check-capitalization` 和
  `./tools/check-frontend-i18n`（界面文字）。

## 开发环境里的便利

- 开发库（9991）里是我们自己生成的中文示例组织，成员和测试库不同：所有者唐僧 `tangseng@zulip.com`、
  管理员孙悟空 `sunwukong@zulip.com`、普通成员猪八戒 `zhubajie@zulip.com`、访客观音菩萨
  `guanyin@zulip.com`，完整名单见 `zcustom/dev_data/org.yaml`。上面表格里的 hamlet 等用户只在测试库里。
  开发库由 `./manage.py populate_dev_zh` 生成（`tools/rebuild-dev-database` 调用它，会清空开发库，先问总领）；
  改了 `zcustom/dev_data/` 的数据后用 `./manage.py populate_dev_zh --check` 校验。
- `./manage.py print_initial_password sunwukong@zulip.com` 打印开发组织成员的初始密码和 API key，可以用
  `curl -u sunwukong@zulip.com:<API key> http://localhost:9991/api/v1/users/me` 调接口（只发 GET，开发数据保持不变）。
- `http://localhost:9991/devtools/` 列出开发用页面：`/emails`（开发环境不真发邮件，「发出」的邮件都在这里）、
  `/devtools/buttons`、`/devtools/banners`、`/devtools/inputs`（组件样式）、`/errors/404`、`/errors/5xx`。
- 改动自动生效：Python 改动后 run-dev 自动重启；`web/src/`、`web/templates/` 改动后浏览器自动刷新；
  `templates/` 下的 Jinja2 模板要刷新页面。开发环境里的前端异常以醒目的错误框显示在页面上，截图里能看到。
