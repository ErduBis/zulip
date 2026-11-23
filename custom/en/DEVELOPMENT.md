# Zulip customization: development guide

This repository is a **customization** of Zulip 13.2 (self-hosted, with our own changes).

- Code: `/home/codyli/zulip` (WSL2 Ubuntu 24.04)
- Branch: `main` (cut from the `13.2` tag; all customizations live here; refer to Zulip's own code
  as `upstream/main`, `upstream/13.x` and release tags, see D13)
- Remotes: `origin` = `ErduBis/zulip` (our fork), `upstream` = `zulip/zulip` (official)

## Environment

```bash
cd ~/zulip && source .venv/bin/activate   # required for all ./tools/ and ./manage.py commands
```

- **Development server**: `./tools/run-dev`, served at `http://localhost:9991`; log in at
  `http://localhost:9991/devlogin/` (no password, just pick a test user).
  It is usually already running in the user's terminal; **don't start a second one**. Check first:
  `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9991/devlogin/`
- **Tests and checks** (most take minutes; run them in the background):
  - Backend: `./tools/test-backend zerver.tests.test_<module>` (only the relevant modules, not
    the whole suite)
  - Frontend: `./tools/test-js-with-node` (the full suite is fast too; can take specific files)
  - Lint: `./tools/lint <changed files> </dev/null` (includes mypy, TypeScript, prettier). Keep
    the trailing `</dev/null`: without a terminal, its commit message check waits for input
    forever. It only checks files tracked by git: check new files separately as described in
    "Lint and type checking" in the testing guide, and list them in your report.
- **Search code** with `git grep`.
- **sudo**: when system packages or system configuration need changing, stop and hand it to the
  lead. `sudo apt-get` and `sudo apt` need no password; the user enters the password for other
  sudo commands.
- If a tool says provision is outdated, run `./tools/provision`; don't bypass it with
  `--skip-provision-check`.

## Roles and path ownership

Several sessions **share this one directory**; each path belongs to exactly one role.

