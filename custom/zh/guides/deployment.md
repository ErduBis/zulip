# 部署与升级

把我们 fork 的 Zulip（`ErduBis/zulip` 的 `main` 分支）部署到自己的服务器，并在之后持续合并
上游版本、重新部署。读者：环境与运维会话、总领。

下文的服务器命令都在生产服务器上以 root 运行（`su zulip -c` 开头的以 `zulip` 用户运行）。
`$D` 指当前部署目录，先执行 `D=/home/zulip/deployments/current`。

## 服务器要求

- **独占**一台物理机或虚拟机：安装程序会用 `apt` 装 nginx、PostgreSQL、RabbitMQ、Redis、memcached
  等并按自己的方式配置。
- 系统：Ubuntu 22.04 / 24.04 / 26.04，Debian 12 / 13（以 `scripts/lib/supported-os` 为准）；
  架构 x86-64 或 aarch64。Ubuntu 需启用 universe 源（`add-apt-repository universe`）。
  选最新的受支持版本，可推迟系统大版本升级。
- 内存至少 2 GB；内存小于 5 GB 时必须有 swap（建议 2 GB），否则安装程序直接退出。
  100 人以上：2 CPU、4 GB；日活 25+ 建议 4 GB，100+ 建议 8 GB。
- 升级时前端在服务器上编译：内存不到 4.2 GiB（标称 4 GB 的机器也达不到）会先停服再编译，
  停机变长，所以选 8 GB 规格。
- 磁盘：至少 10 GB 空闲（约 25 GB 总盘），用 SSD。数据库约每 100 万条消息 10 GB。
- 网络：入站 443（80 可选，只做跳转到 HTTPS）；防火墙挡住 4369（RabbitMQ 的 epmd）；
  出站 80/443（链接预览、推送通知；安装和升级时访问 GitHub、npm、PyPI 和系统软件源）和
  SMTP（通常 587）。
- 一个 DNS 主机名（即 `EXTERNAL_HOST`）和一个可用的发信 SMTP 账号。

## 部署方式

服务器直接从我们的 GitHub 仓库部署（决策 D9）：首次安装时克隆 `main`，之后每次用
`upgrade-zulip-from-git` 部署已推送到 `origin` 的提交。前端在服务器上编译。
界面里显示的版本号来自 `git describe`（如 `13.2-4-gceb0b030c9`）。

## 首次安装

```bash
apt install git
git clone -b main https://github.com/ErduBis/zulip.git zulip-server-git
./zulip-server-git/scripts/setup/install --certbot --email=ADMIN_EMAIL --hostname=HOSTNAME
```

装完后在 `/etc/zulip/zulip.conf` 写上仓库地址（否则以后默认从官方仓库拉取）：

```ini
[deployment]
git_repo_url = https://github.com/ErduBis/zulip.git
```

安装选项（`scripts/lib/install --help`）：

- `--certbot`：自动申请 Let's Encrypt 证书并自动续期，要求服务器能从公网访问；
  `--self-signed-cert`：自签证书，用于测试或放在反向代理后面。二者互斥。
- `--postgresql-version=N`：默认 18；恢复备份时要与备份来源一致。
- `--push-notifications`：注册官方移动推送服务（会要求同意其服务条款）；不加则不注册。
- `--no-init-db`（已有数据库）、`--no-overwrite-settings`（保留现有 `/etc/zulip`）、
  `--no-dist-upgrade`（跳过开头的 `apt-get dist-upgrade`）。

安装程序可重复运行：失败后修好原因再跑一次即可，日志在 `/var/log/zulip/install.log`。
它会创建 `zulip` 用户、`/home/zulip/deployments/`（`current` 指向当前版本）、`/etc/zulip/`
下的配置，初始化数据库，最后打印一次性的组织创建链接。装完先配好发信（见下节）。

```bash
su zulip -c "$D/manage.py generate_realm_creation_link"  # 重新生成链接
su zulip -c "$D/manage.py send_test_email you@example.com"  # 验证发信
```

## 服务器配置

| 文件                            | 内容                              | 改完后运行（`scripts/` 在当前部署目录下） |
| ------------------------------- | --------------------------------- | ----------------------------------------- |
| `/etc/zulip/settings.py`        | 应用设置（Django），模板自带说明  | `scripts/restart-server`（zulip 用户）    |
| `/etc/zulip/zulip-secrets.conf` | 密钥、密码（如 `email_password`） | 同上                                      |
| `/etc/zulip/zulip.conf`         | 系统层配置（INI，puppet 读取）    | `scripts/zulip-puppet-apply`（root）      |

