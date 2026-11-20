# Frontend development guide

For the frontend role (owns `web/` and `templates/`). The rules in `DEVELOPMENT.md`,
`.claude/rules/frontend.md` and `.claude/rules/css.md` still apply and are not repeated here; this
guide adds what you need to know when building custom UI on Zulip 13.2. Before starting, `git grep`
for the most similar existing feature and follow its files and patterns.

## Where the code lives

| Path                           | Contents                                                                                                                            |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `web/src/*.ts`                 | App code, ES modules. Only `ui_init.js`, `server_events.js` and `server_events_dispatch.js` are still JavaScript                    |
| `web/src/portico/`             | Code for logged-out pages (login, signup, etc.)                                                                                     |
| `web/templates/**/*.hbs`       | Handlebars templates, rendered in the browser. Shared components in `components/`, popovers in `popovers/`, settings in `settings/` |
| `web/styles/*.css`             | App styles, one file per UI area; logged-out page styles in `web/styles/portico/`                                                   |
| `web/icons/*.svg`              | Icon sources, compiled into an icon font at build time                                                                              |
| `web/images/`                  | Images bundled by webpack                                                                                                           |
| `templates/**/*.html`          | Jinja2 server templates; the app shell is `templates/zerver/app/index.html`                                                         |
| `web/tests/`, `web/e2e-tests/` | Node unit tests, Puppeteer end-to-end tests                                                                                         |
| `web/webpack.assets.json`      | Bundle entry points per page (dev-only pages in `web/webpack.dev-assets.json`)                                                      |

- New modules and CSS files are only loaded if an entry point reaches them: for use inside the app,
  import them in `web/src/bundles/app.ts`; for both the app and logged-out pages, in
  `web/src/bundles/common.ts`; for a standalone page, add an entry in `webpack.assets.json` and write
  `{% set entrypoint = "entry-name" %}` in the Jinja2 template (`templates/zerver/base.html` injects
  the JS/CSS via `webpack_entry(entrypoint)`).
- The dev server hot-reloads: CSS changes apply immediately; `.ts`/`.hbs` changes reload the browser.
- Browser-console debugging (dev only): `require("./src/people")` returns any module
  (`web/debug-require-webpack-plugin.ts`); the `zulip_test` global is in `web/src/zulip_test.ts`.
  Use these for debugging only.

## Initial state and real-time events

1. **page_params**: the server puts page parameters in `#page-params`, parsed with zod in
   `web/src/base_page_params.ts` (the home page parameters come from
   `build_page_params_for_home_page_load` in `zerver/lib/home.py`). App code imports them from
   `web/src/page_params.ts`.
2. **state_data**: the initial data returned by `/json/register`, usually delivered as
   `page_params.state_data`. For spectators and client-triggered reloads `page_params.no_event_queue`
   is true and `ui_init.js` POSTs `/json/register` itself (keep its parameters in sync with
   `zerver/lib/home.py`).
3. `state_data_schema` in `state_data.ts` uses `split_state_data_schema` to cut the data into one
   part per module, and `ui_init.initialize_everything` hands each part to that module's `initialize`.
   - **zod objects drop undeclared fields**: a field the backend adds must be added to the matching
     part's schema, or the frontend never sees it and nothing errors. Organization settings →
     `realm_schema` (keys prefixed `realm_`); user settings → `user_settings_schema` in
     `user_settings.ts`; current user → `current_user_schema`.
   - Reading: `import {current_user, realm} from "./state_data.ts"`, `import {user_settings} from "./user_settings.ts"`.
   - Messages are not in the initial state; `message_fetch.ts` fetches them separately, and events
     about messages not yet fetched are discarded.
