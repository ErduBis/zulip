# Testing guide

For sessions that write and run tests (backend, frontend, integrations): building on the "Testing"
section of `DEVELOPMENT.md`, this covers how to pick tests, how to write them, and how to debug
failures. Run all commands in `~/zulip` with the venv activated; paths and function names have been
checked against the current code.

## Running tests in the shared directory

- Each `tools/test-backend` run clones its own databases from the template (names carry a random
  ID), so several sessions can run it at the same time.
- These files are shared by all sessions and get overwritten whenever another session runs tests:
  - `var/last_test_failure.json`: read by `--rerun`. If you are unsure your session made the last
    run, name the tests explicitly.
  - `var/.coverage`, `var/coverage/` (backend coverage), `var/node-coverage/` (frontend coverage).
  - `var/puppeteer/`: screenshots and login credentials.
- `tools/test-js-with-puppeteer`, `tools/test-api`, `tools/test-help-documentation` and
  `/visual-test` share the 9981 test server and the `zulip_test` database, and reset it on startup.
  All of them fall under "only one session at a time"; ask the lead first.
- The 9991 dev server uses the user's dev database `zulip`. `tools/rebuild-dev-database` and
  `./manage.py populate_db` wipe it, so ask the lead first; in `./manage.py shell` and
  `./manage.py dbshell`, only run queries.
- `tools/lint` and `tools/run-mypy` only check files tracked by git, so **new files are silently
  skipped**. Check new files with the commands in "Lint and type checking", and list them in your
  report so the lead can `git add` them.

## Backend: `tools/test-backend`

Naming tests runs them serially; with no arguments the full suite runs in parallel:

```bash
./tools/test-backend zerver.tests.test_users       # module; also zerver/tests/test_users.py or test_users
./tools/test-backend PermissionTest                # class name, looked up in the zerver/, corporate/, analytics/ tests
./tools/test-backend PermissionTest.test_role_setters   # single test
./tools/test-backend zerver/webhooks/github        # webhook tests must be named explicitly
./tools/test-backend zerver.transaction_tests.test_user_groups   # transaction tests need the full path
```

| Option                                               | Purpose                                                                                            |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `-x` / `--stop`                                      | Stop at the first failure                                                                          |
| `--rerun`                                            | Run only the tests that failed last time (see shared files above)                                  |
| `--coverage`                                         | Measure coverage; add `--no-cov-cleanup --no-html-report` to keep the data for the analysis script |
| `--parallel N`                                       | Number of processes                                                                                |
| `--verbose`                                          | Print each test name                                                                               |
| `--reverse`                                          | Run in reverse order, to find order dependencies between tests                                     |
| `--ban-console-output`                               | Fail on stray output (`print`, uncaptured logs)                                                    |
| `--include-webhooks` / `--include-transaction-tests` | Include these two parts in a full-suite run (skipped by default)                                   |

- Every run first executes `tools/webpack --test` and checks whether the test database needs
  updating (see the next section).
- Network access is blocked in tests: outgoing calls via `requests` etc. raise
  `Outgoing network requests are not allowed in the Zulip tests`. Mock external HTTP with
  `responses` (`@responses.activate` plus `responses.add(...)`; `git grep responses.add` for
  examples).
- Coverage is enforced only by a full-suite `--coverage` run: every `.py` file under `zerver/`,
  `zproject/`, `analytics/`, `corporate/`, `confirmation/` and similar directories must be 100%
  covered; the exception list is `not_yet_fully_covered` in `tools/test-backend`. New files need full
  coverage too. When running a single module, use the analysis script from `/fix-backend-coverage`
  to see which lines are missing.
- Lines `tools/coveragerc` excludes from coverage: lines with `# nocoverage`,
  `raise AssertionError`, `raise NotImplementedError`, `raise UnsupportedWebhookEventTypeError`,
  `@abstractmethod`, `__str__`/`__repr__`.

## Test database and test data

- Tests clone the template database `zulip_test_template`. `tools/rebuild-test-database` builds it:
  `migrate` → `populate_db --test-suite` (fixed, reproducible data) → dump some tables to
  `zerver/tests/fixtures/messages.json` (generated, git-ignored).
