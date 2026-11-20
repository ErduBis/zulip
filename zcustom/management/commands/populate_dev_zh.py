from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError, CommandParser
from django.utils.timezone import now as timezone_now
from typing_extensions import override

from zcustom.lib.dev_data import DEV_DATA_DIR, DevDataError, load_and_validate_dev_data
from zcustom.lib.dev_realm import localize_analytics_realm, populate_dev_realm
from zerver.lib.management import ZulipBaseCommand
from zerver.lib.remote_server import get_realms_info_for_push_bouncer
from zerver.lib.server_initialization import create_internal_realm
from zerver.models.realm_audit_logs import AuditLogEventType

# Importing populate_db also applies its settings overrides for data
# generation (no push notification bouncer, a local-memory cache).
from zilencer.management.commands.populate_db import clear_database
from zilencer.models import RemoteZulipServer, RemoteZulipServerAuditLog
from zilencer.views import update_remote_realm_data_for_server


class Command(ZulipBaseCommand):
    help = """Rebuild the development database with the Chinese example organization.

Replaces upstream's populate_db for the development database only; the
test database is still built by populate_db --test-suite.  All existing
data in the database is deleted."""

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "-n",
            "--num-messages",
            type=int,
            default=0,
            help="Total number of conversation messages; filler sentences make up any "
            "shortfall of the scripted conversations.",
        )
        parser.add_argument(
            "--extra-users", type=int, default=0, help="The number of extra users to create"
        )
        parser.add_argument(
            "--extra-streams", type=int, default=0, help="The number of extra channels to create"
        )
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=DEV_DATA_DIR,
            help="Directory with the organization data (default: zcustom/dev_data).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Only validate the organization data; don't touch the database.",
        )

    @override
    def handle(self, *args: Any, **options: Any) -> None:
        try:
            data = load_and_validate_dev_data(options["data_dir"])
        except DevDataError as e:
            raise CommandError(
                f"Organization data has {len(e.errors)} problem(s):\n" + "\n".join(e.errors)
            )
        if options["check"]:
            self.stdout.write("Organization data is valid.\n")
            return

        if settings.PRODUCTION or settings.TEST_SUITE:
            raise CommandError("This command only builds the development database.")

        # Process queued work inline, so that no queued event refers
        # to objects from a previous life of the database.
        settings.USING_RABBITMQ = False

        clear_database()
        create_internal_realm()
        populate_dev_realm(
            data,
            string_id="zulip",
            now=timezone_now(),
            num_messages=options["num_messages"],
            extra_users=options["extra_users"],
            extra_streams=options["extra_streams"],
        )
        self.register_with_push_bouncer()

        call_command("populate_analytics_db", skip_checks=True)
        localize_analytics_realm(data.org.analytics)
        self.stdout.write("Successfully populated the development database.\n")

    def register_with_push_bouncer(self) -> None:
        # Development realms are registered with the local push
        # bouncer, as upstream's populate_db does.
        assert isinstance(settings.ZULIP_ORG_ID, str)
        assert isinstance(settings.ZULIP_ORG_KEY, str)
        server = RemoteZulipServer.objects.create(
            uuid=settings.ZULIP_ORG_ID,
            api_key=settings.ZULIP_ORG_KEY,
            hostname=settings.EXTERNAL_HOST,
            last_updated=timezone_now(),
            contact_email="remotezulipserver@zulip.com",
        )
        RemoteZulipServerAuditLog.objects.create(
            event_type=AuditLogEventType.REMOTE_SERVER_CREATED,
            server=server,
            event_time=server.last_updated,
        )
        update_remote_realm_data_for_server(server, get_realms_info_for_push_bouncer())