4. **Events**: `server_events.js` long-polls `/json/events` and passes events to
   `server_events_dispatch.dispatch_normal_event(event)`, which switches on `event.type`.
   - Changes you make yourself come back as events too. Put UI updates in the event handler; the AJAX
     `success` callback only gives feedback for this action (a checkmark, closing the dialog), so
     every tab and every user ends up with the same result.
   - `realm` `update` events: only properties listed in the `realm_settings` object are written back
     to `realm`. A new setting needs a line there (`noop` if no extra UI needs updating); settings-page
     controls are synced by `settings_org.sync_realm_settings`.
   - `user_settings` events work the same way: the property must appear in one of the lists in that
     `case` (notification settings are in `settings_config.all_notification_settings`).
   - When the web app calls `/json/register` itself it only requests the types listed in
     `FETCH_EVENT_TYPES` in `server_event_types.ts`; add a new data type there if the frontend needs
     its initial state.

## Calling the backend

- Use `get`/`post`/`patch`/`put`/`del` from `channel.ts`:
  `channel.post({url: "/json/...", data, success, error})`. The web app uses the `/json/` prefix.
- `data` is form-encoded: parameters the backend declares as `Json[...]` (booleans, numbers, lists,
  objects) must be `JSON.stringify`'d first.
- Parse responses with zod before use: `const {id} = z.object({id: z.number()}).parse(data);`
- Show errors with `ui_report.error(...)` and `channel.xhr_error_message(...)`; submit from a dialog
  with `dialog_widget.submit_api_request(...)`, which handles the spinner, error display and closing.

## Adding a setting (frontend part)

Use the boolean organization setting `realm_require_unique_names` as the model
(`git grep require_unique_names web/` shows every place it touches):

1. Add `realm_<name>: z.boolean()` to `realm_schema` in `state_data.ts`.
2. In a suitable subsection of `web/templates/settings/organization_*_admin.hbs`, add
   `{{> settings_checkbox setting_name="realm_<name>" prefix="id_" is_checked=realm_<name> label=admin_settings_label.realm_<name>}}`.
   Non-checkbox controls need `data-setting-widget-type`. The control's id must be
   `id_<setting_name>` and it must have the `prop-element` class: the save/discard logic gets the
   property name from the id via `settings_components.extract_property_name`.
3. `admin.ts`: add a label to `admin_settings_label` (`$t`) and the current value to the `options`
   in `build_page`.
4. Add a line to `realm_settings` in `server_events_dispatch.js`.
5. Add a default value to `web/tests/lib/example_realm.cjs`.
6. Manual checks: both "Save" and "Discard changes" work; controls that depend on other settings
   show and hide correctly; real-time sync between two open windows; saving one subsection does not
   affect the others.

Personal user settings live in `settings_preferences.ts`, `settings_notifications.ts` and
`web/templates/settings/preferences_*.hbs`. To add a settings section: add a sidebar item with
`data-section` in `settings_overlay.hbs` and register its load function in
`settings_sections.initialize`.

## Templates

**Handlebars** (`import render_foo from "../templates/foo.hbs"`; `render_foo(context)` returns an
HTML string). The compile options in `web/webpack.config.ts` have three traps:

- `strict`: `{{foo}}` referring to a field missing from the context throws (`{{#if foo}}` does not).
  Pass every variable; wrap optional ones in `#if`.
- `knownHelpersOnly`: only helpers registered in `web/src/templates.ts` and listed in `knownHelpers`
  work: `eq`, `and`, `or`, `not`, `t`, `tr`, `rendered_markdown`, `numberFormat`, `list_each`,
  `tooltip_hotkey_hints`, `popover_hotkey_hints`, `map_entries`, `object_entries`, `object_values`.
- `explicitPartialContext`: partials do not inherit the caller's context; write `{{> foo .}}` or
  `{{> foo key=value}}`. Partial paths are relative to the current template's directory, e.g.,
  `{{> ../components/action_button ...}}`.

Other rules:

- `{{var}}` is escaped; `{{{var_html}}}` is not, and the variable name must end in `_html`
  (checked by `tools/check-templates`). Only pass trusted HTML: rendered templates and `$t_html`
  output; for server-rendered message content use `{{rendered_markdown content}}`.
