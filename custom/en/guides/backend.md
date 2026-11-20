# Backend development guide

For the backend session: on top of the rules in `DEVELOPMENT.md`, how things are actually done in
the Zulip 13.2 backend. Every path and function name has been checked against the current code;
still `git grep` for the latest pattern before you start.

## Code map

| Location                      | Contents                                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| `zproject/urls.py`            | Routes. `v1_api_and_json_patterns` is mounted under both `/json/` and `/api/v1/`                 |
| `zerver/views/`               | Views: parse parameters, validate input and permissions, call an action                          |
| `zerver/actions/`             | All writes: database changes, audit log, events. `send_event_on_commit` is only called from here |
| `zerver/lib/`                 | Library code (permission checks, caching, query helpers, etc.)                                   |
| `zerver/models/<module>.py`   | Models; a new model must also be exported from `zerver/models/__init__.py`                       |
| `zerver/lib/events.py`        | `/register` initial state (`fetch_initial_state_data`) and `apply_event`                         |
| `zerver/lib/event_types.py`   | A pydantic type for each event; `zerver/lib/event_schema.py` holds the test checkers             |
| `zerver/tornado/`             | Event queue server (long-polling)                                                                |
| `zerver/worker/`              | RabbitMQ queue workers                                                                           |
| `zerver/management/commands/` | Management commands                                                                              |
| `zerver/openapi/zulip.yaml`   | OpenAPI documentation for the REST API and events                                                |
| `zproject/*settings*.py`      | Server settings (see "Server settings")                                                          |
| `analytics/`                  | `/stats` statistics: the `*Count` tables, `COUNT_STATS` in `analytics/lib/counts.py`             |
| `confirmation/`               | Confirmation links: `create_confirmation_link`, `get_object_from_key`                            |

**A complete template to copy**: the saved snippets feature covers model, actions, views, events,
tests and docs — `zerver/models/saved_snippets.py`, `zerver/actions/saved_snippets.py`,
`zerver/views/saved_snippets.py`, `zerver/tests/test_saved_snippets.py`, plus `saved_snippets` in
`events.py`, `event_types.py` and `zulip.yaml`.

## How a request flows

1. `/json/events` and `/api/v1/events` go to Tornado; everything else goes to Django (proxied by
   `run-dev` in development).
2. `rest_path("foo", GET=view, POST=(view, {"allow_anonymous_user_web"}))` hands the route to
   `rest_dispatch` (`zerver/lib/rest.py`): `/json/` authenticates with the session cookie,
   `/api/v1/` with HTTP Basic `email:api_key`, then dispatches on the HTTP method; OPTIONS is
   handled automatically.
3. The view's decorators check permissions; `@typed_endpoint`, innermost, parses parameters.
4. After validation the view calls a function in `zerver/actions/` to make the change and returns
   `json_success(request, data={...})`. On error, `raise JsonableError(_("..."))`, which produces
   `{"result": "error", "msg": ..., "code": ...}`.
5. Extra per-request data (client, etc.) lives in `RequestNotes.get_notes(request)`.

HTML pages go in `i18n_urls`; logged-in pages use `@zulip_login_required`; Jinja2 templates are in
`templates/zerver/` (a frontend path; raise it with the lead when needed).

## Writing endpoints

**HTTP methods**: GET reads; POST creates a resource without a unique identifier; PUT creates a
resource with a unique identifier; PATCH modifies; DELETE deletes. Apart from operations like
sending a message, repeating a request must not change state again.

**`@typed_endpoint`** (`zerver/lib/typed_endpoint.py`):

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

- Request parameters must come after `*` (keyword-only); views with no parameters use
  `@typed_endpoint_without_parameters`.
- Strings are plain `str`; integers, booleans, lists and objects need `Json[...]`.
- Optional parameters are `X | None = None`; clients cannot explicitly send null. URL path
  variables use `PathOnly[...]`.
- Request name differs from parameter name: `Annotated[X | None, ApiParamConfig(whence="...")]`,
  with `ApiParamConfig` in the outermost `Annotated`.
- Validators are in `zerver/lib/typed_endpoint_validators.py`: `check_string_in_validator`,
  `check_int_in_validator`, `check_url`, `timezone_validator`, `check_color`, etc.; non-empty
  strings use `RequiredStringConstraint()`; complex objects use a pydantic `BaseModel` with
  `@model_validator`.
- All 400-type errors are raised in the view, so the whole request succeeds or fails as a unit.

