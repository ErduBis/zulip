"""Chinese display names for Zulip's system bots.

Our users are Chinese speakers, so Welcome Bot, Notification Bot and
the other system bots are named in Chinese for everyone.  The names
are stored on the bots' UserProfile rows: existing servers are
updated by the migration zcustom/0001, and new servers when their
system bot realm is created (see zcustom.apps).

The test database keeps the upstream English names, which upstream
tests rely on.
"""

from django.conf import settings
from django.db import transaction

from zerver.models import Realm, UserProfile

# Keyed by the var_name in INTERNAL_BOTS and the realm-internal bot
# lists in zproject/computed_settings.py.
SYSTEM_BOT_CHINESE_NAMES: dict[str, str] = {
    "NOTIFICATION_BOT": "通知机器人",
    "EMAIL_GATEWAY_BOT": "邮件网关",
    "WELCOME_BOT": "欢迎机器人",
    "REMINDER_BOT": "提醒机器人",
    "NAGIOS_SEND_BOT": "Nagios 发送机器人",
    "NAGIOS_RECEIVE_BOT": "Nagios 接收机器人",
    "NAGIOS_STAGING_SEND_BOT": "Nagios 预发环境发送机器人",
    "NAGIOS_STAGING_RECEIVE_BOT": "Nagios 预发环境接收机器人",
}


def localize_system_bot_names() -> None:
    """Renames system bots that still have their upstream English name."""
    bots = [
        *settings.INTERNAL_BOTS,
        *settings.REALM_INTERNAL_BOTS,
        *settings.DISABLED_REALM_INTERNAL_BOTS,
    ]
    for bot in bots:
        chinese_name = SYSTEM_BOT_CHINESE_NAMES.get(bot["var_name"])
        if chinese_name is None:
            continue
        email = bot["email_template"] % (settings.INTERNAL_BOT_DOMAIN,)
        for user in UserProfile.objects.filter(
            is_bot=True, email__iexact=email, full_name=bot["name"]
        ):
            user.full_name = chinese_name
            # save() rather than update(), so the user caches are flushed.
            user.save(update_fields=["full_name"])


def localize_bots_of_new_system_bot_realm(
    sender: type[Realm], instance: Realm, created: bool, **kwargs: object
) -> None:
    """post_save receiver for Realm.

    create_internal_realm creates the system bots after saving the
    realm, in the same transaction, so they are renamed once it commits.
    """
    if created and instance.string_id == settings.SYSTEM_BOT_REALM and not settings.TEST_SUITE:
        transaction.on_commit(localize_system_bot_names)
