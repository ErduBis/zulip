# Deployment and upgrades

How to deploy our Zulip fork (the `custom/13.x` branch of `ErduBis/zulip`) to our own servers, and
keep merging upstream releases and redeploying. Audience: the environment and ops session, and the
lead.

Server commands below run as root on the production server (those starting with `su zulip -c` run
as the `zulip` user). `$D` is the current deployment directory; run
`D=/home/zulip/deployments/current` first.

## Server requirements

- A **dedicated** physical machine or VM: the installer uses `apt` to install nginx, PostgreSQL,
  RabbitMQ, Redis, memcached, etc. and configures them its own way.
- OS: Ubuntu 22.04 / 24.04 / 26.04, Debian 12 / 13 (`scripts/lib/supported-os` is authoritative);
  x86-64 or aarch64. On Ubuntu, enable the universe repository (`add-apt-repository universe`).
  Pick the newest supported release to postpone OS upgrades.
- At least 2 GB RAM; with less than 5 GB RAM, swap is mandatory (2 GB recommended), otherwise the
  installer exits. 100+ users: 2 CPUs, 4 GB; 25+ daily actives: 4 GB recommended, 100+: 8 GB.
- Upgrades build the frontend on the server: with less than 4.2 GiB RAM (a nominal 4 GB machine
  falls short too) the server is stopped before the build and downtime is longer, so pick an 8 GB
  size.
- Disk: at least 10 GB free (about 25 GB total), on SSD. The database needs roughly 10 GB per 1M
  messages.
- Network: inbound 443 (80 optional, it only redirects to HTTPS); firewall off 4369 (RabbitMQ's
  epmd); outbound 80/443 (link previews, push notifications; GitHub, npm, PyPI, and the OS package
  repositories during installs and upgrades) and SMTP (usually 587).
- A DNS hostname (this becomes `EXTERNAL_HOST`) and a working SMTP account for outgoing email.

## Deployment method

Servers deploy straight from our GitHub repository (decision D9): the first install clones
`custom/13.x`, and each later deploy runs `upgrade-zulip-from-git` on a commit already pushed to
`origin`. The frontend is built on the server. The version shown in the UI comes from
`git describe` (e.g., `13.2-4-gceb0b030c9`).

## First install

```bash
apt install git
git clone -b custom/13.x https://github.com/ErduBis/zulip.git zulip-server-git
./zulip-server-git/scripts/setup/install --certbot --email=ADMIN_EMAIL --hostname=HOSTNAME
```

After installing, set the repository URL in `/etc/zulip/zulip.conf` (otherwise later upgrades fetch
from the official repository by default):

```ini
[deployment]
git_repo_url = https://github.com/ErduBis/zulip.git
```

Installer options (`scripts/lib/install --help`):

- `--certbot`: obtains a Let's Encrypt certificate and renews it automatically; the server must be
  reachable from the Internet. `--self-signed-cert`: self-signed certificate, for testing or behind
  a reverse proxy. Mutually exclusive.
- `--postgresql-version=N`: default 18; must match the source when restoring a backup.
- `--push-notifications`: registers with the official mobile push notification service (prompts to
  accept its terms of service); without it, no registration.
- `--no-init-db` (existing database), `--no-overwrite-settings` (keep existing `/etc/zulip`),
  `--no-dist-upgrade` (skip the initial `apt-get dist-upgrade`).

The installer is idempotent: fix the cause of a failure and rerun it; the log is
`/var/log/zulip/install.log`. It creates the `zulip` user, `/home/zulip/deployments/` (`current`
points to the running version), and the config under `/etc/zulip/`, initializes the database, and
finally prints a one-time organization creation link. Configure outgoing email first (next section).

```bash
su zulip -c "$D/manage.py generate_realm_creation_link"  # regenerate the link
su zulip -c "$D/manage.py send_test_email you@example.com"  # verify outgoing email
```

## Server configuration

| File                            | Contents                                        | After editing, run (`scripts/` in the current deployment) |
| ------------------------------- | ----------------------------------------------- | --------------------------------------------------------- |
| `/etc/zulip/settings.py`        | Application (Django) settings, self-documenting | `scripts/restart-server` (as zulip)                       |
| `/etc/zulip/zulip-secrets.conf` | Secrets and passwords (e.g., `email_password`)  | Same                                                      |
| `/etc/zulip/zulip.conf`         | System-level config (INI, read by puppet)       | `scripts/zulip-puppet-apply` (as root)                    |