**Permissions**:

- Decorators: `require_realm_admin`, `require_realm_owner`, `require_non_guest_user`,
  `human_users_only` (`zerver/decorator.py`).
- User-group permission settings: `user_profile.has_permission("can_..._group")`, built on
  `user_has_permission_for_group_setting` (`zerver/lib/user_groups.py`).
- Fetch objects with access functions that check permissions: `access_stream_by_id` /
  `access_stream_by_name`, `access_user_by_id`, `access_user_group_for_update`. A direct
  `Stream.objects.filter` in a view is blocked by semgrep; `Message.objects.filter` must have a
  `realm` or `id` condition.
- Scope every query to the current realm.

**Action layer** (`zerver/actions/*.py`):

- `do_*` functions only perform the change (input is assumed valid; errors mean 500); `check_*`
  functions validate first, then perform it.
- Look for an existing `do_*` function first; it already handles caching, audit log and events.
- A complete action: change data → `RealmAuditLog.objects.create(event_type=AuditLogEventType.XXX, ...)`
  → build the event → `send_event_on_commit`.
- Transactions: actions called directly from views use `@transaction.atomic(durable=True)`; actions
  that may be nested inside other actions use `@transaction.atomic(savepoint=False)`.

**User-visible text**: `from django.utils.translation import gettext as _`; use named placeholders,
`_("Invalid language '{language}'").format(language=...)`; never format a `gettext_lazy` string at
its definition. Error classes are in `zerver/lib/exceptions.py` (e.g., `ResourceNotFoundError`).

## Checklists for adding a setting

### Organization setting (realm setting)

For bool / int / str / enum fields (the `property_types` framework):

1. `zerver/models/realms.py`: add the field and add it to `Realm.property_types`.
   - User-group permission settings go in `REALM_PERMISSION_GROUP_SETTINGS` and use
     `do_change_realm_permission_group_setting`.
   - Foreign keys (e.g., a channel) stay outside the framework: write a dedicated action modeled on
     `do_set_realm_stream` and handle it separately in `update_realm`.
2. Migration (confirm the data model with the lead first).
3. `update_realm` in `zerver/views/realm.py`: add the parameter
   `my_setting: Json[bool] | None = None`; validation beyond types goes at the top of the function.
   The loop in the function calls `do_set_realm_property` automatically.
4. Events: handled by the framework — `fetch_initial_state_data` emits `realm_<name>`, `apply_event`
   handles `realm`/`update`. Fields outside the framework must be added to both by hand.
5. Tests: bool fields are covered automatically by `do_set_realm_property_test` in
   `test_events.py` and `do_test_realm_update_api` in `test_realm.py`; other types need values
   added to `test_values` in both. Then add tests that the setting actually controls the behavior.
6. OpenAPI: `git grep -n require_unique_names zerver/openapi/zulip.yaml` and add the new setting at
   every place a similar setting appears (`/register` response, the realm events in `/events`).
7. Frontend handoff (tell the lead): `realm_schema` in `web/src/state_data.ts`,
   `web/src/server_events_dispatch.js`, the settings UI, `web/tests/lib/example_realm.cjs`.

### Personal setting (user setting)

1. `UserBaseSettings` in `zerver/models/users.py`: add the field and add it to `modern_settings` or
   `modern_notification_settings` (together they form `property_types`). Both `UserProfile` and
   `RealmUserDefault` inherit from it, so the migration changes two tables.
2. Views: add the parameter to both `json_change_settings` in `zerver/views/user_settings.py` and
   `update_realm_user_settings_defaults` in `zerver/views/realm.py`.
3. Actions and events are automatic: `do_change_user_setting`, `do_set_realm_user_default_setting`;
   `user_settings` and `realm_user_settings_defaults` in `/register`.
4. Tests: `do_change_user_settings_test` and `do_set_realm_user_default_setting_test` in
   `test_events.py`; `test_settings.py` (non-bool settings must have test values);
   `do_test_realm_default_setting_update_api` in `test_realm.py`.
5. OpenAPI: `git grep -n web_font_size_px zerver/openapi/zulip.yaml` and add it at the matching
   places in `/register`, `PATCH /settings` and `PATCH /realm/user_settings_defaults`.

### Server setting

Configuration that is a matter of organization policy becomes an organization setting; server
settings are for server capabilities and deployment configuration.

- Default: `zproject/default_settings.py`; documentation (as comments):
  `zproject/prod_settings_template.py`.
