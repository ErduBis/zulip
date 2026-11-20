# Integrations and brand guide

For the "integrations and brand" role: incoming webhook integrations (`zerver/webhooks/`), bots,
and brand assets (`static/images/`). For the Chinese translation, see
`custom/en/guides/translation.md`.

## Files that make up an incoming webhook integration

Name it `<name>` (all lowercase, e.g., `mywebhook`) and follow `zerver/webhooks/helloworld/`:

| File                                                | Contents                                                         |
| --------------------------------------------------- | ---------------------------------------------------------------- |
| `zerver/webhooks/<name>/__init__.py`                | Empty file                                                       |
| `zerver/webhooks/<name>/view.py`                    | Handler function `api_<name>_webhook`                            |
| `zerver/webhooks/<name>/fixtures/*.json`            | Payloads the service really sends; used by tests and screenshots |
| `zerver/webhooks/<name>/tests.py`                   | Tests                                                            |
| `zerver/webhooks/<name>/doc.md`                     | Setup instructions, shown at `/integrations/doc/<name>`          |
| `static/images/integrations/logos/<name>.svg`       | Square logo (`.png` when no SVG exists)                          |
| `static/images/integrations/bot_avatars/<name>.png` | Bot avatar generated from the logo                               |
| `static/images/integrations/<name>/001.png`         | Example message screenshot on the doc page                       |

**Registration**: add an entry to `INCOMING_WEBHOOK_INTEGRATIONS` in `zerver/lib/integrations.py`;
the URL `/api/v1/external/<name>` then points to `zerver.webhooks.<name>.view.api_<name>_webhook`.
This file is an original Zulip file: keep the change to the one entry. The list must be in alphabetical order (checked by `test_sorting` in
`zerver/tests/test_integrations.py`):

```python
IncomingWebhookIntegration(
    "helloworld", ["misc"], [WebhookScreenshotConfig("hello.json")], display_name="Hello World"
),
```

- The second argument lists categories, which are keys of `CATEGORIES` in the same file.
- `WebhookScreenshotConfig` names the fixture used for the doc screenshot (it also accepts
  `bot_name`, `channel`, `custom_headers`, `extra_params`, etc.).
- `url_options`: options offered to the user in the "generate integration URL" modal.
  `WebhookUrlOption(name, label, input_type)` with `input_type` `checkbox` (parameter added only when
  checked), `checkbox_enabled` (checked by default) or `text`; or a preset such as
  `WebhookUrlOption.build_preset_config(PresetUrlOption.BRANCHES)` (also
  `IGNORE_PRIVATE_REPOSITORIES`, `CHANNEL_MAPPING`), defined in `zerver/lib/webhooks/common.py`.
- When renaming, keep the old URL working with `legacy_names`.

## Writing the handler

1. **Capture fixtures first**: use Zulip's JSON integration, webhook.site or similar to capture
   payloads the service really sends, or take the examples from the service's API docs. Save
   fixtures unmodified and only those the tests need; name them after the event in snake_case,
   e.g., `issue_created_with_assignee.json`. Before capturing, use realistic project and people names
   in the third-party service, ideally the example people in
   `zerver/webhooks/fixtureless_integrations.py` (they appear in the doc screenshots).
2. **`view.py`**, following `zerver/webhooks/helloworld/view.py`:
   - `@webhook_view("ServiceName")` + `@typed_endpoint`. Write the name in camel case as the service
     spells it, with a capital first letter (`GitHub`, `HelloWorld`); it appears on the stats page.
     For services using HTTP Basic auth, use
     `@authenticated_rest_api_view(webhook_client_name="ServiceName")` instead.
   - Parameter `payload: JsonBodyPayload[WildValue]`; read values with
     `payload["key"].tame(check_string)`. A `KeyError` from a missing field is handled by the server.
   - Send with `check_send_webhook_message(request, user_profile, topic_name, body, event_type)` and
     return `json_success(request)`. With `stream` in the URL it posts to that channel; otherwise it
     sends a direct message to the bot's owner.
