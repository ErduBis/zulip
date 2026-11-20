# Screenshot the development server

English version of `SKILL.md` (the Chinese version is the one loaded as the skill and is
authoritative).

Logs in to `http://localhost:9991` as a test user, opens the given page, and takes a screenshot;
then view the screenshot with the Read tool. Use it to see how UI changes actually look, including
the Chinese UI and the dark theme. Use it when only looking, without changing data; for checks
that change data by sending messages or changing settings on the page, use /visual-test.

```bash
cd ~/zulip
node .claude/skills/screenshot-dev/screenshot.mjs [options]
```

| Option                  | Default                          | Description                                                                     |
| ----------------------- | -------------------------------- | ------------------------------------------------------------------------------- |
| `--user <email>`        | `sunwukong@zulip.com`            | Test user to log in as (any user on the devlogin page)                          |
| `--path <path>`         | `/`                              | Page to open after logging in, e.g., `/#channels/3/devel`, `/#settings/profile` |
| `--out <file>`          | `/tmp/screenshot-dev-<time>.png` | Where to save the screenshot; the script prints this path last                  |
| `--lang <language>`     | user's setting                   | Temporarily switch the UI language; Chinese is `zh-hans`                        |
| `--dark`                | off                              | Temporarily switch to the dark theme                                            |
| `--width/--height`      | `1280` / `800`                   | Window size; use `--width 480` for phone width                                  |
| `--wait-for <selector>` | none                             | Wait for this element before taking the screenshot                              |
| `--element <selector>`  | none                             | Capture only this element                                                       |
| `--full-page`           | off                              | Capture the full page                                                           |

`--lang` and `--dark` apply only while the screenshot is taken; afterwards, that user's language
and theme are restored to their previous settings.

## Notes

- The development server must be running (see the "Environment" section of the development
  guide).
- 9991 uses the development database shared with the user. This script only logs in and browses,
  and changes no data apart from the two temporary settings above; when a check needs clicking
  buttons, sending messages, or changing settings, use `/visual-test` (separate test database).
- For screens that take several steps to reach, copy `screenshot.mjs` to `/tmp/` and adapt it;
  don't edit the copy in the repository.
- To compare before and after, take both screenshots and view them together; when unsure about
  alignment or spacing, use `--element` to capture and enlarge just that part.