```bash
su zulip -c "$D/scripts/restart-server"
$D/scripts/zulip-puppet-apply      # 先列出改动并询问；-f 不询问，--noop 只预览
$D/scripts/get-django-setting NAME # 查看某个设置的实际生效值
```

- `zulip.conf` 常用项：`[machine] puppet_classes`（单机为 `zulip::profile::standalone`）；
  `[deployment] git_repo_url`、`deploy_options`；`[application_server] http_only`（反向代理以 HTTP
  转发时）、`nginx_listen_port`；`[loadbalancer] ips`（信任代理的 `X-Forwarded-*`）；
  `[postgresql] backups_directory`。布尔值写 `true`/`false`。
- puppet 管理的系统配置文件（如 nginx 配置）每次升级都会被重写。
  nginx 的本地扩展放进 include 目录：`/etc/nginx/conf.d/`（http 段）、
  `/etc/nginx/zulip-include/app.d/`（对外 server 段）。
- 证书：`--certbot` 之外，可把证书放到 `/etc/ssl/private/zulip.key` 和
  `/etc/ssl/certs/zulip.combined-chain.crt`（必须含完整中间链），或之后运行
  `$D/scripts/setup/setup-certbot --email=ADMIN_EMAIL HOSTNAME`。
- 改主机名：改 `EXTERNAL_HOST`（额外的访问名放 `ALLOWED_HOSTS`）后重启。

可选功能都在 `/etc/zulip/settings.py` 里配置（模板 `zproject/prod_settings_template.py`）：

- 发信：`EMAIL_HOST`、`EMAIL_HOST_USER`、`EMAIL_PORT`、`EMAIL_USE_TLS`、`NOREPLY_EMAIL_ADDRESS`，
  密码放 `zulip-secrets.conf` 的 `email_password`。
- 登录方式：`AUTHENTICATION_BACKENDS`，以及 `AUTH_LDAP_*`、`SOCIAL_AUTH_*`（Google、GitHub、GitLab、
  SAML、OIDC 等）、`JWT_AUTH_KEYS`。
- 移动推送：`ZULIP_SERVICE_PUSH_NOTIFICATIONS`、`ZULIP_SERVICE_SUBMIT_USAGE_STATISTICS`，
  然后 `su zulip -c "$D/manage.py register_server"`。
- 文件存储：默认 `LOCAL_UPLOADS_DIR = "/home/zulip/uploads"`；S3 用 `S3_AUTH_UPLOADS_BUCKET`、
  `S3_AVATAR_BUCKET`、`S3_REGION`、`S3_ENDPOINT_URL`；上限 `MAX_FILE_UPLOAD_SIZE`。
- 邮件转消息：`EMAIL_GATEWAY_PATTERN`、`EMAIL_GATEWAY_*`；外部数据库：`REMOTE_POSTGRES_HOST` 等。
- 视频会议：`JITSI_SERVER_URL`、`VIDEO_ZOOM_*`、`BIG_BLUE_BUTTON_URL`；错误上报：`SENTRY_DSN`。
- 其他：`INLINE_IMAGE_PREVIEW`、`RATE_LIMITING_RULES`、`PASSWORD_MIN_LENGTH`、
  `TERMS_OF_SERVICE_VERSION` + `POLICIES_DIRECTORY`（建议 `/etc/zulip/policies`，随备份保存）。

## 升级：合并上游后部署

### 1. 在开发环境合并上游（总领）

1. `git fetch upstream --tags`，在 `main` 上 `git merge <新标签>`（如 `13.3`）。
2. 冲突按 `custom/zh/CUSTOMIZATIONS.md` 逐条核对；按开发规范「中文翻译」第 3 步核对译文。
3. 检查 migration：上游新增的 migration 与我们的同时成为叶节点时，交后端会话处理；
   已在生产执行过的 migration 保持原名不变。
4. 跑相关测试和 lint，推送到 `origin`。

大版本（如 14.x）先合并到该系列最新的小版本；升级前读上游各版本发布说明里的「Upgrade notes」，
合并后对照新的 `zproject/prod_settings_template.py` 更新服务器的 `settings.py`（见下文）。

### 2. 升级前检查

- 已读这次跨越的所有版本的升级注意事项（有无耗时 migration、系统要求变化）。
- 刚做过备份（见「备份与恢复」），并已拷到服务器之外。
- 最好先在预发环境演练：把生产备份恢复到装有**当前生产版本**的预发机，再升级预发机。
- 选在低峰期。