3. **Event types**:
   - When the event type is in an HTTP header: `get_event_header(request, "X-Event-Key", "ServiceName")`;
     name fixtures `<header value>__<subtype>.json` and define
     `fixture_to_headers = default_fixture_to_headers("HTTP_X_EVENT_KEY")` in `view.py`.
   - Unsupported events: `raise UnsupportedWebhookEventTypeError(event_type)` (`zerver/lib/exceptions.py`).
   - Event filtering: `@webhook_view(..., all_event_types=ALL_EVENT_TYPES)` and pass
     `complete_event_type` with every message; pass `complete_event_type=None` explicitly for notices
     that must not be filtered. Event names end up in users' URLs, so they keep their names once
     released; hierarchical names like `git.pullrequest.created` let users write `git.pullrequest.*`.
4. **Helpers** (all in `zerver/lib/webhooks/common.py`): `get_setup_webhook_message` builds the
   standard reply to a service's test payload; `guess_zulip_user_from_external_account` turns
   external usernames into silent mentions of Zulip users.
5. **Message content**: use Zulip Markdown; put messages about the same object (the same bug, the
   same service) in the same topic; capitalize the service's name the way its vendor does. The
   message body is stored as message content and does not go through translation files; errors
   returned to the caller use `JsonableError(_("..."))` and are translated.

## Tests

- In `tests.py`, the class is `<Name>HookTests(WebhookTestCase)`. The URL defaults to
  `/api/v1/external/<dir name>?stream=<dir name>&api_key=...` and usually needs no setup.
- One test per event and per branch:
  `self.check_webhook("fixture_name", expected_topic, expected_body, content_type=...)`.
- Direct message to the owner: `send_and_test_private_message`; URL parameters:
  `self.url = self.build_webhook_url(topic="...")`; expected errors:
  `self.client_post(self.url, ...)` + `self.assert_json_error(result, "...")`.
- For integrations that declare event types, `WebhookTestCase` fails the test when a message is sent
  without `complete_event_type` or with an undeclared one.
- Run `./tools/test-backend zerver/webhooks/<name>`; after changing the registration or images, also
  run `./tools/test-backend zerver.tests.test_integrations zerver.tests.test_docs` (sorting, screenshot
  configs, logos, doc pages).

## Manual testing

First create a bot of type **Incoming webhook** under **Settings → Bots** and copy its API key.

- UI: `http://localhost:9991/devtools/integrations/`; pick the bot, integration and fixture, then
  click **Send!**.
- Command line:

  ```bash
  ./manage.py send_webhook_fixture_message \
      --fixture=zerver/webhooks/<name>/fixtures/<fixture>.json \
      '--url=http://localhost:9991/api/v1/external/<name>?api_key=<key>&stream=<channel>' \
      --custom-headers='{"X-Event-Key": "issue_created"}'
  ```

- URL parameters: `api_key` (required), `stream` (channel ID or URL-encoded channel name), `topic`,
  `only_events` / `exclude_events` (e.g., `["issue_*"]`, `*` wildcards allowed).

## Doc page and images

- **`doc.md`**: copy `zerver/webhooks/basecamp/doc.md` and edit it. Structure: one-sentence intro →
  numbered steps inside `{start_tabs}` → `{end_tabs}` → `{!congrats.md!}` → screenshot
  `![](/static/images/integrations/<name>/001.png)` → `{!event-filtering-additional-feature.md!}`
  when filtering is supported → `### Related documentation` + `{!webhooks-url-specification.md!}`.
- Macros live in `templates/zerver/integrations/include/`; common ones: `create-an-incoming-webhook.md`,
  `generate-webhook-url-basic.md`, `generate-webhook-url-with-branch-filtering.md`,
  `create-channel.md`. When you must write a URL yourself, use `{{ api_url }}` instead of a hardcoded
  domain.