| Role                       | Responsible for                                                          | Paths it may change                                                                                                                                        |
| -------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Lead**                   | Breaking down requirements, architecture, review, commits, upstream sync | `CLAUDE.md`, `README.md`, `.claude/`, `custom/` (except the two `design/` folders), and **all git write operations**                                       |
| **Interaction design**     | Interaction flows, UI states, copy, usability, design acceptance         | `custom/zh/design/`, `custom/en/design/`                                                                                                                   |
| **Backend**                | Data model, business logic, REST API, permissions, real-time events      | `zerver/` (except `zerver/webhooks/` and `zerver/lib/integrations.py`), `zproject/`, `analytics/`, `corporate/`, `confirmation/`, `api_docs/`, `zcustom/`  |
| **Frontend**               | Web UI, interactions, styles, templates                                  | `web/`, `templates/` (except `templates/zerver/integrations/`)                                                                                             |
| **Environment and ops**    | Dev environment, dependencies, deployment, backups                       | `tools/`, `scripts/`, `puppet/`, `.github/`, and the dependency files `pyproject.toml`, `uv.lock`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` |
| **Integrations and brand** | Bot and webhook integrations, Chinese translation, brand assets          | `zerver/webhooks/`, `zerver/lib/integrations.py`, `templates/zerver/integrations/`, `locale/zh_Hans/`, `static/images/`                                    |

Each role's tests go with its code: backend writes `zerver/tests/`, frontend writes `web/tests/`.
To add a dependency, ask the lead; environment and ops changes the dependency files. Any role may
create temporary test files starting with `_claude_` under `web/e2e-tests/` (used by
`/visual-test`); these files are ignored locally and never committed. To change a path not listed
here, ask the lead first.

### Interaction design

Interaction design writes design specs only and doesn't change code. Each feature with UI gets
one spec, in both languages under the same name: `custom/zh/design/<feature-name>.md` and
`custom/en/design/<feature-name>.md`. A spec covers:

1. **Goal**: whose problem it solves, in what situation.
2. **Entry points and flow**: where the user starts, and what they do and see at each step.
3. **Screens and states**: layout and elements of each screen; what it looks like when normal,
   empty, loading, failed, without permission, and with overly long content.
4. **Copy**: the English source text and Chinese translation of every piece of UI text (Zulip's
   UI uses English as the source language; Chinese comes from the translation files).
5. **References**: which existing Zulip components and interactions it reuses, for consistency.
6. **Adaptation**: wide and phone widths, light and dark themes, keyboard use.
7. **Open questions**: trade-offs the user needs to decide, with the options and their costs.

Annotated screenshots or HTML prototypes may be attached, in a subfolder with the same name under
`custom/zh/design/`. Frontend starts implementing only after the user approves the spec. Once
implemented, interaction design takes screenshots of the actual UI (see "UI checklist"), checks
them item by item against the spec, and reports deviations to the lead.

## How to work

Every task goes **understand → plan → implement → verify**.

1. **Understand**: read the code you'll change and your role's guide (see "Documentation"), and use
   `git grep` to find similar implementations in the codebase to follow. Don't start until you
   can explain why your change is the right one.
2. **Plan**: when requirements, interfaces, or the data model aren't settled, first lay out your
   understanding and how you intend to change things, and get confirmation before writing code.
3. **Implement**: see "Code requirements" below.
4. **Verify**: relevant tests and lint must pass; UI changes must be checked in screenshots of
   the actual result (see "UI checklist"). Think about where it could break and how to show it
   doesn't.

**Fixing bugs**: reproduce and confirm the cause first, then fix it; add a test that would have
caught the bug; check whether the same problem exists elsewhere.

### Stop and ask the lead when

- Security is involved (authentication, permissions, user input reaching SQL or HTML)
- A database migration is needed
- One change has to touch several subsystems at once
- The performance impact is unclear
- Requirements, interfaces, or the data model aren't settled
- Existing tests fail for unclear reasons
- The development database would be wiped (`./tools/rebuild-dev-database`,
  `./manage.py populate_db`)
- A design or interaction trade-off is needed — lay out the constraint and the options rather
  than deciding yourself, and don't remove or hide existing features or change interaction
  patterns on your own

## Code requirements

- **Stay consistent with the surrounding code**; follow existing patterns.
- **Clear, greppable names**: functions, arguments, variables, and tests should say what they're
  for.
- **Don't duplicate code**, especially permission checks and subtle logic.
- **Comments explain "why"**, not what the code does; each comment on its own line; match the
  comment density of nearby code. Don't describe "what this change did / which bug it fixed" in
  comments; that belongs in the commit message. Don't put line numbers in comments; name the
  function.
- **Leave no** debugging code, commented-out code, or temporary TODOs.
- User-visible text must be **marked for translation**; error messages must say what's wrong and
  what to do.
- No hard-coded secrets or credentials. Watch for **XSS** in UI changes and check **access
  control** in server changes.
- Python: complete type annotations, with a comment justifying any `Any`; no string-built SQL;
  avoid N+1 queries.
- Frontend: use `const`/`let`; use event delegation, not `onclick` attributes; use class/ID
  selectors.

### Tests

- Test what you change; new code needs test coverage. To check the files you changed for missing
  coverage, use `/fix-backend-coverage` for the backend and `/debug-node-coverage` for the
  frontend. When using `/fix-backend-coverage`, drop `--skip-provision-check` from its commands;
  when it calls for changing `tools/test-backend`, hand that to the lead.
- Test the behavior that matters, not internal implementation; assert that state actually
  changed, not just "success".
- Cover error paths too. Tests must run offline (use fixtures for external services).
- See `zerver/tests/test_example.py` for patterns.

### UI checklist

**How to look at the UI**:

- Looking only, without changing data: use `/screenshot-dev` to log in to `localhost:9991` and
  take a screenshot, then view it with Read. Add `--lang zh-hans` for the Chinese UI and `--dark`
  for the dark theme.
- Checks that click buttons, send messages, or change settings on the page: use `/visual-test`.
  It runs on a separate test server (port 9981) and test database, leaving the user's development
  data untouched. `./tools/test-js-with-puppeteer`, `./tools/test-api`, and
  `./tools/test-help-documentation` use the same test server. **Only one session at a time may
  use it**; ask the lead before starting.

Frontend self-checks before handing off, and interaction design accepts, against this list:

- Consistent with neighboring and similar elements (alignment, spacing, fonts, colors)
- Every state works: hover, selected, disabled, empty, overly long content
- Light and dark themes (when colors changed)
- Wide screen, laptop, and phone widths
- **Chinese UI**: Chinese fonts render properly; mixed Chinese and English text doesn't truncate
  or misalign
- Checked as a user with and without permission (when permissions are involved)
- No unintended effect on other pages (`git grep` the CSS selectors you changed)

## Chinese translation

Zulip's UI uses English as the source text; Chinese translations live in `locale/zh_Hans/`:
frontend text in `translations.json`, backend text in `LC_MESSAGES/django.po`.

1. **Frontend, backend**: write UI text in English and mark it for translation. Don't change
   `locale/`.
2. **Integrations and brand**: run `./manage.py makemessages -l zh_Hans` to add new text to the
   Chinese translation files, fill in the Chinese translations (following the copy in the
   interaction spec), then run `./manage.py compilemessages`. Always use `-l zh_Hans`, so other
   languages' files stay unchanged.
3. **Lead**: when merging upstream, check `locale/zh_Hans/` to make sure our translations are
   still there; after merging, rerun the two commands from step 2 and check the Chinese UI in
   screenshots.

## Documentation

All of our documentation lives under `custom/`, each document in both Chinese and English:
identically named files with identical content in `custom/zh/` and `custom/en/`. **The Chinese
version is authoritative**; when you change one version, update the other in the same change.
Skills we write live in `.claude/skills/<name>/`: `SKILL.md` is in Chinese (it is the one
loaded), and `SKILL.en.md` in the same folder is the English version.

| Document            | Contents                                                                          |
| ------------------- | --------------------------------------------------------------------------------- |
| `DEVELOPMENT.md`    | Development guide (this file)                                                     |
| `DECISIONS.md`      | Architecture and process decision log                                             |
| `CUSTOMIZATIONS.md` | Changes to Zulip's original code for our customizations (checked on each upgrade) |
| `design/`           | Interaction design specs                                                          |
| `guides/`           | Zulip development guides by role (see the table below)                            |

Each role reads its own guide before starting work:

| Guide                    | Readers                                   | Contents                                                                                                       |
| ------------------------ | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `guides/backend.md`      | Backend                                   | Code map, writing endpoints, adding settings, real-time events, migrations, caching, and more                  |
| `guides/frontend.md`     | Frontend                                  | Initial state and events, calling endpoints, templates, translation markup, existing components, CSS, and more |
| `guides/testing.md`      | Backend, frontend, integrations and brand | Running tests, writing tests, test data, lint and type checking                                                |
| `guides/integrations.md` | Integrations and brand                    | Webhook integrations, bots, brand assets                                                                       |
| `guides/translation.md`  | Integrations and brand                    | Translation file formats, placeholders and plurals, style, glossary                                            |
| `guides/design.md`       | Interaction design                        | Zulip design conventions, existing components, UI text rules, screenshot acceptance                            |
| `guides/deployment.md`   | Environment and ops, lead                 | Deployment options, installation, server configuration, upgrades, rollback, backups, operations                |

The root `CLAUDE.md` only imports the Chinese development guide; `README.md` is the bilingual
project overview.

## Collaboration rules

1. **Change only your own paths.** If you need another role's help (for example, frontend needs a
   new endpoint), stop and tell the lead what you need instead of crossing over.
2. **Only the lead does git write operations.** Worker sessions must not `commit`,
   `switch`/`checkout`, `stash`, `reset`, `rebase`, or `push`, and must not `git add` (the index is
   shared). Read-only commands (`status`, `diff`, `log`, `grep`, `show`) are fine.
3. **Only the backend session generates database migrations**, and it confirms the data model
   design with the lead first.
4. **The lead breaks down cross-layer features**, in this order: interaction design writes the
   spec and the user approves it → the lead defines the interface contract (URLs, parameters,
   responses, event formats) → backend implements → frontend implements per the spec →
   interaction design accepts. Features without UI skip the two design steps.
5. **The UI follows the interaction spec.** When frontend hits a case the spec doesn't cover, stop
   and ask rather than improvising.
6. **Change Zulip's original files as little as possible.** Prefer configuration, new files, and
   new functions; when an original file must change, keep the change focused and minimal, without
   refactoring or reformatting unrelated code — every Zulip upgrade has to reapply these changes.
7. **New or changed API endpoints**: document them in `zerver/openapi/zulip.yaml` (Zulip's tests
   enforce this), and leave `API_FEATURE_LEVEL` unchanged.

## Reporting when a task is done

Report to the lead when done (the lead reviews and commits based on this). Reports and replies are
always in Chinese:

1. **Files changed**: list new and modified files separately.
2. **Zulip original files touched**: for each, what changed and why it couldn't be avoided.
3. **Verification**: which tests and lint ran, with results; how UI changes were looked at.
4. **Anything unfinished, uncertain, or risky**.

Interaction design reports: when delivering a spec, give the spec file paths and open questions;
when accepting, list each deviation between the implementation and the spec.

## Lead responsibilities

- Break requirements into tasks, assign the role and path scope, and state acceptance criteria.
- Review worker sessions' changes, commit them to `main`, and push.
- Record every change to Zulip's original files in `CUSTOMIZATIONS.md`.
- Record important decisions in `DECISIONS.md`.
- Sync with upstream regularly: merge 13.x patch releases as they come; plan major upgrades
  separately. When merging, check translations per step 3 of "Chinese translation"; when
  upstream changes files we have deleted, keep them deleted (`git rm`). Deployment steps are in
  `guides/deployment.md`. After merging, compare upstream's changes to
  `zilencer/management/commands/populate_db.py` for new dev data worth porting to `zcustom/` (D11).
  When upstream changes a file listed in `IMPORTANT_FILES` in `zerver/lib/test_fixtures.py`, the
  next `./tools/provision` wipes and rebuilds the dev database, so tell the user before running it.

### Commit guidelines

- **One commit, one idea**, complete and passing tests on its own; tests go in the same commit as
  the code.
- Moving or splitting files goes in a separate commit from changing their contents.
- Don't fix an earlier commit's mistake with a later commit; amend the original (see
  `/git-rebase`).
- Commit messages are bilingual (decision D10): an English title in the `/commit-message` format
  `subsystem: Summary.`, then a Chinese body (its first paragraph is the title in Chinese) followed
  by the same in English, saying what the diff can't show.