- The template updates itself: changed migrations trigger an automatic migrate or rebuild; changes to
  files in `IMPORTANT_FILES` in `zerver/lib/test_fixtures.py` (`populate_db.py`,
  `zerver/lib/generate_test_data.py`, etc.) trigger a rebuild. If the test database gets broken (for
  example after debugging a migration), run `tools/rebuild-test-database` by hand.
- Each test runs inside a transaction that is rolled back at the end; Redis and memcached keys get a
  per-test prefix. So tests don't affect each other, but a test also never sees what happens after a
  transaction commits (see "Events, queues and email").
- Test users live in the `zulip` realm; get them with `self.example_user("<name>")`:

| Name      | Role          | Channels subscribed in the test data       |
| --------- | ------------- | ------------------------------------------ |
| hamlet    | Member        | Verona, Denmark, core team, etc.           |
| cordelia  | Member        | Verona only                                |
| othello   | Member        | Verona, Denmark, Scotland                  |
| prospero  | Member        | Verona, Denmark, Scotland, Venice          |
| aaron     | Member        | Verona only                                |
| iago      | Administrator | Verona, Denmark, Scotland, core team, etc. |
| desdemona | Owner         | Verona, Denmark, Venice, core team, etc.   |
| shiva     | Moderator     | Verona, Denmark, Scotland                  |
| polonius  | Guest         | Verona only                                |

- Bots: `webhook_bot`, `outgoing_webhook_bot`, `default_bot`. Other realms: `self.lear_user("king")`
  (`lear`), `self.mit_user("sipbtest")` (`zephyr`). The Rome channel is web-public.
  `self.nonreg_email("alice")` is an unregistered address for testing signup.
- Use iago for admin, hamlet for a regular user, and cordelia or othello as "someone else". Create the
  data a test needs yourself, without relying on existing data such as message counts.

## Writing backend tests

```python
from typing_extensions import override

from zerver.lib.test_classes import ZulipTestCase


class WidgetTest(ZulipTestCase):
    @override  # mypy requires this when overriding a parent method
    def setUp(self) -> None:
        super().setUp()
        self.hamlet = self.example_user("hamlet")

    def test_rename_widget(self) -> None:
        self.login("hamlet")
        result = self.client_patch("/json/widgets/1", {"name": "new"})
        self.assert_json_success(result)
        # Read from the database again to confirm the state really changed

        result = self.api_patch(self.example_user("polonius"), "/api/v1/widgets/1", {"name": "x"})
        self.assert_json_error(result, "Insufficient permission")
```

- **Requests**: after `self.login(name)`, use `client_get/post/patch/put/delete` for `/json/...`;
  `api_get/post/patch/delete(user, "/api/v1/...")` authenticates with the API key and needs no login.
  Add `subdomain="lear"` to hit another realm.
- **Parameters**: an `info` dict is form-encoded; parameters declared as `Json[...]` in the view need
  `orjson.dumps(value).decode()`.
- **Asserting results**: `assert_json_success(result)` returns the parsed dict;
  `assert_json_error(result, "full error message", status_code=400)`; `assert_json_error_contains`;
  for HTML pages, `assert_in_success_response(["text"], result)`.
- **Asserting state**: after the request, `obj.refresh_from_db()` or query again.
- **Setting up data**: `make_stream`, `subscribe`, `unsubscribe`, `send_stream_message` (returns the
  message ID), `send_personal_message`, `send_group_direct_message`, `set_user_role`; more often, call
  the `do_*` functions in `zerver/actions/` directly so the test takes the same path as real code.
  `create_test_bot` logs the client in as the user you pass.
- **Other**: `assert_length(items, n)`, `get_last_message()`; in `zerver/lib/test_helpers.py`,
  `most_recent_message(user)` and `get_subscription(stream_name, user)`.
- Share setup between success and failure cases by asserting them in sequence in one test, so a
  failure case can't "pass by accident" because it failed for some other reason.
