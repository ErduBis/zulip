# 后端开发指南

面向后端会话：在 `DEVELOPMENT.md` 的规范之上，说明在 Zulip 13.2 后端里具体怎么做。
路径和函数名都已对照当前代码核实；动手前仍用 `git grep` 看一眼最新写法。

## 代码地图

| 位置                          | 内容                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------- |
| `zproject/urls.py`            | 路由。`v1_api_and_json_patterns` 同时挂在 `/json/` 和 `/api/v1/` 下           |
| `zerver/views/`               | 视图：解析参数、校验输入和权限，调用 action                                   |
| `zerver/actions/`             | 所有写操作：改数据库、写审计日志、发事件。`send_event_on_commit` 只在这里调用 |
| `zerver/lib/`                 | 库代码（权限检查、缓存、查询辅助等）                                          |
| `zerver/models/<模块>.py`     | 模型；新模型还要在 `zerver/models/__init__.py` 里导出                         |
| `zerver/lib/events.py`        | `/register` 初始状态（`fetch_initial_state_data`）和 `apply_event`            |
| `zerver/lib/event_types.py`   | 每种事件的 pydantic 类型；`zerver/lib/event_schema.py` 是测试用检查器         |
| `zerver/tornado/`             | 事件队列服务器（长轮询）                                                      |
| `zerver/worker/`              | RabbitMQ 队列 worker                                                          |
| `zerver/management/commands/` | 管理命令                                                                      |
| `zerver/openapi/zulip.yaml`   | REST API 和事件的 OpenAPI 文档                                                |
| `zproject/*settings*.py`      | 服务器设置（见「服务器设置」）                                                |
| `analytics/`                  | `/stats` 统计：`*Count` 表、`analytics/lib/counts.py` 的 `COUNT_STATS`        |
| `confirmation/`               | 确认链接：`create_confirmation_link`、`get_object_from_key`                   |

**照着抄的完整样板**：saved snippets 功能覆盖了模型、action、视图、事件、测试和文档——
`zerver/models/saved_snippets.py`、`zerver/actions/saved_snippets.py`、
`zerver/views/saved_snippets.py`、`zerver/tests/test_saved_snippets.py`，以及 `events.py`、
`event_types.py`、`zulip.yaml` 里的 `saved_snippets`。

## 一个请求怎么走

1. `/json/events`、`/api/v1/events` 进 Tornado；其他请求进 Django（开发环境由 `run-dev` 代理）。
2. `rest_path("foo", GET=view, POST=(view, {"allow_anonymous_user_web"}))` 把路由交给
   `rest_dispatch`（`zerver/lib/rest.py`）：`/json/` 用会话 cookie 认证，`/api/v1/` 用 HTTP Basic
   的 `email:api_key` 认证，再按 HTTP 方法分发；OPTIONS 自动处理。
3. 视图的装饰器做权限检查，`@typed_endpoint` 在最内层解析参数。
4. 视图校验通过后调用 `zerver/actions/` 里的函数完成修改，返回 `json_success(request, data={...})`。
   出错时 `raise JsonableError(_("..."))`，得到 `{"result": "error", "msg": ..., "code": ...}`。
5. 请求的附加信息（client 等）在 `RequestNotes.get_notes(request)`。

返回 HTML 的页面放在 `i18n_urls`，登录页面用 `@zulip_login_required`；Jinja2 模板在
`templates/zerver/`（前端路径，需要时向总领提出）。

## 写接口

**HTTP 方法**：GET 读取；POST 创建无唯一标识的资源；PUT 创建有唯一标识的资源；PATCH 修改；
DELETE 删除。除发消息这类操作外，重复请求不能重复改变状态。

**`@typed_endpoint`**（`zerver/lib/typed_endpoint.py`）：

```python
@require_realm_admin
@typed_endpoint
def update_widget(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    widget_id: PathOnly[int],
    name: Annotated[str, StringConstraints(max_length=60)] | None = None,
    enabled: Json[bool] | None = None,
    member_ids: Json[list[int]] | None = None,
) -> HttpResponse:
```

