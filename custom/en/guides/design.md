# Interaction design guide

For the interaction design role. The spec format and the UI checklist are in the development guide;
this guide covers the design conventions that make a spec fit Zulip, and how to accept an
implementation by screenshots.

## Principles

- **Start from what exists**: when Zulip already has a similar interaction, design after it and
  name the screen and component you reuse in the spec's "References". Design a new pattern only when
  nothing fits, and list it as an open question.
- **The UI explains itself**: if a feature needs long instructions to use, change the flow or the UI
  text first.
- **Real time**: Zulip pushes data changes live to every open page; the spec says what other tabs
  and other users see change.
- **Minimal interruption**: put new prompts where the user is already working; to announce a new
  feature, use a one-time notice (see the table below).

## Where to look at existing components

- Component samples on the dev server: `http://localhost:9991/devtools/buttons/`,
  `/devtools/banners/`, `/devtools/inputs/`; other dev tools are linked from `/devtools/`.
- Find a similar feature in the app, capture it with `/screenshot-dev`, and attach it in the spec's
  folder as a reference.
- To find which component a piece of UI uses: `git grep 'English text on screen' web/templates web/src`.

Refer to components by the names below in the spec, so the frontend can map them straight to code:

| Name            | Purpose                                                                                    | Code                                                                                                                                 |
| --------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Button          | Variant solid / subtle / text × intent brand / neutral / info / success / warning / danger | `web/templates/components/action_button.hbs`; icon-only `icon_button.hbs`                                                            |
| Banner          | In-page notice, same intents, may have buttons and a close button                          | `web/templates/components/banner.hbs`; above the compose box `web/src/compose_banner.ts`; top of the page `web/src/navbar_alerts.ts` |
| Dialog          | Title + content + submit/cancel; default buttons "Save changes" / "Cancel"                 | `web/src/dialog_widget.ts`                                                                                                           |
| Confirm dialog  | Second confirmation, default button "Confirm"; danger style for dangerous actions          | `web/src/confirm_dialog.ts` (`dangerous_action`)                                                                                     |
| Popover menu    | Action menu opened from an icon                                                            | `web/src/popover_menus.ts`                                                                                                           |
| Tooltip         | Hover explanation, keyboard shortcut hint                                                  | `web/src/tippyjs.ts`, `web/templates/tooltip_templates.hbs`                                                                          |
| Dropdown        | Searchable single-choice list                                                              | `web/src/dropdown_widget.ts`                                                                                                         |
| Tab switcher    | Switching views within one area                                                            | `web/src/components.ts`                                                                                                              |
| Input pills     | Entering and picking several users, channels, user groups                                  | `web/src/input_pill.ts`, with typeahead `web/src/typeahead_helper.ts`                                                                |
| List / table    | Long list with search and sorting; empty state                                             | `web/src/list_widget.ts`, `web/templates/empty_list_widget_for_list.hbs`, `..._for_table.hbs`                                        |
| Undo notice     | Brief notice after an action, with undo (e.g., "Undo mute")                                | `web/src/feedback_widget.ts`                                                                                                         |
| Inline status   | "Saved" or the failure reason, shown in place                                              | `web/src/ui_report.ts`                                                                                                               |
| One-time notice | New-feature intro shown once per user (banner, modal or tooltip)                           | `ONE_TIME_NOTICES` in `zerver/lib/onboarding_steps.py`, `web/src/onboarding_steps.ts`                                                |

Icons: existing icons are in `web/icons/` (the file name is the icon name; class
`zulip-icon-<file name>`); when none fits, pick one from Lucide (lucide.dev) and give its name in the
spec.

## Settings page conventions

- **Personal settings**: saved immediately on change, with "Saving" / "Saved" next to the control
  (`web/src/settings_ui.ts`).
- **Organization settings**: each subsection shows "Save changes" / "Discard" buttons once modified
  (`web/templates/settings/settings_save_discard_widget.hbs`).
- **Users without permission**: the control is shown disabled, with a tooltip giving the reason,
  e.g., "Only organization administrators can edit this setting." Write that tooltip text in the spec.

## UI text