- Build complex DOM with templates. Don't pass HTML strings directly to `.append()` (eslint
  `no-jquery/no-append-html`); use `$(render_foo(...))` or `ui_util.parse_html(...)`.
- Use `style=` only for dynamic values (such as channel colors); put all other styling in CSS.

**Jinja2** (`templates/`): the context comes from `zulip_default_context` in
`zerver/context_processors.py` and from the view's `render(...)` call (find it with
`git grep 'template/path' '*.py'`). Ask the backend when a new context variable is needed.

## Marking strings for translation

TypeScript (`web/src/i18n.ts`):

```ts
$t({defaultMessage: "Channel settings"});
$t({defaultMessage: "Invite {name}?"}, {name}); // plain text, not escaped: use .text() or let a template escape it
$t_html({defaultMessage: "<b>{count}</b> new replies."}, {count}); // values are escaped; result is safe HTML
$t_html(
    {defaultMessage: "Go to <z-link>settings</z-link>."},
    {"z-link": (content_html) => `<a href="#settings">${content_html.join("")}</a>`},
);
$t({defaultMessage: "{N, plural, one {# message} other {# messages}}"}, {N: count});
```

Handlebars:

```hbs
{{t "Channel settings" }}
{{t "Invite {full_name}?" }}  {{! variables come from the current context (strings, numbers, dates) }}
{{> settings_checkbox label=(t "Require unique names") }}
{{#tr}}Your plan is <b>{plan_name}</b>.{{/tr}}
{{#tr}}Read the <z-link>guide</z-link>.{{#*inline "z-link"}}<a href="/help/">{{> @partial-block}}</a>{{/inline}}{{/tr}}
```

Jinja2:

```jinja
{{ _("Log in") }}
{% trans %}Check your email ({{ email }}).{% endtrans %}
```

- The argument to `defaultMessage` and `{{t}}` must be a literal, never a variable: the extraction
  tools only see literals (eslint also checks this in TS).
- The only tags allowed directly in a translated string are `b code em i kbd p strong`, without
  attributes (`default_html_elements` in `i18n.ts`); use a `<z-...>` custom tag for links and other
  markup. A `{{#tr}}` block must not contain `{{var}}` or `{{#if}}`; variables use single braces.
- Mark whole sentences, never concatenate; keep end punctuation inside the string. Use ICU syntax
  for plurals, and prefer an icon plus a number over a plural sentence where possible. Format lists
  with `util.format_array_as_list(items, "long", "conjunction")`.
- Use sentence case: "Channel settings", not "Channel Settings"; capitalize proper nouns; write URL,
  HTTP etc. in their standard forms. User-facing text says organization, never realm (rejected by
  the check). Check with `./tools/check-capitalization` (it only regenerates the git-ignored
  `locale/en/`).
- Until the Integrations and brand role updates the translation files, new strings show in
  English in the Chinese UI; that is expected.
- Text length varies a lot between languages; don't hard-code widths for buttons or labels.

## Existing components (reuse first)