- Different value in development or tests: `zproject/dev_settings.py`,
  `zproject/test_extra_settings.py`.
- Secrets: read in `zproject/computed_settings.py` with `get_secret` / `get_mandatory_secret`
  (`zproject/config.py`); development values live in the untracked `zproject/dev-secrets.conf`.
- Load order (`zproject/configured_settings.py`): `default_settings` → `/etc/zulip/settings.py` in
  production, or `prod_settings_template` + `dev_settings` + `custom_dev_settings` in development
  (personal overrides, untracked, not loaded in tests) → `computed_settings`.
- Reading: `from django.conf import settings`; from the shell: `./scripts/get-django-setting NAME`.
- Tests: `with self.settings(NAME=...)`, which only works for settings read at runtime.

## Real-time events

**Model**: on `POST /register`, Django first creates a queue in Tornado, then calls
`fetch_initial_state_data`, then applies the events queued meanwhile with `apply_events`
(`do_events_register`). The client then long-polls `GET /events`. So every event type needs both
"initial state" and "incremental apply" logic.

**Sending**: inside the action's transaction, call `send_event_on_commit(realm, event, user_ids)`;
it is sent only after the transaction commits. Recipients are usually: a single user; the whole
organization, `active_user_ids(realm.id)`; or the message's recipients. Too wide leaks data; too
narrow causes UI sync bugs.

**Adding an event type**:

1. `zerver/lib/event_types.py`: define `class XxxEvent(BaseEvent)` with `Literal` defaults for
   `type`/`op` (the model forbids extra fields).
2. In the action, build an instance and `send_event_on_commit` it.
3. `zerver/lib/events.py`: add `if want("xxx"):` to `fetch_initial_state_data` and a matching
   branch to `apply_event`.
4. `zerver/lib/event_schema.py`: `check_xxx = make_checker(XxxEvent)`.
5. `zerver/tests/test_events.py` (a `BaseAction` subclass):

   ```python
   with self.verify_action() as events:
       do_xxx(...)
   check_xxx("events[0]", events[0])
   ```

   `verify_action` compares "old state + apply_events" against "a fresh fetch" and prints a diff
   when they differ. Events that don't change state (e.g., typing) pass
   `state_change_expected=False`; multiple events pass `num_events=`. Every
   `send_event_on_commit` call needs a test like this.

6. `zulip.yaml`: document the event format in `/events` and the initial state in `/register`.
7. Frontend handoff (tell the lead): the sample in `web/tests/lib/events.cjs`, handling in
   `server_events_dispatch.js`, `FETCH_EVENT_TYPES` in `web/src/server_event_types.ts`;
   `tools/check-schemas` verifies the three agree.

**Changing an existing event's format** affects released clients (e.g., the mobile app); ask the
lead first. The workable approach is a `client_capabilities` flag that enables the new format on
request (see `bulk_message_deletion` in `zerver/lib/events.py`). Tornado queues persist across
restarts, so when changing fields Tornado reads, accept the old format in `from_dict` in
`zerver/tornado/event_queue.py`. Mark compatibility code with `# TODO/compatibility: ...`.

**Tornado code does no database or cache queries**: query the data in the action and put it in the
event, or hand the work to a queue worker.

## Database and migrations

Confirm the data model with the lead before generating anything.

- Flow: change the model → `./manage.py makemigrations` → rename if the name is unclear →
  `./manage.py migrate` (also flushes memcached) → `./tools/test-migrations` checks the migration
  graph matches the models. New tables go in the `zcustom/`
  app; write a `zerver` migration (with `_custom_` in the file name) only to add fields to existing
  tables; handle number conflicts with upstream per D8 in `DECISIONS.md`. The last upstream
  migration in 13.2 is `0815_merge`.
- New non-null column: set both `default=` and `db_default=`. Per-row computed defaults take three
  steps: nullable column → backfill → make non-null (template: `0710_realm_topics_policy` →
  `0711_...` → `0712_...`).
- **New table**: register it in `ALL_ZULIP_TABLES` in `zerver/lib/export.py`, and add it to the
  export config (`get_realm_config`, import in `zerver/lib/import_realm.py`) or to
  `NON_EXPORTED_TABLES`; otherwise `test_import_export` fails.