- 请求参数必须写在 `*` 之后（keyword-only）；没有参数的视图用 `@typed_endpoint_without_parameters`。
- 字符串直接写 `str`；整数、布尔、列表、对象都要 `Json[...]`。
- 可选参数写 `X | None = None`，客户端不能显式传 null。URL 路径变量用 `PathOnly[...]`。
- 请求名和参数名不同：`Annotated[X | None, ApiParamConfig(whence="...")]`，
  `ApiParamConfig` 放在最外层的 `Annotated` 里。
- 校验器在 `zerver/lib/typed_endpoint_validators.py`：`check_string_in_validator`、
  `check_int_in_validator`、`check_url`、`timezone_validator`、`check_color` 等；
  非空字符串用 `RequiredStringConstraint()`；复杂对象用 pydantic `BaseModel` 加 `@model_validator`。
- 所有 400 类错误都在视图里抛出，整个请求要么全部成功、要么全部失败。

**权限**：

- 装饰器：`require_realm_admin`、`require_realm_owner`、`require_non_guest_user`、
  `human_users_only`（`zerver/decorator.py`）。
- 用户组权限设置：`user_profile.has_permission("can_..._group")`，底层是
  `user_has_permission_for_group_setting`（`zerver/lib/user_groups.py`）。
- 取对象用自带权限检查的访问函数：`access_stream_by_id` / `access_stream_by_name`、
  `access_user_by_id`、`access_user_group_for_update`。视图里直接 `Stream.objects.filter`
  会被 semgrep 拦下；`Message.objects.filter` 必须带 `realm` 或 `id` 条件。
- 每个查询都限定在当前 realm 内。

**action 层**（`zerver/actions/*.py`）：

- `do_*` 函数只执行修改（假定输入已校验，出错即 500）；`check_*` 函数先校验再执行。
- 先找有没有现成的 `do_*` 函数，它已处理好缓存、审计日志和事件。
- 一个完整的 action：改数据 → `RealmAuditLog.objects.create(event_type=AuditLogEventType.XXX, ...)`
  → 构造事件 → `send_event_on_commit`。
- 事务：被视图直接调用的 action 用 `@transaction.atomic(durable=True)`；
  可能被其他 action 嵌套调用的用 `@transaction.atomic(savepoint=False)`。

**用户可见文字**：`from django.utils.translation import gettext as _`；占位符用命名字段
`_("Invalid language '{language}'").format(language=...)`；`gettext_lazy` 的字符串不要在定义处格式化。
错误类在 `zerver/lib/exceptions.py`（如 `ResourceNotFoundError`）。

## 新增设置项的检查清单

### 组织设置（realm setting）

适用于 bool / int / str / 枚举类型的字段（`property_types` 框架）：

1. `zerver/models/realms.py`：加字段，并加进 `Realm.property_types`。
   - 用户组权限设置加进 `REALM_PERMISSION_GROUP_SETTINGS`，走 `do_change_realm_permission_group_setting`。
   - 外键（如频道）不进框架，参照 `do_set_realm_stream` 单独写 action，并在 `update_realm` 里单独处理。
2. migration（先找总领确认数据模型）。
3. `zerver/views/realm.py` 的 `update_realm`：加参数 `my_setting: Json[bool] | None = None`；
   类型之外的校验写在函数开头。函数里的循环会自动调用 `do_set_realm_property`。
4. 事件：框架自动处理——`fetch_initial_state_data` 输出 `realm_<名称>`，`apply_event` 处理
   `realm`/`update`。不进框架的字段要手动加到这两处。
5. 测试：bool 字段自动被 `test_events.py` 的 `do_set_realm_property_test` 和 `test_realm.py` 的
   `do_test_realm_update_api` 覆盖；其他类型要在两处的 `test_values` 里加取值。再补上
   「这个设置确实控制了行为」的测试。