### 3. 执行

```bash
$D/scripts/upgrade-zulip-from-git <提交 ID>  # 也可以写分支名 main
```

写提交 ID 能确保部署的正是验证过的那个提交。

脚本可重复运行，输出追加到 `/var/log/zulip/upgrade.log`。升级过程：

1. `apt-get update` 和 `apt-get upgrade`；为新目录 `/home/zulip/deployments/<时间戳>` 建 venv。
2. 降级检查：若当前数据库里有新版本不包含的 migration，报「This is not an upgrade」并停止。
3. 装 Node，补生成新版本新增的密钥；运行 `tools/update-prod-static`（webpack）编译前端，
   内存不到 4.2 GiB 时先停服再编译。
4. `manage.py check`，检查是否需要 migration 和 puppet 改动；运行 pre-deploy 钩子。
5. 停服 → `zulip-puppet-apply` → `manage.py migrate` → 在新版本上启动。通常停机不到 30 秒，
   除非有耗时 migration。
6. 运行 post-deploy 钩子，通知浏览器重新加载，清理 14 天前的旧部署目录。

可加在命令行或 `zulip.conf` 的 `[deployment] deploy_options` 里的选项
（`upgrade-zulip-from-git --help` 可列全）：

- `--skip-puppet`：之后手动运行 `zulip-puppet-apply`。
- `--skip-migrations`：之后手动 `manage.py migrate`；在线跑时设
  `MIGRATIONS_ADD_REMOVE_INDEXES_CONCURRENTLY = True`。
- `--skip-restart`：只准备好新版本，涉及系统改动或 migration 就中止。
- `--skip-purge-old-deployments`、`--audit-fts-indexes`、`--less-graceful`。

### 4. 升级后

- 打开网页确认版本号（齿轮菜单）；看 `/var/log/zulip/errors.log` 有无新错误；
  `supervisorctl status`。
- 跨大版本后更新 `settings.py`（升级不会改动它）：

  ```bash
  cp -a /etc/zulip/settings.py ~/zulip-settings-backup.py
  cp -a $D/zproject/prod_settings_template.py /etc/zulip/settings-new.py
  $D/scripts/setup/compare-settings-to-template  # 列出我们相对模板的修改
  # 把这些修改迁入 settings-new.py，然后：
  cp -a /etc/zulip/settings-new.py /etc/zulip/settings.py
  su zulip -c "$D/scripts/restart-server"
  ```

- 部署钩子：`/etc/zulip/hooks/pre-deploy.d/` 和 `/etc/zulip/hooks/post-deploy.d/`
  中以 `.hook` 结尾的可执行文件按字母序在新版本目录中运行，环境变量有 `ZULIP_OLD_VERSION`、
  `ZULIP_NEW_VERSION`（git 部署另有 `ZULIP_OLD_COMMIT`、`ZULIP_NEW_COMMIT` 等）。
  pre-deploy 失败会中止升级，post-deploy 失败只报告。

## 回滚

- 每次部署是一个独立目录，`current`、`last` 是符号链接。回到上一版：
  `su zulip -c '/home/zulip/deployments/last/scripts/restart-server'`；更早的版本运行对应
  `/home/zulip/deployments/<时间戳>/scripts/restart-server`（14 天前的目录已被清理）。
- 这只换代码。新版本带了 migration 时，旧代码面对新表结构可能出错：这时用升级前的备份恢复。
- 已在生产执行过的 migration（包括我们自己的）必须一直留在之后的每个版本里，否则部署会被
  降级检查拦下。

## 备份与恢复

```bash
su zulip -c "$D/manage.py backup --output=/home/zulip/backup-$(date +%F).tar.gz"
$D/scripts/setup/restore-backup /path/to/backup.tar.gz      # 恢复（root）
tar -Oaxf /path/to/backup.tar.gz zulip-backup/zulip-version  # 查看备份时的版本
```

- 包含：数据库、`/etc/zulip`（设置和密钥）、`LOCAL_UPLOADS_DIR` 中的上传文件。
  `--skip-db`、`--skip-uploads` 可跳过对应部分。
- 不包含：`/var/log/zulip` 日志、S3 上的文件、SSL 证书。备份要另存到服务器之外。
- 恢复条件：同一系统版本、同一 PostgreSQL 主版本（安装时用 `--postgresql-version`）、
  同一个 Zulip 构建（`manage.py showmigrations` 输出一致），也就是先装上与备份时相同的我们的版本。
  备份里的 `zulip-version`、`os-version`、`postgres-version` 记录了这些信息。