- **Sentence case**: capitalize only the first word and proper nouns: "Channel settings", not
  "Channel Settings"; write acronyms in their standard form: URL, API, ID.
  `./tools/check-capitalization` checks every string marked for translation; the exception list is
  `IGNORED_PHRASES` in `tools/lib/capitalization.py` (the view names "Inbox" and "Recent
  conversations" are capitalized mid-sentence too).
- **Terms**: channel, topic, direct message (DM), organization, user group, bot. "realm" must not
  appear in the UI (the check script fails on it). Chinese equivalents are in the glossary in
  `custom/en/guides/translation.md`.
- **Whole sentences**: one sentence is one string, with its final punctuation inside the string; a
  sentence with a variable is written whole, like "Deactivate {name}?", never assembled from pieces.
- **Counts**: when an icon plus a number can say it, skip sentences with plurals; when a plural is
  needed, write the English as "{count, plural, one {# message} other {# messages}}".
- **Buttons**: verbs that state the result ("Save changes", "Archive channel"); a confirm dialog's
  submit button names the specific action; irreversible actions use the danger style and the text
  states the consequence.
- **Voice**: address the user as "you"; don't use "we" for Zulip.
- **Length**: Chinese is usually shorter than English, Russian or German longer; layouts must
  accommodate varying text length rather than being sized to the English.

## Theme, font size and width

- **Theme**: users choose light, dark or follow the system. Colors are defined in pairs in
  `web/styles/app_variables.css` (`light-dark(light value, dark value)`). In the spec, specify a
  color as "same as <existing element>" or by variable name; a new color comes with its dark value.
- **Information density**: users can adjust font size (16px default, 14px compact) and line height;
  layouts scale with font size, so check both.
- **Width**: below about 1200px the right sidebar collapses, below about 768px the left sidebar too
  (scaled with font size); breakpoints are defined in `web/src/css_variables.ts`. There is also a
  "full-width layout" setting.
- **Time**: displayed times follow the user's 12/24-hour setting.
- **Animation**: animations are turned off when the system's "reduce motion" is on, so information
  never depends on animation alone.

## Keyboard and accessibility

- Every action can be done with the keyboard alone: Tab order matches visual order; Enter submits or
  activates; Esc closes dialogs and popovers, and focus returns to the element that opened them. Put
  this in the spec's "Adaptation" section.
- **Keyboard shortcuts**: the current list is `web/templates/keyboard_shortcuts.hbs` (opened with `?`
  in the app), handled in `web/src/hotkey.ts`. Check a new shortcut against the list for conflicts;
  write keys with non-Mac names (Ctrl, Enter); Macs show the equivalent keys automatically
  (`has_mac_keyboard` in `web/src/common.ts`). Buttons with a shortcut show it in their tooltip.
- **Icon-only buttons** must have a tooltip, and their screen-reader text (`aria-label`) matches the
  tooltip; decorative icons next to text are hidden from screen readers. Put these tooltip texts in
  "Copy".
- **Contrast** per WCAG AA: 4.5:1 for body text, 3:1 for large text and icons, in both light and dark
  themes; states are never distinguished by color alone, add an icon or text.
- Informative images need alt text, written in "Copy".

## Cases specs often miss

- The message area's views: topic, channel, Combined feed, direct messages; once with a channel
  message and once with a direct message.
- Both compose box sizes (normal and expanded).
- Roles: owner, administrator, moderator, member, guest; for web-public channels, also logged-out
  spectators.
- Input: empty, invalid, very long (once in Chinese, once in English).
- Coexistence: shown together with other banners; messages muted or collapsed; topic marked as
  resolved; content edited or deleted.
- Menu items hidden from some users: hiding them leaves no stray separators.

## Accepting by screenshots

- **Before screenshots**: while writing the spec, capture the current state with `/screenshot-dev`,
  store it in `custom/zh/design/<feature-name>/`, and record the parameters in the spec (`--user`,
  `--path`, `--width/--height`, `--lang`, `--dark`); at acceptance, capture the after state with the
  same parameters.
- **Precise comparison**: both shots show the same UI state (same user, same page, same scroll
  position) at the same pixel size; for details, capture the same element with `--element`.
- **Cover every affected state**: e.g., for a new dropdown setting, capture the setting in its page,
  the open dropdown, the disabled state with its tooltip for users without permission, and the
  effect of each value.
- **Keep enough context**: include the surrounding UI so you can tell whether the new element fits
  its neighbors; when shared styles changed, the frontend provides the `git grep` results for the
  selectors and you capture each place.
- Use still screenshots; capture an interaction as an ordered series of screenshots with
  `/visual-test`.
- In your report, compare side by side in a table:

  ```markdown
  | Before                   | After                   |
  | ------------------------ | ----------------------- |
  | ![](settings-before.png) | ![](settings-after.png) |
  ```

- By default capture at least: Chinese and English UI, widths 1280 and 480; add the dark theme when
  colors changed.
