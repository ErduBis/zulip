# Chinese translation guide

For the "integrations and brand" role, which maintains `locale/zh_Hans/`. The basic three steps are
in the "Chinese translation" section of the development guide; this guide covers file formats, common
mistakes and terminology.

## The two translation files

| File                                   | Text it covers                                                                                                 | When it takes effect                             |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `locale/zh_Hans/translations.json`     | Web app: `$t` / `$t_html` in `web/src/`, `{{t}}` / `{{#tr}}` in `web/templates/*.hbs`                          | On browser refresh (read on every page load)     |
| `locale/zh_Hans/LC_MESSAGES/django.po` | Server: Python `_()` / `gettext_lazy` (including API errors), Jinja2 pages (login, signup, …), email templates | After `./manage.py compilemessages` builds `.mo` |

- `translations.json`: the key is the English source text (exactly), the value is the Chinese;
  `""` means untranslated and the UI shows English. `makemessages` rewrites the file (sorted keys,
  two-space indent); keep that format when editing by hand. Loaded via `zerver/lib/home.py` →
  `get_language_translation_data` in `zerver/lib/i18n.py`.
- `django.po`: the `#:` comment says which file a string comes from; long strings span several
  lines that are joined end to end. `.mo` files are generated, not in git, and must be rebuilt after
  every `.po` change.
- When the English source is wrong (spelling, capitalization, wording): have the role that owns the
  source change the English, then rerun `makemessages`; the JSON keys stay as generated.

## What makemessages does

`./manage.py makemessages -l zh_Hans` updates both files:

- New strings in the code are added with empty values; existing translations are kept.
- Strings no longer in the code are removed. **Change one character of the English and the old
  translation is gone**; retranslate against the new source.
- In `django.po`, gettext guesses a similar old translation for new strings and marks it
  `#, fuzzy`. **Fuzzy entries are not compiled into the UI**: check each one, fix the `msgstr`, then
  delete the `#, fuzzy` and `#| msgid ...` comment lines.

Finding work:

```bash
jq -r 'to_entries[] | select(.value == "") | .key' locale/zh_Hans/translations.json   # frontend untranslated
msgattrib --untranslated --no-obsolete locale/zh_Hans/LC_MESSAGES/django.po            # backend untranslated
msgattrib --only-fuzzy --no-obsolete locale/zh_Hans/LC_MESSAGES/django.po              # backend to check
```

Handle only the strings this task touches (the "Copy" section of the design spec is authoritative);
afterwards, check `git diff locale/zh_Hans/` for unintended changes.

## Placeholders and tags

- Keep `{name}`, `{count}` verbatim; you may move them; the word inside the braces is not translated.
- `z-` custom tags such as `<z-link>…</z-link>` and `<z-user></z-user>`: keep the tags as they are and
  translate only the text between them; you may move them. Adding tags is not allowed.
- Only the simple tags `b`, `code`, `em`, `i`, `kbd`, `p`, `strong` are allowed, without attributes
  (`default_html_elements` in `web/src/i18n.ts`).
- In `django.po`, keep `%(name)s` (`python-format`) and `{name}` (`python-brace-format`) verbatim;
  leave HTML attributes such as `<a href="%(url)s">` untouched to the character. `compilemessages`
  checks that `%(name)s` placeholders match; an error there usually means a broken placeholder. To
  check on its own: `msgfmt --check-format -o /dev/null locale/zh_Hans/LC_MESSAGES/django.po`.
- `translations.json` is JSON: write quotes as `\"`. Using full-width quotes “” in Chinese avoids
  escaping; also avoid the ASCII apostrophe `'`, which is an escape character in ICU message format.

## Plurals and select

The frontend uses ICU message format:

```json
{
  "At least {count, plural, one {# message} other {# messages}} will be moved.": "至少会移动 {count, plural, one {# 条消息} other {# 条消息}}。"
}
```

- Keep the `{count, plural, ...}` structure and the `one` / `other` keywords; translate only the text
  inside the braces; `#` stands for the number.
- Chinese only uses the `other` branch (a count of 1 also uses `other`), so `other` must be right;
  give `one` the same text. Exact-match branches such as `=0 {…}` still apply and need their own
  translation.
- `{x, select, a {…} other {…}}`: likewise, translate only the text in each branch.
- Plurals in `django.po`: the header says `nplurals=1`, so fill in only `msgstr[0]`.

## Checking in the UI

- Web app: `/screenshot-dev --lang zh-hans`, or set the test user's language to Simplified Chinese.
- Logged-out pages: prefix the path with the language, e.g., `http://localhost:9991/zh-hans/login/`.
- Emails: emails sent by the dev environment are at `http://localhost:9991/emails/`.
- What to look for: truncated text, awkward line breaks, unreplaced placeholders (a visible `{name}`
  means the translation is broken), buttons stretched by long text. If backend translations don't
  change after `compilemessages`, ask the lead to have the user restart `run-dev`.

## Style

- Address the user as “您”; most English “we” is dropped, rewritten as a subjectless sentence or as
  the action (“Still no email? We can resend it” → “仍然没有收到邮件？点击重新发送”).
- Sentence-final punctuation follows the English: use “。” where the English has a period; buttons,
  menu items, headings and labels get none. English exclamation marks read too strongly in Chinese;
  usually use “。”.
- Use full-width punctuation: ，。？：；“”（）.
- Put one ASCII space between Chinese and English words, numbers or placeholders: “{count} 条消息”,
  “API Key 无效”.
- Pair numbers with the right measure word: 条消息, 个话题, 位用户, 个频道.
- Prefer meaning over literal wording, phrased the way Chinese software says it; a setting labeled
  “I want …” becomes “开启……”.
- Messages sent by the backend (Welcome Bot, notifications, etc.): a single line break is replaced
  with a space, which becomes a stray space in Chinese, so write each paragraph on one line and
  separate paragraphs with a blank line.
- Syntax such as `#**channel>topic**` and `@**user**` needs a space or line break before it; right
  after full-width punctuation (such as “：”) it doesn't render.

## Glossary

Based on the most common wording in the existing translations; new translations follow this table.
When an old translation disagrees with it, make it consistent only in the UI this task touches, and
list the change in your report.

| English                               | Chinese                    | English                             | Chinese           |
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

Translate “Narrow to …” as “搜索……” or “筛选……” depending on context.