- Step style: imperative; actions in the order they happen ("Under **Webhooks**, click **Add
  Webhook**."); bold third-party UI elements and drop their trailing punctuation; "navigate to the
  page" and "fill out the form and save" are one step each; put side notes in `!!! tip ""` and problem
  warnings in `!!! warn ""`.
- **Logo**: after adding the SVG, run `./tools/setup/optimize-svg` (with no argument it compresses all
  logos and regenerates all bot avatars), then check with `git status static/images/integrations`
  that only your files changed.
- **Screenshot**: `./tools/screenshots/generate-integration-docs-screenshot --integration <name>`.
  It sends the fixture to the running dev server, creating a bot and channel in the dev database, and
  saves the screenshot to `static/images/integrations/<name>/001.png`.

## Bots

- **Outgoing webhook bots**: when @-mentioned in a channel (`trigger` is `mention`) or sent a direct
  message (`direct_message`), the server POSTs the message to the bot's URL, in Zulip format or
  Slack-compatible format; fields are documented under `/zulip-outgoing-webhook` in
  `zerver/openapi/zulip.yaml` and in `api_docs/outgoing-webhook-payload.md`. The service replies with
  JSON: `content` is posted as the reply; `response_not_required: true` means no reply. Timeout is
  `OUTGOING_WEBHOOK_TIMEOUT_SECONDS` (10 seconds by default); on failure the bot owner is notified.
  Implemented in `zerver/lib/outgoing_webhook.py` and `zerver/worker/outgoing_webhooks.py` (backend
  paths).
- **Reaching internal services in production**: the server's outgoing requests go through the
  Smokescreen proxy, which rejects private IPs by default. For an internal target, environment and
  ops adds `allow_addresses = <IP>` under `[http_proxy]` in `/etc/zulip/zulip.conf` and reruns
  `zulip-puppet-apply`. The dev environment does not use the proxy.
- **Embedded bots**: run inside the server; the list is `EMBEDDED_BOTS` in
  `zerver/lib/integrations.py`, the code comes from the `zulip_bots` package, dispatched by
  `zerver/worker/embedded_bots.py`.
- In tests, outgoing HTTP requests are mocked with the `responses` library; examples:
  `git grep responses.add`.

## Brand assets

When replacing an asset, keep its file name and dimensions, and `git grep <file name>` first to find
every reference.

| Where it shows                             | File                                                  | Related files (owner)                                                                                                       |
| ------------------------------------------ | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Browser tab icon                           | `static/images/favicon.svg`, `favicon.png`            | Unread-count version `web/templates/favicon.svg.hbs`; the `?v=4` cache parameter in `templates/zerver/base.html` (frontend) |
| Top-left when the org has no uploaded logo | `static/images/logo/zulip-org-logo.svg`               | `zerver/lib/realm_logo.py`                                                                                                  |
| Link preview image                         | `static/images/logo/zulip-icon-128x128.png`           | `templates/zerver/meta_tags.html`                                                                                           |
| iOS home screen icon                       | `static/images/logo/apple-touch-icon-precomposed.png` | `templates/zerver/app/index.html`                                                                                           |
| Email header logo                          | `static/images/emails/email_logo.png`                 | `templates/zerver/emails/`                                                                                                  |
| Default avatar                             | `static/images/default-avatar.png`                    | `zerver/lib/avatar.py`                                                                                                      |
| Logo on logged-out pages such as login     | Inline SVG in `templates/zerver/portico-header.html`  | Frontend                                                                                                                    |

- Changing the favicon is joint work with the frontend: both favicon files, `favicon.svg.hbs` and the
  `?v=` parameter change together, coordinated by the lead.
- Replacements without code changes (server settings, in production in `/etc/zulip/settings.py`,
  configured by environment and ops): `CUSTOM_LOGO_URL` (logged-out page logo),
  `DEFAULT_LOGO_URI` (default org logo), `DEFAULT_AVATAR_URI` (default avatar).
- Organization logos and icons are uploaded by administrators in organization settings; they are
  data.