6. OpenAPI：`git grep -n require_unique_names zerver/openapi/zulip.yaml`，在同类设置出现的每个位置
   （`/register` 响应、`/events` 的 realm 事件）照样补上。
7. 前端交接（向总领说明）：`web/src/state_data.ts` 的 `realm_schema`、
   `web/src/server_events_dispatch.js`、设置界面、`web/tests/lib/example_realm.cjs`。

### 个人设置（user setting）

1. `zerver/models/users.py` 的 `UserBaseSettings`：加字段，并加进 `modern_settings` 或
   `modern_notification_settings`（合起来就是 `property_types`）。`UserProfile` 和
   `RealmUserDefault` 都继承它，migration 会改两张表。
2. 视图：`zerver/views/user_settings.py` 的 `json_change_settings` 和 `zerver/views/realm.py` 的
   `update_realm_user_settings_defaults` 都加参数。
3. action、事件自动处理：`do_change_user_setting`、`do_set_realm_user_default_setting`；
   `/register` 的 `user_settings` 和 `realm_user_settings_defaults`。
4. 测试：`test_events.py` 的 `do_change_user_settings_test`、`do_set_realm_user_default_setting_test`；
   `test_settings.py`（非 bool 必须加测试值）；`test_realm.py` 的 `do_test_realm_default_setting_update_api`。
5. OpenAPI：`git grep -n web_font_size_px zerver/openapi/zulip.yaml`，在 `/register`、`PATCH /settings`、
   `PATCH /realm/user_settings_defaults` 对应位置补上。

### 服务器设置（server setting）

属于组织政策的配置做成组织设置；服务器设置只用于服务器能力和部署配置。

- 默认值：`zproject/default_settings.py`；说明（注释形式）：`zproject/prod_settings_template.py`。
- 开发或测试环境需要不同的值：`zproject/dev_settings.py`、`zproject/test_extra_settings.py`。
- 密钥：在 `zproject/computed_settings.py` 用 `get_secret` / `get_mandatory_secret`
  （`zproject/config.py`）读取；开发环境的值在未纳入 git 的 `zproject/dev-secrets.conf`。
- 加载顺序（`zproject/configured_settings.py`）：`default_settings` → 生产环境的
  `/etc/zulip/settings.py`，或开发环境的 `prod_settings_template` + `dev_settings` +
  `custom_dev_settings`（个人覆盖，未纳入 git，测试时不加载）→ `computed_settings`。
- 读取：`from django.conf import settings`；命令行：`./scripts/get-django-setting NAME`。
- 测试：`with self.settings(NAME=...)`，只对运行时读取的设置有效。

## 实时事件

**模型**：客户端 `POST /register` 时，Django 先在 Tornado 建队列，再调用 `fetch_initial_state_data`
取状态，最后把期间进队的事件用 `apply_events` 叠加上去（`do_events_register`）。之后客户端
长轮询 `GET /events`。因此每种事件都要同时维护「初始状态」和「增量应用」两份逻辑。

**发送**：在 action 的事务里调用 `send_event_on_commit(realm, event, user_ids)`，事务提交后才发出。
接收者通常是：单个用户；全组织 `active_user_ids(realm.id)`；或消息的接收者。范围过大会泄露数据，
过小会造成界面不同步。

**新增一种事件**：

1. `zerver/lib/event_types.py`：定义 `class XxxEvent(BaseEvent)`，`type`/`op` 用 `Literal` 默认值
   （模型禁止多余字段）。
2. action 里构造该类实例并 `send_event_on_commit`。
3. `zerver/lib/events.py`：`fetch_initial_state_data` 加 `if want("xxx"):`；`apply_event` 加对应分支。
4. `zerver/lib/event_schema.py`：`check_xxx = make_checker(XxxEvent)`。
5. `zerver/tests/test_events.py`（`BaseAction` 子类）：

   ```python
   with self.verify_action() as events:
       do_xxx(...)
   check_xxx("events[0]", events[0])
   ```

   `verify_action` 比较「旧状态 + apply_events」和「重新 fetch」的结果，不一致时打印 diff。
   不改变状态的事件（如输入提示）传 `state_change_expected=False`；多个事件传 `num_events=`。
   每个 `send_event_on_commit` 调用都要有这样的测试。