```bash
su zulip -c "$D/scripts/restart-server"
$D/scripts/zulip-puppet-apply      # lists changes and asks first; -f doesn't ask, --noop only previews
$D/scripts/get-django-setting NAME # show the effective value of a setting
```

- Common `zulip.conf` keys: `[machine] puppet_classes` (single host: `zulip::profile::standalone`);
  `[deployment] git_repo_url`, `deploy_options`; `[application_server] http_only` (when a reverse
  proxy forwards over HTTP), `nginx_listen_port`; `[loadbalancer] ips` (trust the proxy's
  `X-Forwarded-*`); `[postgresql] backups_directory`. Booleans are `true`/`false`.
- Puppet-managed system config files (e.g., nginx config) are rewritten on every upgrade. Local nginx
  extensions go into the include directories: `/etc/nginx/conf.d/` (http context),
  `/etc/nginx/zulip-include/app.d/` (public server context).
- Certificates: besides `--certbot`, put the certificate at `/etc/ssl/private/zulip.key` and
  `/etc/ssl/certs/zulip.combined-chain.crt` (must include the full intermediate chain), or later run
  `$D/scripts/setup/setup-certbot --email=ADMIN_EMAIL HOSTNAME`.
- Changing the hostname: change `EXTERNAL_HOST` (extra names go in `ALLOWED_HOSTS`), then restart.

Optional features are all configured in `/etc/zulip/settings.py` (template
`zproject/prod_settings_template.py`):

- Outgoing email: `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_PORT`, `EMAIL_USE_TLS`,
  `NOREPLY_EMAIL_ADDRESS`; password as `email_password` in `zulip-secrets.conf`.
- Login methods: `AUTHENTICATION_BACKENDS`, plus `AUTH_LDAP_*`, `SOCIAL_AUTH_*` (Google, GitHub,
  GitLab, SAML, OIDC, etc.), `JWT_AUTH_KEYS`.
- Mobile push: `ZULIP_SERVICE_PUSH_NOTIFICATIONS`, `ZULIP_SERVICE_SUBMIT_USAGE_STATISTICS`, then
  `su zulip -c "$D/manage.py register_server"`.
- File storage: default `LOCAL_UPLOADS_DIR = "/home/zulip/uploads"`; for S3, `S3_AUTH_UPLOADS_BUCKET`,
  `S3_AVATAR_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`; size limit `MAX_FILE_UPLOAD_SIZE`.
- Email gateway: `EMAIL_GATEWAY_PATTERN`, `EMAIL_GATEWAY_*`; external database:
  `REMOTE_POSTGRES_HOST` etc.
- Video calls: `JITSI_SERVER_URL`, `VIDEO_ZOOM_*`, `BIG_BLUE_BUTTON_URL`; error reporting:
  `SENTRY_DSN`.
- Other: `INLINE_IMAGE_PREVIEW`, `RATE_LIMITING_RULES`, `PASSWORD_MIN_LENGTH`,
  `TERMS_OF_SERVICE_VERSION` + `POLICIES_DIRECTORY` (`/etc/zulip/policies` recommended, so it's
  included in backups).

## Upgrades: merge upstream, then deploy

### 1. Merge upstream in the dev environment (lead)

1. `git fetch upstream --tags`, then on `custom/13.x` run `git merge <new tag>` (e.g., `13.3`).
2. Resolve conflicts by checking `custom/en/CUSTOMIZATIONS.md` item by item; check translations per
   step 3 of "Chinese translation" in the development guide.
3. Check migrations: when an upstream migration and one of ours both become leaf nodes, hand it to
   the backend session; migrations already applied in production keep their names.
4. Run the relevant tests and lint, push to `origin`.

For a major version (e.g., 14.x), merge the latest maintenance release of that series; before
upgrading, read the "Upgrade notes" in upstream's release notes for each version, and after merging,
update the server's `settings.py` against the new `zproject/prod_settings_template.py` (see below).

### 2. Pre-upgrade checklist

- Read the upgrade notes for every version being crossed (expensive migrations, changed system
  requirements).
