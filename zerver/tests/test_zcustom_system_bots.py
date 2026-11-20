import importlib

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from zcustom.lib.system_bots import localize_bots_of_new_system_bot_realm, localize_system_bot_names
from zerver.lib.test_classes import ZulipTestCase
from zerver.models import Realm, UserProfile
from zerver.models.realms import get_realm
from zerver.models.users import get_system_bot

MIGRATION_NAME = "0001_localize_system_bot_names"


class SystemBotNamesTest(ZulipTestCase):
    def system_bot_name(self, email: str) -> str:
        return UserProfile.objects.get(email=email, is_bot=True).full_name

    def test_localize_system_bot_names(self) -> None:
        internal_realm_id = get_realm(settings.SYSTEM_BOT_REALM).id
        # Bots whose name was changed on purpose keep it.
        email_gateway = get_system_bot(settings.EMAIL_GATEWAY_BOT, internal_realm_id)
        email_gateway.full_name = "Our gateway"
        email_gateway.save(update_fields=["full_name"])

        localize_system_bot_names()
        self.assertEqual(self.system_bot_name(settings.WELCOME_BOT), "欢迎机器人")
        self.assertEqual(self.system_bot_name(settings.NOTIFICATION_BOT), "通知机器人")
        self.assertEqual(self.system_bot_name(settings.NAGIOS_SEND_BOT), "Nagios 发送机器人")
        self.assertEqual(self.system_bot_name(settings.EMAIL_GATEWAY_BOT), "Our gateway")
        # The cached UserProfile reflects the new name.
        self.assertEqual(
            get_system_bot(settings.WELCOME_BOT, internal_realm_id).full_name, "欢迎机器人"
        )

        localize_system_bot_names()
        self.assertEqual(self.system_bot_name(settings.WELCOME_BOT), "欢迎机器人")

    def test_new_system_bot_realm_hook(self) -> None:
        internal_realm = get_realm(settings.SYSTEM_BOT_REALM)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            localize_bots_of_new_system_bot_realm(Realm, internal_realm, created=False)
            localize_bots_of_new_system_bot_realm(Realm, get_realm("zulip"), created=True)
            # The test database keeps upstream's English names.
            localize_bots_of_new_system_bot_realm(Realm, internal_realm, created=True)
        self.assert_length(callbacks, 0)
        self.assertEqual(self.system_bot_name(settings.WELCOME_BOT), "Welcome Bot")

        with (
            self.settings(TEST_SUITE=False),
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            localize_bots_of_new_system_bot_realm(Realm, internal_realm, created=True)
        self.assert_length(callbacks, 1)
        self.assertEqual(self.system_bot_name(settings.WELCOME_BOT), "欢迎机器人")

    def test_migration(self) -> None:
        migration = importlib.import_module(f"zcustom.migrations.{MIGRATION_NAME}")
        state_apps = (
            MigrationExecutor(connection).loader.project_state([("zcustom", MIGRATION_NAME)]).apps
        )

        migration.localize_system_bot_names(state_apps, connection.schema_editor())
        self.assertEqual(self.system_bot_name(settings.WELCOME_BOT), "Welcome Bot")

        with self.settings(TEST_SUITE=False):
            migration.localize_system_bot_names(state_apps, connection.schema_editor())
        self.assertEqual(self.system_bot_name(settings.WELCOME_BOT), "欢迎机器人")
        self.assertEqual(self.system_bot_name(settings.NOTIFICATION_BOT), "通知机器人")
        self.assertEqual(self.system_bot_name(settings.EMAIL_GATEWAY_BOT), "邮件网关")