6. `zulip.yaml`：在 `/events` 里写事件格式，在 `/register` 里写初始状态。
7. 前端交接（向总领说明）：`web/tests/lib/events.cjs` 的样例、`server_events_dispatch.js` 的处理、
   `web/src/server_event_types.ts` 的 `FETCH_EVENT_TYPES`；`tools/check-schemas` 会核对三方是否一致。

**改已有事件的格式**会影响已发布的客户端（如手机 App），先问总领。可行做法是加一个
`client_capabilities` 标志让新格式按需启用（参照 `zerver/lib/events.py` 里的
`bulk_message_deletion`）。Tornado 队列在重启时会持久化，改 Tornado 读取的字段时要在
`zerver/tornado/event_queue.py` 的 `from_dict` 里兼容旧格式。兼容代码标 `# TODO/compatibility: ...`。

**Tornado 代码里不查数据库和缓存**：需要的数据在 action 里查好放进事件，或交给队列 worker。

## 数据库与 migration

生成前先找总领确认数据模型。

- 流程：改模型 → `./manage.py makemigrations` → 名字不清楚就改名 → `./manage.py migrate`
  （也会清空 memcached）→ `./tools/test-migrations` 检查迁移图与模型一致。
  新表放进 `zcustom/` 应用，给原有表加字段才写 `zerver` migration（文件名带 `_custom_`）；
  与上游的编号冲突按 `DECISIONS.md` 的 D8 处理。13.2 最后一个上游 migration 是 `0815_merge`。
- 新的非空列：同时写 `default=` 和 `db_default=`。需要逐行计算的默认值分三步：可空列 →
  回填 → 改非空（样板：`0710_realm_topics_policy` → `0711_...` → `0712_...`）。
- **新表**：在 `zerver/lib/export.py` 的 `ALL_ZULIP_TABLES` 登记，并加进导出配置
  （`get_realm_config`，导入在 `zerver/lib/import_realm.py`）或 `NON_EXPORTED_TABLES`；
  否则 `test_import_export` 失败。
- **RunPython**：
  - 用 `apps.get_model("zerver", "Foo")`；不从 `zerver` 导入任何代码（semgrep 检查），需要的常量
    复制进来并注明出处。
  - `reverse_code=migrations.RunPython.noop`，`elidable=True`；
  - 可重复执行：只处理「尚未迁移」的行；读设置用 `getattr(settings, "X", 默认值)`；
  - 原始 SQL 用 `psycopg2.sql.SQL` / `Identifier` 拼表名列名。
  - 有逻辑的 RunPython 用 `MigrationsTestCase` + `use_db_models` 写测试。
- **大表**（`Message`、`UserMessage`、`Subscription`、`RealmAuditLog` 等）：
  - 索引用 `zerver/lib/migrate.py` 的 `add_index` / `remove_index`，迁移类设
    `atomic = not settings.MIGRATIONS_ADD_REMOVE_INDEXES_CONCURRENTLY`；表达式索引后加
    `RunSQL("ANALYZE zerver_<表>")`。
  - 全表更新先考虑 `do_batch_update`；手写循环时 `atomic = False`、每批一个
    `transaction.atomic()`、按 id 区间分批（有 `realm_id` 的按 realm）、遍历用 `.iterator()`。
  - 加约束或外键：`NOT VALID` + `VALIDATE CONSTRAINT`，放在 `SeparateDatabaseAndState` 里
    （样板 `0794_...`、`0791_...`）。
- 同一个原子迁移里混合 RunPython 和 `ALTER TABLE` 会报 "pending trigger events"，拆成两个文件。
- 测试库坏了用 `./tools/rebuild-test-database`。`./tools/rebuild-dev-database` 会清掉用户的开发数据，
  先问总领。

