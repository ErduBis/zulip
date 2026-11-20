from django.conf import settings
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

# Email local part, upstream English name and Chinese name of each
# system bot; copied from INTERNAL_BOTS and DISABLED_REALM_INTERNAL_BOTS
# in zproject/computed_settings.py and from zcustom/lib/system_bots.py,
# since migrations must not depend on code that can change later.
SYSTEM_BOT_NAMES = [
    ("notification-bot", "Notification Bot", "通知机器人"),
    ("emailgateway", "Email Gateway", "邮件网关"),
    ("welcome-bot", "Welcome Bot", "欢迎机器人"),
    ("reminder-bot", "Reminder Bot", "提醒机器人"),
    ("nagios-send-bot", "Nagios Send Bot", "Nagios 发送机器人"),
    ("nagios-receive-bot", "Nagios Receive Bot", "Nagios 接收机器人"),
    ("nagios-staging-send-bot", "Nagios Staging Send Bot", "Nagios 预发环境发送机器人"),
    ("nagios-staging-receive-bot", "Nagios Staging Receive Bot", "Nagios 预发环境接收机器人"),
]


def localize_system_bot_names(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    # The test database keeps the upstream English names, which
    # upstream tests rely on.
    if getattr(settings, "TEST_SUITE", False):
        return

    UserProfile = apps.get_model("zerver", "UserProfile")
    domain = getattr(settings, "INTERNAL_BOT_DOMAIN", "zulip.com")
    # Only bots still named in English are renamed.  The migrate
    # command clears memcached afterwards, so update() is safe here.
    for local_part, english_name, chinese_name in SYSTEM_BOT_NAMES:
        UserProfile.objects.filter(
            is_bot=True, email__iexact=f"{local_part}@{domain}", full_name=english_name
        ).update(full_name=chinese_name)


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0815_merge"),
    ]

    operations = [
        migrations.RunPython(
            localize_system_bot_names,
            reverse_code=migrations.RunPython.noop,
            elidable=True,
        ),
    ]