- A fresh backup exists (see "Backups and restore") and has been copied off the server.
- Ideally rehearse on staging: restore a production backup onto a staging server running the
  **current production version**, then upgrade staging.
- Pick a low-traffic window.

### 3. Run it

```bash
$D/scripts/upgrade-zulip-from-git <commit ID>  # the branch name custom/13.x also works
```

A commit ID guarantees that exactly the verified commit is deployed.

The script is idempotent and appends its output to `/var/log/zulip/upgrade.log`. What the upgrade
does:

1. `apt-get update` and `apt-get upgrade`; creates the venv for the new directory
   `/home/zulip/deployments/<timestamp>`.
2. Downgrade check: if the database has migrations the new version lacks, it reports "This is not an
   upgrade" and stops.
3. Installs Node, generates any secrets the new version adds; builds the frontend with
   `tools/update-prod-static` (webpack), stopping the server first if RAM is under 4.2 GiB.
4. `manage.py check`, checks whether migrations and puppet changes are needed; runs pre-deploy hooks.
5. Stop → `zulip-puppet-apply` → `manage.py migrate` → start on the new version. Downtime is usually
   under 30 seconds, unless there's an expensive migration.
6. Runs post-deploy hooks, tells browsers to reload, purges deployment directories older than 14
   days.

Options for the command line or `[deployment] deploy_options` in `zulip.conf`
(`upgrade-zulip-from-git --help` lists them all):

- `--skip-puppet`: run `zulip-puppet-apply` manually afterwards.
- `--skip-migrations`: run `manage.py migrate` manually afterwards; when running it live, set
  `MIGRATIONS_ADD_REMOVE_INDEXES_CONCURRENTLY = True`.
- `--skip-restart`: only prepare the new version; aborts if system changes or migrations are needed.
- `--skip-purge-old-deployments`, `--audit-fts-indexes`, `--less-graceful`.

### 4. After the upgrade

- Open the web app and confirm the version (gear menu); check `/var/log/zulip/errors.log` for new
  errors; `supervisorctl status`.
- After a major version, update `settings.py` (upgrades never modify it):

  ```bash
  cp -a /etc/zulip/settings.py ~/zulip-settings-backup.py
  cp -a $D/zproject/prod_settings_template.py /etc/zulip/settings-new.py
  $D/scripts/setup/compare-settings-to-template  # lists our changes relative to the template
  # move those changes into settings-new.py, then:
  cp -a /etc/zulip/settings-new.py /etc/zulip/settings.py
  su zulip -c "$D/scripts/restart-server"
  ```

- Deploy hooks: executables ending in `.hook` in `/etc/zulip/hooks/pre-deploy.d/` and
  `/etc/zulip/hooks/post-deploy.d/` run in alphabetical order from the new version's directory, with
  `ZULIP_OLD_VERSION` and `ZULIP_NEW_VERSION` set (git deploys also get `ZULIP_OLD_COMMIT`,
  `ZULIP_NEW_COMMIT`, etc.). A failing pre-deploy hook aborts the upgrade; post-deploy failures are
  only reported.

## Rollback

- Each deployment is its own directory; `current` and `last` are symlinks. To go back one version:
  `su zulip -c '/home/zulip/deployments/last/scripts/restart-server'`; for older versions run the
  matching `/home/zulip/deployments/<timestamp>/scripts/restart-server` (directories older than 14
  days have been purged).
- This only switches code. If the new version added migrations, old code may break against the new
  schema: restore the pre-upgrade backup instead.
- Migrations applied in production (including ours) must stay in every later version, otherwise the
  downgrade check blocks the deploy.

## Backups and restore

```bash
su zulip -c "$D/manage.py backup --output=/home/zulip/backup-$(date +%F).tar.gz"
$D/scripts/setup/restore-backup /path/to/backup.tar.gz      # restore (as root)
tar -Oaxf /path/to/backup.tar.gz zulip-backup/zulip-version  # version at backup time
```

- Included: the database, `/etc/zulip` (settings and secrets), uploaded files in
  `LOCAL_UPLOADS_DIR`. `--skip-db` and `--skip-uploads` skip those parts.
- Not included: logs in `/var/log/zulip`, files on S3, SSL certificates. Store backups off the
  server.