| Need                      | Use                                                                                                                                                                                                                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dialog, form modal        | `dialog_widget.launch({modal_title_text, modal_content_html, on_click, ...})`; confirmation `confirm_dialog.launch`; underlying `modals.ts`                                                                                                                               |
| Popover menu              | `popover_menus.register_popover_menu(selector, tippy_props)`, calling `instance.destroy()` in `onHidden`; templates in `web/templates/popovers/`                                                                                                                          |
| Tooltip                   | `tippy-zulip-tooltip` class plus `data-tippy-content="{{t '...' }}"`; delayed variant `tippy-zulip-delayed-tooltip`; rich content via `data-tooltip-template-id` pointing at a `<template>` in `tooltip_templates.hbs`                                                    |
| Button                    | `components/action_button.hbs` (`variant` + `intent`), `components/icon_button.hbs`; in dev, `/devtools/buttons`, `/devtools/banners`, `/devtools/inputs` show every variant                                                                                              |
| Banner                    | `banners.ts` + `components/banner.hbs`; banners above the compose box use `compose_banner.ts`                                                                                                                                                                             |
| Dropdown                  | `DropdownWidget` in `dropdown_widget.ts`                                                                                                                                                                                                                                  |
| Pill input (pick users)   | `input_pill.create({$container, create_item_from_text, get_text_from_item, get_display_value_from_item})`; ready-made `user_pill.ts`, `stream_pill.ts`, `user_group_pill.ts`, etc.; typeahead via `pill_typeahead.ts`; update save state in `onPillCreate`/`onPillRemove` |
| Long list, sortable table | `list_widget.create($container, items, {name, get_item, modifier_html, filter, $simplebar_container})`, renders progressively on scroll                                                                                                                                   |
| Typeahead                 | `bootstrap_typeahead.ts`, `typeahead_helper.ts`                                                                                                                                                                                                                           |
| Tab switcher              | `components.toggle(...)`                                                                                                                                                                                                                                                  |
| Loading, save feedback    | `loading.make_indicator`, `loading.show_button_spinner`; settings use `settings_ui.do_settings_change`; transient notice `feedback_widget.show`                                                                                                                           |
| Date/time picker          | `flatpickr.ts`                                                                                                                                                                                                                                                            |
| Permission checks         | `user_can_*` and `user_has_permission_for_group_setting` in `settings_data.ts`; don't re-implement permission logic in UI code                                                                                                                                            |

Pill container HTML: `<div class="pill-container"><div class="input" contenteditable="true"></div></div>`;
pills are inserted before `.input`.

## Icons

- Markup: `<i class="zulip-icon zulip-icon-<name>" aria-hidden="true"></i>`, mapped to
  `web/icons/<name>.svg` (the font is generated from `web/icons/zulip-icons.font.cjs` and
  `template.hbs`). New UI always uses `zulip-icon`.
- Look for an existing icon in `web/icons/` first. For a new one prefer Lucide style, and clean the
  SVG down to an `<svg>` (`xmlns`, `width`, `height`, `viewBox`) containing `<path>` elements with
  only a `d` attribute; no `fill`, `fill-rule` or `stroke` (checked by lint).
- Two cases that break in font conversion: stroke-based icons need Path → Stroke to Path in
  Inkscape, then stroke set to 0; icons with `evenodd` cut-outs need Object to Path → Flatten →
  Combine.
- For icons from a third-party source, tell the Lead where it came from so attribution is recorded.
- Decorative icons next to text get `aria-hidden="true"`; icon-only buttons need a tooltip plus an
  `aria-label` with the same text.

## CSS

- **Colors** are variables in `:root` of `web/styles/app_variables.css`, written as
  `light-dark(light value, dark value)` to cover both themes at once; component CSS only uses
  `var(--color-...)`. Palette variables (`--grey-*`, `--purple-*`, etc.) are in the same file.
- Dark overrides that `light-dark()` can't express go in `%dark-theme { ... }` in
  `web/styles/dark_theme.css` (extended onto `:root.dark-theme` and, when following the system, onto
  `:root.color-scheme-automatic`). In JS, check the theme with `settings_data.using_dark_theme()`.
- Colors use `hsl()` only: stylelint bans hex, `rgb()` and named colors. Don't use
  `thin`/`medium`/`thick` for border widths.
- Base font size and line height are user settings (`--base-font-size-px`,
  `--base-line-height-unitless`, set by `information_density.ts`), so sizes use `em`; by convention a
  comment gives the conversion: `0.1875em; /* 3px at 16px/1em */`.
- Use breakpoint variables: media queries `@media (width < $xl_min)`, container queries
  `@container app (width < $cq_md_min)`, defined in `web/src/css_variables.ts`. CSS nesting is
  supported.
- Class names are kebab-case, unique and easy to `git grep`; selectors don't include tag names.

## TypeScript

- Write new modules in TypeScript; edit the three `.js` files above as they are. Import paths include
  the `.ts` extension.
