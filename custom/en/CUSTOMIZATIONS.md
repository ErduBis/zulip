# Customization inventory

Records **the changes we make to Zulip's original code to implement our customizations**. New
files don't need to be listed one by one, but where one hooks into existing code (for example, a
line added to an existing URL table, setting, or registry), the hook point must be listed.

**Purpose**: When upgrading Zulip, check each entry: is the change still needed, and can it be
reapplied cleanly?

Maintained by the lead at commit time.

## Changes to original files

| ID  | File                                                                              | What changed                                                                                                                                                           | Why the original file had to change                                                                                                                                                           | Commits                                                            |
| --- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| C1  | `zerver/lib/onboarding.py`                                                        | Welcome Bot command names and list formatting are translatable; translated commands are recognized; replies use the user's own language                                | The command list was hard-coded English, so Chinese users couldn't use the commands                                                                                                           | i18n: Make hard-coded English strings translatable.                |
| C2  | `zerver/lib/reminders.py`                                                         | `poll` and `todo list` in reminders are marked for translation                                                                                                         | The English words were inserted into translated sentences                                                                                                                                     | i18n: Make hard-coded English strings translatable.                |
| C3  | `zerver/models/users.py`                                                          | “Plain text” in `EMOJISET_CHOICES` uses `gettext_lazy`; `emojiset_choices()` converts it to `str`                                                                      | The settings page takes the emoji theme labels from here; no migration is created                                                                                                             | i18n: Make hard-coded English strings translatable.                |
| C4  | `zerver/views/unsubscribe.py`, `templates/zerver/unsubscribe_success.html`        | Email type display names are translatable; the template checks the English key `email_type` for welcome emails                                                         | The display name appears in a sentence on the unsubscribe page; the template used it for a check that breaks once translated                                                                  | i18n: Make hard-coded English strings translatable.                |
| C5  | `web/templates/settings/playground_settings_admin.hbs`, `realm_domains_modal.hbs` | Input placeholder examples are marked for translation                                                                                                                  | The examples should suit Chinese users                                                                                                                                                        | i18n: Make hard-coded English strings translatable.                |
| C6  | `zerver/tests/test_tutorial.py`, `zerver/tests/test_signup.py`                    | Adds tests for Chinese commands, de-duplication and unsubscribing from welcome emails                                                                                  | Covers the behavior of C1 and C4                                                                                                                                                              | i18n: Make hard-coded English strings translatable.                |
| C7  | `zerver/lib/home.py`, `zerver/tests/test_home.py`                                 | Switch to the user's language before building the home page's initial state; adds a test                                                                               | The initial state has server-translated text (e.g., emoji theme names) that was built in the stale language from the browser cookie, so the first load after a language change showed English | i18n: Build the home page state in the user's language.            |
| C8  | `zproject/computed_settings.py`                                                   | Adds `"zcustom"` to `INSTALLED_APPS`                                                                                                                                   | Django only finds management commands and migrations in installed apps (D8)                                                                                                                   | zcustom: Generate a Chinese dev organization with populate_dev_zh. |
| C9  | `tools/rebuild-dev-database`                                                      | The dev database is generated by `populate_dev_zh -n400`                                                                                                               | provision's automatic dev database rebuild must also produce the Chinese organization; the test database still uses `populate_db --test-suite` (D11)                                          | zcustom: Generate a Chinese dev organization with populate_dev_zh. |
| C10 | `zerver/views/development/email_log.py`                                           | "Generate all emails" picks the member and administrator by role and invites to the new-channel announcements channel, instead of hard-coding hamlet, iago and Denmark | The dev organization has none of those names, so the original code returned a 500                                                                                                             | zcustom: Generate a Chinese dev organization with populate_dev_zh. |

## Custom API endpoints

| Endpoint | Method | Purpose | Introduced in |
| -------- | ------ | ------- | ------------- |
|          |        |         |               |

## Custom database migrations

| Migration | Contents | Introduced in |
| --------- | -------- | ------------- |
|           |          |               |