- **OpenAPI validation**: the test client (`ZulipClientHandler` in `zerver/lib/test_classes.py`)
  checks every `/json/` and `/api/v1/` request and response against `zerver/openapi/zulip.yaml`: a
  response from a documented endpoint that doesn't match the docs fails, and so does a 2xx request
  with parameters missing from the docs; pass `intentionally_undocumented=True` when deliberately
  testing undocumented behavior. When changing an endpoint, update `zulip.yaml` first, then run
  `zerver.tests.test_openapi`.

## Events, queues and email

- `send_event_on_commit`, `queue_event_on_commit` and other `transaction.on_commit` callbacks only
  run when the transaction commits, and a test's outer transaction never commits. To verify them:
  - Real-time events: `with self.capture_send_event_calls(expected_num_events=1) as events:`, then
    check `events[0]["event"]` and `events[0]["users"]`.
  - Other callbacks: `with self.captureOnCommitCallbacks(execute=True):`.
- There is no RabbitMQ in tests: queue events make a JSON round trip and are then processed
  synchronously by the matching worker (`zerver/lib/queue.py`). To assert only what was published,
  use `test_helpers.mock_queue_publish("<module>.queue_event_on_commit")`, which also checks the event
  is JSON-serializable.
- Email: tests use Django's in-memory backend, so sent mail lands in `django.core.mail.outbox`; get
  confirmation links with `self.get_confirmation_url_from_outbox(email)`.
- Adding or changing an event format:
  1. Define the type in `zerver/lib/event_types.py` and add a `check_*` checker in
     `zerver/lib/event_schema.py`;
  2. In `zerver/tests/test_events.py`, run the action inside `with self.verify_action() as events:`,
     then `check_*("events[0]", events[0])`; `verify_action` also verifies that the `apply_events`
     result matches a fresh fetch of the state;
  3. Frontend: add an example event to `web/tests/lib/events.cjs` and test dispatch in
     `web/tests/dispatch.test.cjs`;
  4. `./tools/check-schemas` checks that the Python types, OpenAPI and frontend examples agree.
- Once a new realm setting is in `Realm.property_types`, `do_set_realm_property_test` in
  `test_events.py` and `do_test_realm_update_api` in `test_realm.py` cover it automatically; for
  non-boolean types, add test values to `test_values` in both places.

## Mocks, settings, time and performance

- Apply `mock.patch` **where the name is used**: if module `b` does `from a import f` and calls `f`,
  patch `"b.f"`.
- Assert on mocks with methods starting with `assert_`, such as `assert_called_once_with` (enforced
  by lint; something like `m.called_once_with(...)` verifies nothing).
- Server settings: `with self.settings(NAME=value):` or `@override_settings(...)`; this only works for
  settings read at runtime. Change realm settings through actions such as `do_set_realm_property`.
- Rate limiting is off in tests by default; to test it, use
  `test_helpers.ratelimit_rule(range_seconds, num_requests, domain=...)`.
- Time: `with time_machine.travel(dt, tick=False):`.
- Logs: `with self.assertLogs("<logger>", level="WARNING") as m:`; see `.claude/rules/testing.md` for
  how to assert on them.
- Query counts: `with self.assert_database_query_count(n):`; to see the SQL, use
  `test_helpers.queries_captured()`; for cache accesses, `assert_memcached_count(n)`. When the number
  changes, first work out whether the extra queries are necessary, then update the number.
- Files: put temporary files under `settings.TEST_WORKER_DIR` (unique per test process, deleted when
  the run ends); `LOCAL_UPLOADS_DIR` is emptied in every test's `tearDown`.
- Tests that need real commits (`select_for_update` races, `transaction.atomic(durable=True)`)
  inherit from `ZulipTransactionTestCase` and live in `zerver/transaction_tests/`; when such a test
  ends, every table must hold exactly the rows it held at the start.
- Type test helper methods that return a response as `"TestHttpResponse"`:
  `if TYPE_CHECKING: from django.test.client import _MonkeyPatchedWSGIResponse as TestHttpResponse`.
- LDAP: `self.init_default_ldap_database()` together with `override_settings(AUTH_LDAP_...)`; see
  `zerver/tests/test_auth_backends.py`.

## Webhook integration tests