- **RunPython**:
  - Use `apps.get_model("zerver", "Foo")`; import no code from `zerver` (semgrep checks); copy
    needed constants in, noting their source.
  - `reverse_code=migrations.RunPython.noop`, `elidable=True`;
  - Re-runnable: only touch rows "not yet migrated"; read settings with
    `getattr(settings, "X", default)`;
  - Build table/column names in raw SQL with `psycopg2.sql.SQL` / `Identifier`.
  - RunPython with real logic gets a test using `MigrationsTestCase` + `use_db_models`.
- **Large tables** (`Message`, `UserMessage`, `Subscription`, `RealmAuditLog`, etc.):
  - Indexes use `add_index` / `remove_index` from `zerver/lib/migrate.py`, with
    `atomic = not settings.MIGRATIONS_ADD_REMOVE_INDEXES_CONCURRENTLY` on the migration class; add
    `RunSQL("ANALYZE zerver_<table>")` after an expression index.
  - Whole-table updates: try `do_batch_update` first; hand-written loops use `atomic = False`, one
    `transaction.atomic()` per batch, batches by id range (per realm when there is `realm_id`), and
    `.iterator()`.
  - Adding constraints or foreign keys: `NOT VALID` + `VALIDATE CONSTRAINT` inside
    `SeparateDatabaseAndState` (templates `0794_...`, `0791_...`).
- Mixing RunPython and `ALTER TABLE` in one atomic migration fails with "pending trigger events";
  split it into two files.
- A broken test database: `./tools/rebuild-test-database`. `./tools/rebuild-dev-database` wipes
  the user's development data; ask the lead first.

## Transactions and concurrency

- "Read then write" where the result depends on what was read: lock the rows with
  `select_for_update(no_key=True)` inside `transaction.atomic()`. `no_key` must be explicit
  (semgrep checks); use `no_key=False` only when deleting the row or changing its primary key, with
  a comment explaining why.
- Lock multiple rows in a consistent order (`order_by`); when changing both `Message` and
  `UserMessage`, lock `Message` first. Joined queries use `of=("self",)`. Keep the transaction short
  once the lock is held.
- Always pass `update_fields=[...]` to `.save()`.
- Side effects run after commit: `send_event_on_commit`, `queue_event_on_commit`, otherwise
  `transaction.on_commit`.
- Use `ZulipTransactionTestCase` only to test locking or `durable=True` behavior.

## Caching

- Use the cached accessors: `get_user_profile_by_id`, `get_user_by_delivery_email`, `get_realm`,
  `get_client`, `access_stream_by_id`, etc. They handle case, `select_related` and caching.
- `@cache_with_key(key_func, timeout=...)` (`zerver/lib/cache.py`): on a hit the function body
  doesn't run. A different query needs a different key function; never share a key with an
  existing cache.
- Invalidation is via `post_save.connect(flush_xxx, sender=Model)` in `zerver/models/*.py`, keyed on
  `update_fields`. When adding a cache, add the fields that affect it to the matching flush
  function.
- `QuerySet.update()`, `bulk_update()` and `bulk_create()` don't fire `post_save`; flush caches by
  hand (e.g., `bulk_flush_users`).
- Fetch in bulk with `bulk_cached_fetch` / `generic_bulk_cached_fetch`, never one by one in a loop.
- For caching within a single request, use `@cache_for_current_request`
  (`zerver/lib/per_request_cache.py`).
- Starting `run-dev` and running `migrate` flush memcached; each test uses its own key prefix.

## Queue workers

- Publish: `queue_event_on_commit(queue_name, event)` (`zerver/lib/queue.py`); the event must be
  JSON-serializable. In tests there is no RabbitMQ; the matching worker processes it directly.
- For occasional background jobs, prefer adding an `event["type"]` branch to
  `zerver/worker/deferred_work.py` over a new process.
- New queue: the file must be `zerver/worker/<queue_name>.py`, the class decorated with
  `@assign_queue("<queue_name>")`, subclassing `QueueProcessingWorker` (one `consume` per event)
  or `LoopQueueProcessingWorker` (batches). Production also needs it in `$base_queues` in
  `puppet/zulip/manifests/app_frontend_base.pp` (an ops path; tell the lead).
- Debugging: `run-dev` runs all workers; run one alone with
  `./manage.py process_queue --queue=<name>`; clear with `./manage.py purge_queue <name>`.

## Messages, notifications, Markdown, email

- Server code sends messages with `internal_send_stream_message` / `internal_send_private_message`
  (`zerver/actions/message_send.py`); user messages go through `check_message` + `do_send_messages`.
  That path is heavily optimized: keep queries bulk and guard it with query-count tests.