## 事务与并发

- 「先读后写」且结果依赖读到的值：在 `transaction.atomic()` 里用
  `select_for_update(no_key=True)` 锁行。`no_key` 必须显式写（semgrep 检查）；只有要删除该行或修改
  主键时才用 `no_key=False`，并写注释说明原因。
- 多行加锁用一致的顺序（`order_by`）；同时改 `Message` 和 `UserMessage` 时先锁 `Message`。
  带 join 的查询用 `of=("self",)`。持锁后事务块尽量短。
- `.save()` 一律带 `update_fields=[...]`。
- 副作用放到提交之后：`send_event_on_commit`、`queue_event_on_commit`，其他用 `transaction.on_commit`。
- 测试锁或 `durable=True` 行为才用 `ZulipTransactionTestCase`。

## 缓存

- 用带缓存的访问函数：`get_user_profile_by_id`、`get_user_by_delivery_email`、`get_realm`、
  `get_client`、`access_stream_by_id` 等。它们处理了大小写、`select_related` 和缓存。
- `@cache_with_key(key_func, timeout=...)`（`zerver/lib/cache.py`）：命中时函数体不执行。
  查询条件不同就用不同的 key 函数，不能和已有缓存共用 key。
- 失效靠 `zerver/models/*.py` 里的 `post_save.connect(flush_xxx, sender=Model)`，按 `update_fields`
  判断。新增缓存时，把影响它的字段加进对应 flush 函数。
- `QuerySet.update()`、`bulk_update()`、`bulk_create()` 不触发 `post_save`，要手动清缓存
  （例如 `bulk_flush_users`）。
- 批量取用 `bulk_cached_fetch` / `generic_bulk_cached_fetch`，不在循环里逐个取。
- 只在单个请求内缓存用 `@cache_for_current_request`（`zerver/lib/per_request_cache.py`）。
- `run-dev` 启动和 `migrate` 会清空 memcached；每个测试用独立的 key 前缀。

## 队列 worker

- 投递：`queue_event_on_commit(queue_name, event)`（`zerver/lib/queue.py`），事件必须可 JSON 序列化。
  测试里不经过 RabbitMQ，由对应 worker 直接处理。
- 偶发的后台任务优先在 `zerver/worker/deferred_work.py` 里加一个 `event["type"]` 分支，不新增进程。
- 新队列：文件名必须是 `zerver/worker/<队列名>.py`，类用 `@assign_queue("<队列名>")` 装饰，继承
  `QueueProcessingWorker`（逐条 `consume`）或 `LoopQueueProcessingWorker`（批量）。
  生产环境还要加进 `puppet/zulip/manifests/app_frontend_base.pp` 的 `$base_queues`（运维路径，告诉总领）。
- 调试：`run-dev` 自动运行所有 worker；单独运行 `./manage.py process_queue --queue=<名>`；
  清空 `./manage.py purge_queue <名>`。

## 消息、通知、Markdown、邮件

- 服务端代码发消息用 `internal_send_stream_message` / `internal_send_private_message`
  （`zerver/actions/message_send.py`）；用户发消息走 `check_message` + `do_send_messages`。
  这条路径高度优化，改动要保持批量查询，并用查询次数测试守住。
- 长期不活跃的用户被「软停用」，他们可能没有 `UserMessage` 行（回来时由 `add_missing_messages`
  补齐），代码不能假定该行一定存在。
- 通知判断逻辑在 `zerver/lib/notification_data.py`（测试 `test_notification_data.py`）；Tornado 的
  `maybe_enqueue_notifications` 把任务放进 `missedmessage_emails` / `missedmessage_mobile_notifications`
  队列，worker 发送前会重新检查已读、已删除和用户设置。
- Markdown 后端在 `zerver/lib/markdown/__init__.py`，处理器在线程里运行，不能查数据库。新语法要
  前端同步（`web/src/markdown.ts`）并在 `zerver/tests/fixtures/markdown_test_cases.json` 加用例。
  渲染出的 HTML 结构属于 API，且有 XSS 风险，改动前问总领。