- Restore requires: the same OS release, the same PostgreSQL major version (`--postgresql-version`
  at install), and the same Zulip build (identical `manage.py showmigrations` output) — i.e. first
  install the same build of our fork as the backup was taken on. `zulip-version`, `os-version`, and
  `postgres-version` in the backup record these.
- `restore-backup --keep-settings` / `--keep-zulipconf` keep the local `settings.py` / `zulip.conf`.
  If the hostname changed, update `EXTERNAL_HOST` and restart.
- Continuous backups (optional, database only): wal-g takes a daily full backup at 02:00 UTC plus
  continuous WAL, kept 30 days. Set `backups_directory` under `[postgresql]` in `zulip.conf` (on a
  different disk), or `s3_backups_bucket` etc. in `zulip-secrets.conf`, then run
  `zulip-puppet-apply`; list backups with `env-wal-g backup-list --pretty`.
- Do a restore drill once backups are set up.

## Day-to-day operations and troubleshooting

Logs are in `/var/log/zulip/`:

| File                         | Contents                                                  |
| ---------------------------- | --------------------------------------------------------- |
| `errors.log`                 | All errors; look here first                               |
| `server.log`                 | Django and Tornado logs; search with `scripts/log-search` |
| `workers.log`                | Queue workers                                             |
| `install.log`, `upgrade.log` | Install and upgrade script output                         |

Common commands:

```bash
supervisorctl status                    # every service RUNNING, uptime not just a few seconds
su zulip -c "$D/scripts/restart-server" # restart all services after settings changes
su zulip -c "$D/scripts/stop-server"    # stop; start with start-server
su zulip -c "$D/manage.py list_realms"  # a single organization's string_id is '' (-r '')
su zulip -c "$D/manage.py help"         # list management commands; each has --help
service nginx restart                   # nginx failing to start is usually a certificate problem
service rabbitmq-server restart         # on AMQPConnectionError
```

- Apply settings changes with `restart-server`, not by restarting a single service with
  `supervisorctl restart`.
- Backend exceptions are emailed to `ZULIP_ADMINISTRATOR`; a healthy server sends none.
- Monitoring: disk (database and uploads), memory and OOM kills, `supervisorctl status`;
  `/usr/lib/nagios/plugins/` has checks such as `check_send_receive_time`, `check_rabbitmq_queues`,
  `check_rabbitmq_consumers`.
- A cron job restarts the server every Sunday at 06:00 (`/etc/cron.d/restart-zulip`) to mitigate
  memory leaks.
- unattended-upgrades: in `/etc/apt/apt.conf.d/50unattended-upgrades`, exclude `postgresql-\d+$`,
  `rabbitmq-server$`, `redis-server$`, `memcached$`, `nginx-full$`, `supervisor$`, etc. via
  `Unattended-Upgrade::Package-Blacklist`; upgrade them manually and run `restart-server` afterwards.
- Anyone who can log in as root or the `zulip` user can read and modify all data; limit this to a
  few trusted people.
- `Invalid HTTP_HOST header` in `server.log` is usually port scanning, or a hostname missing from
  `ALLOWED_HOSTS`; RabbitMQ failing to start is often a hostname or `/etc/hosts` problem.

### PostgreSQL and OS major upgrades

- PostgreSQL major version: first upgrade to the latest maintenance release of the current series;
  stop the server; back up; as root run `$D/scripts/setup/upgrade-postgresql`; start.
- OS major version: stop and back up; `do-release-upgrade` (on Debian, follow Debian's procedure);
  reinstall the current version; upgrade PostgreSQL; reboot. Ubuntu 22.04→24.04 and Debian 12→13
  require draining the RabbitMQ queues and `apt purge rabbitmq-server` beforehand. Verify the exact
  steps for the target release before starting. The reinstall command:

  ```bash
  rm -rf /srv/zulip-venv-cache/* $D/.venv /root/.cache/uv
  $D/scripts/lib/upgrade-zulip-stage-2 $D/ --ignore-static-assets --audit-fts-indexes
  ```

## Test installs

Staging server: a VM with the same OS as production, installed with the steps above
(`--self-signed-cert`); deploy the same commit there first, then to production.

## For the lead to decide

- OS release, hostname, certificate approach (Certbot / own certificate / reverse proxy).
- Backups: frequency, storage location, whether to enable wal-g; whether to run a staging server.
- Whether to register with the official mobile push notification service (requires accepting its
  terms of service).