- `restore-backup` 的 `--keep-settings`、`--keep-zulipconf` 保留本机的 `settings.py`、`zulip.conf`。
  换了主机名就改 `EXTERNAL_HOST` 后重启。
- 连续备份（可选，只覆盖数据库）：wal-g 每天 02:00 UTC 全量加持续 WAL，保留 30 天。
  在 `zulip.conf` 的 `[postgresql]` 设 `backups_directory`（放在另一块盘），或在 `zulip-secrets.conf`
  设 `s3_backups_bucket` 等，再运行 `zulip-puppet-apply`；用 `env-wal-g backup-list --pretty` 查看。
- 备份配好后做一次恢复演练。

## 日常运维与排错

日志在 `/var/log/zulip/`：

| 文件                         | 内容                                                   |
| ---------------------------- | ------------------------------------------------------ |
| `errors.log`                 | 所有错误，排错先看这里                                 |
| `server.log`                 | Django 和 Tornado 日志，可用 `scripts/log-search` 搜索 |
| `workers.log`                | 队列 worker                                            |
| `install.log`、`upgrade.log` | 安装、升级脚本输出                                     |

常用命令：

```bash
supervisorctl status                    # 各服务都应 RUNNING，uptime 不应只有几秒
su zulip -c "$D/scripts/restart-server" # 改设置后重启全部服务
su zulip -c "$D/scripts/stop-server"    # 停服；启动用 start-server
su zulip -c "$D/manage.py list_realms"  # 单组织的 string_id 为 ''（-r ''）
su zulip -c "$D/manage.py help"         # 管理命令列表，各命令 --help
service nginx restart                   # nginx 起不来多为证书问题
service rabbitmq-server restart         # AMQPConnectionError 时
```

- 改设置要用 `restart-server`，不要只用 `supervisorctl restart` 重启单个服务。
- 后端异常会邮件发给 `ZULIP_ADMINISTRATOR`；正常的服务器不应收到这类邮件。
- 监控：磁盘（数据库和上传目录）、内存与 OOM、`supervisorctl status`；
  `/usr/lib/nagios/plugins/` 下有 `check_send_receive_time`、`check_rabbitmq_queues`、
  `check_rabbitmq_consumers` 等检查。
- 每周日 06:00 有定时任务自动重启（`/etc/cron.d/restart-zulip`），用于缓解内存泄漏。
- unattended-upgrades：在 `/etc/apt/apt.conf.d/50unattended-upgrades` 的
  `Unattended-Upgrade::Package-Blacklist` 里排除 `postgresql-\d+$`、`rabbitmq-server$`、
  `redis-server$`、`memcached$`、`nginx-full$`、`supervisor$` 等，改为手动升级，升级后
  `restart-server`。
- 能登录服务器 root 或 `zulip` 用户的人可以读写全部数据，只给少数可信的人。
- `server.log` 里的 `Invalid HTTP_HOST header` 多为端口扫描，或访问名没加进 `ALLOWED_HOSTS`；
  RabbitMQ 起不来常因主机名或 `/etc/hosts` 配置不对。

### PostgreSQL 与系统大版本升级

- PostgreSQL 主版本：先升到当前系列最新小版本；停服；备份；以 root 运行
  `$D/scripts/setup/upgrade-postgresql`；启动。
- 系统大版本：停服并备份；`do-release-upgrade`（Debian 按官方步骤）；重装当前版本；
  升级 PostgreSQL；重启机器。Ubuntu 22.04→24.04 和 Debian 12→13 需要事先清空 RabbitMQ 队列并
  `apt purge rabbitmq-server`。做之前先按目标版本核实具体步骤。重装当前版本的命令：

  ```bash
  rm -rf /srv/zulip-venv-cache/* $D/.venv /root/.cache/uv
  $D/scripts/lib/upgrade-zulip-stage-2 $D/ --ignore-static-assets --audit-fts-indexes
  ```

## 测试安装

预发机：一台与生产同系统的虚拟机，按上面步骤安装（`--self-signed-cert`），先部署同一个提交
验证，再部署到生产。

## 待总领决定

- 系统版本、主机名、证书方式（Certbot / 自有证书 / 反向代理）。
- 备份：频率、保存位置、是否启用 wal-g；是否设预发环境。
- 是否注册官方移动推送服务（需同意其服务条款）。
