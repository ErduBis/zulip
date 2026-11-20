from django.apps import AppConfig
from django.db.models.signals import post_save
from typing_extensions import override


class ZCustomConfig(AppConfig):
    name: str = "zcustom"

    @override
    def ready(self) -> None:
        from zcustom.lib.system_bots import localize_bots_of_new_system_bot_realm
        from zerver.models import Realm

        post_save.connect(
            localize_bots_of_new_system_bot_realm,
            sender=Realm,
            dispatch_uid="zcustom_localize_bots_of_new_system_bot_realm",
        )