- Tests go in `zerver/webhooks/<name>/tests.py` and inherit from `WebhookTestCase`; payloads go in
  `zerver/webhooks/<name>/fixtures/<fixture>.json`, using data sent by the real service.
- By default messages are sent as `webhook-bot@zulip.com` to a channel named after the directory; set
  `URL_TEMPLATE` when the URL format differs.
- Main assertion:
  `self.check_webhook("<fixture>", expected_topic_name, expected_message, content_type=...)`; pass
  extra request headers as keyword arguments (e.g., `HTTP_X_GITHUB_EVENT="push"`).
- When the view declares event types with `@webhook_view(..., all_event_types=ALL_EVENT_TYPES)`,
  every `check_send_webhook_message` call must pass a `complete_event_type` that is in the list, or
  the test errors out.
- Unsupported events `raise UnsupportedWebhookEventTypeError` (excluded from coverage).

## Frontend: `tools/test-js-with-node`

```bash
./tools/test-js-with-node compose            # web/tests/compose.test.cjs; several names allowed
./tools/test-js-with-node --coverage         # runs serially; coverage is enforced only on full runs
```

- Every file in `web/src/` needs 100% line coverage; the exception list is `EXEMPT_FILES` in
  `tools/test-js-with-node`. New files need full coverage too. The report is in `var/node-coverage/`;
  see `/debug-node-coverage` for troubleshooting.
- `web/tests/*.test.cjs` files are discovered automatically; tests for `web/src/foo.ts` go in
  `web/tests/foo.test.cjs`. To get started, read `web/tests/example1.test.cjs` through
  `example8.test.cjs`; for zjquery, read `web/tests/zjquery.test.cjs`.

```js
"use strict";

const assert = require("node:assert/strict");

const {mock_esm, zrequire} = require("./lib/namespace.cjs");
const {run_test, noop} = require("./lib/test.cjs");
const {$} = require("./lib/zjquery.cjs");

// mock_esm must come before zrequire: it swaps dependencies at module load time
const channel = mock_esm("../src/channel");

const foo = zrequire("foo");

run_test("foo sends a request", ({override}) => {
    override(channel, "get", (opts) => {
        assert.equal(opts.url, "/json/foo");
    });
    foo.load();
});
```

- `zrequire("name")` loads real code (relative to `web/src/`); `mock_esm("../src/x", {fn: noop})`
  replaces a whole module with a fake object (relative to `web/tests/`). "You asked to mock … but we
  never saw it during compilation" means the code under test doesn't use that module; delete the
  mock.
- Tools passed to the `run_test` callback, all restored when the test ends:
  - `override(obj, "prop", value)`: replace a property or function; a replaced function that is never
    called fails with `never got invoked!`; pass `{unused: false}` when not calling it is legitimate.
    `disallow(obj, "prop")`: fail if it is ever called.
  - `override_rewire(mod, "fn", value)`: replace a function called from inside its own module. The
    source must declare it as `export let fn = ...` and export `rewire_fn` (see
    `rewire_send_presence_to_server` in `web/src/activity.ts`). `disallow_rewire` works the same way.
  - `mock_template("path.hbs", false, (data) => …)`: assert on the data passed to a template; with
    `true` as the second argument it really renders, and the callback also receives `html`.
- DOM: jQuery is simulated by zjquery, and `$("#id")` returns a fake element;
  `$el.set_find_results(selector, $result)` sets what `.find()` returns;
  `$el.get_on_handler("click")` fetches an event handler so you can call it directly. On "You must
  create a stub for …" or "You need to call … set_find_results", add what the message asks for.
- blueslip: before the code under test calls `blueslip.warn`/`blueslip.error`, the test must call
  `blueslip.expect("error", "full message")`, or the test fails (`web/tests/lib/zblueslip.cjs`).
- Test data: `make_user` from `web/tests/lib/example_user.cjs`, `make_stream` from
  `example_stream.cjs`, `make_realm` from `example_realm.cjs`; set the current realm and user with
  `set_realm` and `set_current_user` from `state_data`.
- Timers are fake: use the `clock` exported by `namespace.cjs`, with `clock.tick(ms)` to advance and
  `clock.setSystemTime(...)` to set the current time; the time zone is fixed to UTC.
