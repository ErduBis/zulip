# Decision log

Each entry: date, what was decided, and why. Superseded decisions are not deleted; mark them
"Superseded" and point to the new decision.

## D1 Build on the 13.2 stable release (2026-11-20)

The customization branch `custom/13.x` is cut from the `13.2` tag.

**Why**: The result will run in production. A stable release can be deployed directly, and
later 13.x patch releases merge cleanly. Upgrade as a whole once 14.0 is released.

## D2 Development environment: WSL2 + SSH (2026-11-20)

The development environment is Ubuntu 24.04 in WSL2 (installed at `D:\WSL\Ubuntu`), with the code
at `/home/codyli/zulip`. Worker sessions run directly inside WSL through the Claude desktop app's
SSH connection "WSL" (`127.0.0.1:2222`, localhost only, key authentication only). WSL starts in
the background at logon and stays running.

**Why**: Zulip only supports Linux. Accessing WSL files from the Windows side is too slow (a
repository-wide search times out after 20 seconds, while `git grep` inside WSL takes about 0.2
seconds), so sessions need to run inside WSL.

## D3 Sessions share one directory; only the lead commits (2026-11-20)

Worker sessions share `/home/codyli/zulip`, with ownership divided by path; all git write
operations are done by the lead.

**Why**: The user chose a shared directory. The git index is shared, so several sessions
running `add`/`commit` at the same time would commit each other's changes.

## D4 Documenting custom APIs (2026-11-20, tentative)

Custom endpoints are documented in `zerver/openapi/zulip.yaml`, `API_FEATURE_LEVEL` is left
unchanged, and each endpoint is recorded in `CUSTOMIZATIONS.md`.

**Why**: Zulip's tests require every endpoint to have OpenAPI documentation, while the feature
level is upstream's version number; mixing our changes into it would conflict on upgrades.

## D5 Documentation in Chinese and English (2026-11-20)

All of our documentation lives under `custom/`, split by language into `custom/zh/` and
`custom/en/`, with identically named files and identical content. The Chinese version is
authoritative. AI sessions load only the Chinese development guide, through the root
`CLAUDE.md`.

**Why**: The user requires every document in both Chinese and English; loading both would
duplicate the session context.

## D6 Chinese translation workflow (2026-11-20)

Frontend and backend write only the English source text and mark it for translation;
integrations and brand owns the Chinese translations in `locale/zh_Hans/`, updating them with
`./manage.py makemessages -l zh_Hans` and `./manage.py compilemessages`; the lead checks the
translations when merging upstream.

**Why**: Without `-l`, `makemessages` changes the files of every language; changing only
`zh_Hans` keeps our changes focused and easy to check on upgrades. Tested: `-l zh_Hans` changes
only files under `locale/zh_Hans/`.

## D7 Development guides by role (2026-11-20)

Zulip development knowledge lives in `custom/zh/guides/` and `custom/en/guides/`, one guide per
role (plus one each for testing and deployment), with every path and function name checked
against the 13.2 code. `docs/` keeps only `docs/THIRDPARTY` (the third-party license list: `NOTICE`
refers to it and `tools/check-thirdparty` checks it).

**Why**: Worker sessions need essentials that match our roles and the current code; with one guide
per role, each session reads only its own.

## D8 Database migrations alongside upstream (2026-11-20)

- **New tables** go in our own Django app `zcustom/` (models and migrations both live there, with
  foreign keys to `Realm`, `UserProfile`, and so on). The backend creates it the first time it's
  needed, adds a `"zcustom"` line to `INSTALLED_APPS` in `zproject/computed_settings.py`, and
  records that in `CUSTOMIZATIONS.md`.
- Write a `zerver` migration only to **add fields to Zulip's existing tables** (for example, to
  hook into the `property_types` framework for organization settings). Name the file
  `<number>_custom_<description>.py`, numbered after the last migration at the time.
- When `zerver` has several leaf migrations after merging upstream:
  - If our migrations haven't been deployed to any server yet: move them after upstream's with
    `./tools/renumber-migrations`.
  - If they have been deployed: keep their names, generate a merge migration with
    `./manage.py makemigrations --merge zerver`, and rename it to
    `<number>_custom_merge_<upstream version>.py`.
- A deployed migration is never renamed, deleted, or edited.

**Why**: Django records which migrations have run by app and name, and orders them by their
dependencies. Migrations in a separate app never collide with upstream's numbers, and new tables
there don't need registering in Zulip's export table list (`zerver/lib/export.py` only checks
`zerver` and a few other apps), so fewer original files change; the `_custom_` prefix makes ours
easy to spot during merges. Renaming would make a server treat an already-applied migration as
new and run it again, so deployed migrations can only be reconciled with a merge migration.

## D9 Servers deploy from git (2026-11-20)

Servers deploy from `https://github.com/ErduBis/zulip.git`: the first install clones
`custom/13.x` and sets `git_repo_url` in `/etc/zulip/zulip.conf`; each later upgrade runs
`upgrade-zulip-from-git <commit ID>` on a commit already pushed to `origin` and verified on staging.
Servers get 8 GB of RAM. Steps are in `guides/deployment.md`.

**Why**: the user chose it. Deploying is one command, and the code directory on the server is a git
repository, so the deployed version can be checked directly. The frontend is built on the server,
and with less than 4.2 GiB RAM the upgrade script stops the server before the build, so servers get
enough memory.

## D10 Bilingual commit messages (2026-11-20)

- The title is English, in the form `subsystem: Summary.`.
- The body is Chinese first, then English, with the same content: the first Chinese paragraph is
  the title in Chinese, followed by the Chinese explanation; then the English explanation.
- Chinese lines are at most 35 characters, English lines at most 70.
- The last line is the `Co-Authored-By: …` trailer.

```text
i18n: Make hard-coded English strings translatable.

把写死的英文改成可翻译。

欢迎机器人的命令名等几处文字对中文用户显示为英文。……

Welcome Bot command names and a few other strings were shown in
English to Chinese users. ...

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

**Why**: the user asked for bilingual commit messages. The title stays English because the commit
message check (`.gitlint`) requires an uppercase English letter after the colon, and upstream's
titles are all English, which keeps them easy to compare when merging upstream.