- Long-inactive users are "soft-deactivated" and may lack `UserMessage` rows (filled in by
  `add_missing_messages` when they return); code must not assume the row exists.
- Notification decisions live in `zerver/lib/notification_data.py` (tests in
  `test_notification_data.py`); Tornado's `maybe_enqueue_notifications` puts work on the
  `missedmessage_emails` / `missedmessage_mobile_notifications` queues, and the workers recheck
  read status, deletion and user settings before sending.
- The backend Markdown processor is in `zerver/lib/markdown/__init__.py`; it runs in a thread and
  cannot query the database. New syntax needs the frontend to follow (`web/src/markdown.ts`) and
  cases in `zerver/tests/fixtures/markdown_test_cases.json`. The rendered HTML structure is part of
  the API and carries XSS risk; ask the lead before changing it.
- Email: `send_email` / `send_future_email` (`zerver/lib/send_email.py`); address mail to
  `user_profile.delivery_email`; bulk sending goes through a queue. Templates are in
  `templates/zerver/emails/` (a frontend path). In development see `http://localhost:9991/emails`
  or `var/log/email_content.log`; in tests check `django.core.mail.outbox`.

## API design conventions

- **Compatibility**: new endpoints, parameters and response fields are compatible as long as old
  requests keep their meaning (a new parameter's default equals the old behavior). These changes
  are incompatible; ask the lead first: changing meaning or type, removing fields, adding enum
  values, adding new kinds of objects to existing lists, changing the structure or classes of
  rendered message HTML, changing push notification payloads. Make incompatible changes opt-in:
  a parameter that defaults to off for endpoints, `client_capabilities` for events.
- **Clarity**: design from the client implementation's point of view; names match meanings exactly;
  use objects rather than tuples so fields can be added later.
- The `Client` model (from User-Agent) is for statistics and debugging only, never for behavior.

## OpenAPI documentation

- Each endpoint in `zerver/openapi/zulip.yaml` has `operationId`, `tags`, `summary`, `description`;
  admin-only endpoints add `x-requires-administrator: true`; every parameter has a schema and an
  `example`; the 200 response uses `allOf` + `$ref: "#/components/schemas/JsonSuccessBase"`, lists
  every field, and has an `example`. Descriptions state current behavior only.
- Automated checks:
  - `zerver/tests/test_openapi.py`: documented parameters match the view's keyword-only parameters
    one to one.
  - Every API response in `test-backend` is validated against the schema; a missing field reports
    `Additional properties are not allowed ('x' was unexpected)`. Debug with
    `./tools/test-backend --rerun`.
  - `node tools/check-openapi.ts` (run by `tools/lint`) checks the YAML.
  - Each `operationId` needs a line in `api_docs/include/rest-endpoints.md` (checked by
    `test_openapi`).
  - `./tools/test-api` runs the curl examples and the `@openapi_test_function` examples in
    `zerver/openapi/python_examples.py`. It uses port 9981, which conflicts with `/visual-test`;
    ask the lead before running it.

## Management commands

Put them in `zerver/management/commands/<name>.py`, subclass `ZulipBaseCommand`
(`zerver/lib/management.py`), and use `add_realm_args` / `get_realm` / `get_user` for `--realm`
and user arguments. Logic lives in functions in `zerver/lib/` or `zerver/actions/` (so events and
caches stay correct and it is testable); the command itself only parses arguments.

## Python essentials

- Avoid N+1: `select_related` / `prefetch_related`; pin query counts in tests with
  `assert_database_query_count`.
- Never use model objects as dict keys or set members; use ids.
- Time: `from django.utils.timezone import now as timezone_now`; convert timestamps with
  `zerver.lib.timestamp.timestamp_to_datetime`; always UTC. Tests use
  `time_machine.travel(..., tick=False)` rather than mocking `timezone_now`.
- Format strings with f-strings or `.format`; test existence with `.exists()`; iterate large result
  sets once with `.iterator()`; replace `functools.partial` with `zerver.lib.partial.partial`; use
  `urlsplit`; get MIME types from `zerver.lib.mime_types`.
- Pass state or log file paths through `zulip_path` (`zproject/computed_settings.py`).
- Logging: `logging.warning` goes to `var/log/errors.log`; `logging.error` / `logging.exception`
  email the admins in production. The dev server's per-request log line (terminal and
  `var/log/server.log`) shows database time and query count; check it after changing an endpoint.

## Tests

For how to write tests, test data, and common assertions, see `guides/testing.md`.