- Counting stubs: `make_stub()` from `web/tests/lib/stub.cjs` (`stub.f`, `stub.num_calls`,
  `stub.get_args(...)`).

## Browser end-to-end tests (Puppeteer)

- Tests are `web/e2e-tests/*.test.ts`, helpers are in `web/e2e-tests/lib/common.ts`; run
  `./tools/test-js-with-puppeteer compose` (matches file names by prefix). Subject to the 9981 server's
  "one session at a time" rule.
- Cover with node tests whatever node tests can cover; write end-to-end tests for behavior that needs
  a real browser, such as login redirects, keyboard shortcuts and copy/paste.
- Wait for the UI before every action: `page.waitForSelector(sel, {visible: true})` (without
  `visible`, the wait ends as soon as the element is in the DOM).
- Failures save screenshots to `var/puppeteer/*.png`; `--loop N` runs N times to check for flaky
  failures.
- Test data is the same as for backend tests (`populate_db --test-suite`), logged in as desdemona by
  default. See `/visual-test` for writing details.

## Lint and type checking

- Run a subset of checks: `./tools/lint --only=mypy,ruff <files> </dev/null`, or `--skip=...`,
  `--groups=backend,frontend`; `--list` lists all checks, `--fix` fixes formatting-type problems.
- Check new files that git doesn't track yet individually:

```bash
mypy <file.py>
ruff check <file.py> && ruff format --check <file.py>
node_modules/.bin/eslint <file>
node_modules/.bin/prettier --check <file>
node_modules/.bin/stylelint <file.css>
./tools/run-tsc        # checks the whole frontend per tsconfig.json, untracked files included
```

- mypy runs in strict mode (configured in `pyproject.toml`): add `@override`
  (`from typing_extensions import override`) when overriding a parent method; write
  `# type: ignore` as `# type: ignore[code] # reason`; give `QuerySet` its model type, as in
  `QuerySet[UserProfile]`.
- Test-related rules in `tools/linter_lib/custom_check.py`: use `assert_length` instead of
  `assertEqual(len(...), n)`; assert on mocks with `assert_` methods; pass `durable=True` or
  `savepoint=False` to `transaction.atomic` explicitly; use `assert.ok(...)` in frontend tests; don't
  tag test strings for translation.
- Specialized checks: `./tools/check-schemas` (event formats), `./tools/test-migrations` (migrations
  match models), `./tools/check-templates` (template tags and indentation),
  `./tools/check-capitalization` and `./tools/check-frontend-i18n` (user-facing strings).

## Dev environment conveniences

- The dev database (9991) holds our own generated Chinese sample organization, whose members differ
  from the test database: owner 唐僧 `tangseng@zulip.com`, administrator 孙悟空
  `sunwukong@zulip.com`, regular member 猪八戒 `zhubajie@zulip.com`, guest 观音菩萨
  `guanyin@zulip.com`; the full list is in `zcustom/dev_data/org.yaml`. hamlet and the other users in
  the table above exist only in the test database. `./manage.py populate_dev_zh` generates the dev
  database (`tools/rebuild-dev-database` runs it and wipes the dev database, so ask the lead first);
  after changing data in `zcustom/dev_data/`, validate it with `./manage.py populate_dev_zh --check`.
- `./manage.py print_initial_password sunwukong@zulip.com` prints a dev organization member's
  initial password and API key, for calls like
  `curl -u sunwukong@zulip.com:<API key> http://localhost:9991/api/v1/users/me` (send only GET
  requests, so the dev data stays unchanged).
- `http://localhost:9991/devtools/` lists dev-only pages: `/emails` (the dev environment doesn't
  really send mail; everything "sent" shows up here), `/devtools/buttons`, `/devtools/banners`,
  `/devtools/inputs` (component styles), `/errors/404`, `/errors/5xx`.
- Changes take effect automatically: run-dev restarts itself after Python changes; the browser
  reloads after changes to `web/src/` and `web/templates/`; for Jinja2 templates under `templates/`,
  reload the page. Frontend exceptions in the dev environment show up as a prominent error box on the
  page, visible in screenshots.