- 邮件：`send_email` / `send_future_email`（`zerver/lib/send_email.py`）；收件地址用
  `user_profile.delivery_email`；批量发送走队列。模板在 `templates/zerver/emails/`（前端路径）。
  开发环境在 `http://localhost:9991/emails` 或 `var/log/email_content.log` 查看；测试里看
  `django.core.mail.outbox`。

## API 设计约定

- **兼容**：新增接口、参数、响应字段是兼容的，前提是旧请求的含义不变（新参数的默认值等于旧行为）。
  以下改动不兼容，先问总领：改变含义或类型、删除字段、给枚举加新值、在已有列表里加入新种类的对象、
  改消息渲染 HTML 的结构或 class、改推送通知内容。不兼容的改动做成可选启用：接口加默认关闭的参数，
  事件用 `client_capabilities`。
- **清晰**：从客户端实现的角度设计；名字准确对应含义；用对象而不是元组，方便以后加字段。
- `Client` 模型（来自 User-Agent）只用于统计和调试，不用来控制行为。

## OpenAPI 文档

- 每个接口在 `zerver/openapi/zulip.yaml` 里写 `operationId`、`tags`、`summary`、`description`；
  仅管理员可用的加 `x-requires-administrator: true`；每个参数写 schema 和 `example`；
  200 响应用 `allOf` + `$ref: "#/components/schemas/JsonSuccessBase"`，写全字段并附 `example`。
  描述只写当前行为。
- 自动检查：
  - `zerver/tests/test_openapi.py`：文档参数和视图的 keyword-only 参数逐一对应。
  - `test-backend` 中每个 API 响应都按 schema 校验；漏写字段报
    `Additional properties are not allowed ('x' was unexpected)`。调试用 `./tools/test-backend --rerun`。
  - `node tools/check-openapi.ts`（`tools/lint` 会运行）检查 YAML。
  - 每个 `operationId` 要在 `api_docs/include/rest-endpoints.md` 有一行（`test_openapi` 检查）。
  - `./tools/test-api` 运行 curl 示例和 `zerver/openapi/python_examples.py` 里的
    `@openapi_test_function` 示例。它占用 9981 端口，与 `/visual-test` 冲突，运行前问总领。

## 管理命令

放在 `zerver/management/commands/<名>.py`，继承 `ZulipBaseCommand`（`zerver/lib/management.py`），
用 `add_realm_args` / `get_realm` / `get_user` 处理 `--realm`、用户参数。逻辑写在 `zerver/lib/` 或
`zerver/actions/` 的函数里（这样事件和缓存都正确，也便于测试），命令本身只做参数解析。

## Python 写法要点

- 避免 N+1：`select_related` / `prefetch_related`，测试里用 `assert_database_query_count` 固定查询数。
- 不用模型对象做 dict 键或 set 元素，用 id。
- 时间：`from django.utils.timezone import now as timezone_now`；时间戳转换用
  `zerver.lib.timestamp.timestamp_to_datetime`；一律 UTC。测试里用
  `time_machine.travel(..., tick=False)`，不 mock `timezone_now`。
- 字符串格式化用 f-string 或 `.format`；判断存在用 `.exists()`；大结果集单次遍历用 `.iterator()`；
  `functools.partial` 换成 `zerver.lib.partial.partial`；用 `urlsplit`；MIME 类型用 `zerver.lib.mime_types`。
- 状态或日志文件路径经过 `zulip_path`（`zproject/computed_settings.py`）。
- 日志：`logging.warning` 写入 `var/log/errors.log`；`logging.error` / `logging.exception` 在生产环境
  会发邮件给管理员。开发服务器每个请求的日志行（终端和 `var/log/server.log`）带数据库耗时和查询次数，
  改完接口看一眼。

## 测试

写法、测试数据和常用断言见 `guides/testing.md`。