- `tsconfig.json` enables `strict`, `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`:
  array and object index lookups may be `undefined`; optional properties can't be assigned
  `undefined` unless their type says so.
- Validate server data with zod, imported only as `import * as z from "zod/mini"` (importing `zod`
  directly is rejected by eslint). The mini API is functional: `z.optional(z.string())`,
  `z.nullable(...)`, `z.array(...)`, with no `.optional()` chaining; get types with
  `z.infer<typeof schema>`.
- Use `assert` from `minimalistic-assert`; report errors with `blueslip.error`/`blueslip.warn`.
- eslint forbids import cycles (`import-x/no-cycle`): when two modules need each other, move the
  shared part to a new module or pass a callback through `initialize({...})`.
- Other common lint rules: no `for...in` over arrays; `+= 1` instead of `++`; no `alert`; no jQuery
  pseudo-selectors like `:visible` or `:first`. Type-check on its own with `./tools/run-tsc`.

## URLs and navigation

- Modules: `hashchange.ts`, `hash_parser.ts`, `hash_util.ts`, `browser_history.ts`.
- If your code already updated the UI and only the URL should change: `browser_history.update(hash)`;
  to have hashchange render the target page: `browser_history.go_to_location(hash)`.
- A new overlay route: add it to the list in `hash_parser.is_overlay_hash` and add a branch in
  `do_hashchange_overlay` in `hashchange`; normal views go in `do_hashchange_normal`.
- After changing navigation logic, test by hand: in-app links, the browser back button, switching
  within an overlay (must not replay the open animation), reload returning to the same place, and
  server-initiated reloads (`reload.ts` saves state into a `#reload` hash, `reload_setup.ts`
  restores it).

## Accessibility and keyboard

- Every action works from the keyboard; global shortcuts are in `hotkey.ts`, in-menu navigation uses
  `popover_menus.popover_items_handle_keyboard`.
- Images have `alt`; ARIA attributes are used correctly; text contrast meets WCAG AA.

## Other subsystems at a glance

| Subsystem         | Code                                                                                                                                                                                                                             |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unreads           | `unread.ts`: initial `unread_msgs`, maintained by `message`, `update_message_flags` and `update_message` events. Messages are marked read as you read only in views containing whole conversations; search views never mark them |
| Typing indicators | Sending `typing_status.ts`; receiving `typing_events.ts`, `typing_data.ts`                                                                                                                                                       |
| Message widgets   | Polls, todo lists, zform: registered in `widgets.ts`, plus `widgetize.ts`, `submessage.ts`, `poll_widget.ts`, `todo_widget.ts`, `zform.ts`; templates in `web/templates/widgets/`; data goes through `/json/submessage`          |
| Slash commands    | `/light`, `/dark`, etc.: `zcommand.ts` → `/json/zcommand`; typeahead list is `slash_commands` in `composebox_typeahead.ts`                                                                                                       |
| One-time notices  | `onboarding_steps.ts`: show if `ONE_TIME_NOTICES_TO_DISPLAY.has(name)`, then call `post_onboarding_step_as_read(name)`; names are registered by the backend in `zerver/lib/onboarding_steps.py`                                  |
| Image thumbnails  | Message HTML contains one size; `postprocess_content.ts` rewrites the URL using `preferred_format` from `thumbnail.ts`                                                                                                           |
| Emoji             | `emoji.ts` (e.g., `get_emoji_details_by_name`), `emoji_picker.ts`; data from `static/generated/emoji/emoji_codes.json`                                                                                                           |
| Common data       | `people.ts`, `stream_data.ts`, `sub_store.ts`, `user_groups.ts`, `message_store.ts`, `narrow_state.ts`                                                                                                                           |

## Tests

See "Frontend: `tools/test-js-with-node`" in `guides/testing.md`. For a new organization setting,
update `web/tests/lib/example_realm.cjs`; for a new event, add an example to
`web/tests/lib/events.cjs` and a test to `web/tests/dispatch.test.cjs`.
