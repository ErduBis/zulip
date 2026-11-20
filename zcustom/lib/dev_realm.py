"""Generates the Chinese development organization from zcustom/dev_data.

Unlike upstream's populate_db, the organization and its people are
created through the same code paths as a real organization
(do_create_realm and do_create_user), so it has the onboarding
messages, Welcome Bot DMs and default channels a new organization
has.  All times are backdated so that message IDs increase with
message dates, as they would on a real server.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import orjson
from django.conf import settings
from django.core.files.base import File
from django.db.models import F
from django.utils.timezone import now as timezone_now

from zcustom.lib.dev_data import (
    ANALYTICS_EMAIL_DOMAIN,
    BOT_TYPES,
    DEV_EMAIL_DOMAIN,
    DEV_REALM_LANGUAGE,
    PROFILE_FIELD_TYPES,
    ROLE_VALUES,
    AnalyticsData,
    ChannelTarget,
    DevData,
    DirectTarget,
    MessageData,
    build_index,
    can_post,
    can_view,
    conversation_start_time,
    message_offsets,
)
from zerver.actions.alert_words import do_add_alert_words
from zerver.actions.channel_folders import check_add_channel_folder
from zerver.actions.create_realm import do_create_realm
from zerver.actions.create_user import do_create_user
from zerver.actions.custom_profile_fields import (
    do_update_user_custom_profile_data_if_changed,
    try_add_realm_custom_profile_field,
    try_add_realm_default_custom_profile_field,
)
from zerver.actions.default_streams import do_add_default_stream
from zerver.actions.message_edit import check_update_message
from zerver.actions.message_send import build_message_send_dict, do_send_messages
from zerver.actions.realm_emoji import check_add_realm_emoji
from zerver.actions.realm_linkifiers import do_add_linkifier
from zerver.actions.realm_settings import do_set_realm_property
from zerver.actions.scheduled_messages import check_schedule_message
from zerver.actions.streams import bulk_add_subscriptions
from zerver.actions.user_groups import add_subgroups_to_user_group, create_user_group_in_database
from zerver.lib.bulk_create import bulk_create_streams
from zerver.lib.drafts import DraftData, do_create_drafts
from zerver.lib.emoji import EmojiData, get_emoji_data
from zerver.lib.initial_password import initial_password
from zerver.lib.onboarding_steps import ALL_ONBOARDING_STEPS
from zerver.lib.recipient_users import get_recipient_from_user_profiles
from zerver.lib.server_initialization import create_users
from zerver.lib.storage import static_path
from zerver.lib.topic import RESOLVED_TOPIC_PREFIX
from zerver.lib.types import ProfileDataElementUpdateDict, ProfileFieldData
from zerver.lib.users import add_service
from zerver.lib.utils import assert_is_not_none, generate_api_key
from zerver.models import (
    Message,
    NamedUserGroup,
    Reaction,
    Realm,
    RealmAuditLog,
    RealmDomain,
    Service,
    Stream,
    UserMessage,
    UserPresence,
    UserProfile,
)
from zerver.models.clients import get_client
from zerver.models.groups import SystemGroups
from zerver.models.onboarding_steps import OnboardingStep
from zerver.models.realms import get_realm
from zerver.models.streams import get_stream

# Messages in the last day stay unread, so the inbox has something
# in it; older ones are marked as read, as an active user would have.
UNREAD_WINDOW = timedelta(days=1)
RESOLVE_DELAY = timedelta(minutes=10)
SEND_BATCH_SIZE = 500
FILLER_REACTION_EMOJIS = ["+1", "smile", "heart", "tada", "eyes", "joy"]
FILLER_FLAIR_EMOJIS = [":+1:", ":smile:", ":tada:", ":thinking:", ":pray:"]


@dataclass
class PlannedMessage:
    time: datetime
    sender: str
    text: str
    channel: str | None = None
    topic: str | None = None
    direct_members: list[str] | None = None
    reactions: dict[str, list[str]] = field(default_factory=dict)
    message_id: int | None = None


@dataclass
class PlannedResolve:
    time: datetime
    channel: str
    topic: str
    resolver: str


def plan_scripted_messages(
    data: DevData, now: datetime
) -> tuple[list[PlannedMessage], list[PlannedResolve]]:
    messages: list[PlannedMessage] = []
    resolves: list[PlannedResolve] = []
    for conversation in data.conversations:
        channel = conversation.data.channel
        for topic in conversation.data.topics:
            planned = plan_conversation(topic.messages, conversation_start_time(topic.start, now))
            for message in planned:
                message.channel = channel
                message.topic = topic.topic
            messages.extend(planned)
            if topic.resolved:
                resolves.append(
                    PlannedResolve(
                        time=min(planned[-1].time + RESOLVE_DELAY, now),
                        channel=channel,
                        topic=topic.topic,
                        resolver=topic.resolved_by or topic.messages[-1].sender,
                    )
                )
    for direct_conversation in data.direct_messages:
        planned = plan_conversation(
            direct_conversation.messages, conversation_start_time(direct_conversation.start, now)
        )
        for message in planned:
            message.direct_members = direct_conversation.members
        messages.extend(planned)
    return messages, resolves


def plan_conversation(messages: list[MessageData], start: datetime) -> list[PlannedMessage]:
    return [
        PlannedMessage(
            time=start + offset,
            sender=message.sender,
            text=message.text,
            reactions=message.reactions,
        )
        for message, offset in zip(messages, message_offsets(messages), strict=True)
    ]


def add_filler_flair(rng: random.Random, sentence: str) -> str:
    roll = rng.random()
    if "\n" in sentence or sentence.startswith((":", "@", ">")):
        return sentence
    if roll < 0.08:
        return f"**{sentence}**"
    if roll < 0.12:
        return f"> {sentence}"
    if roll < 0.22:
        return f"{sentence} {rng.choice(FILLER_FLAIR_EMOJIS)}"
    return sentence


def plan_filler_messages(
    data: DevData,
    rng: random.Random,
    count: int,
    earliest: datetime,
    latest: datetime,
    resolves: list[PlannedResolve],
) -> list[PlannedMessage]:
    index = build_index(data)
    channels = sorted(data.filler.topics)
    if count <= 0 or not channels or not data.filler.sentences:
        return []
    resolve_times = {(resolve.channel, resolve.topic): resolve.time for resolve in resolves}
    planned = []
    for _ in range(count):
        channel = rng.choice(channels)
        topic = rng.choice(data.filler.topics[channel])
        senders = sorted(key for key in index.members if can_post(index, key, channel))
        message_time = earliest + (latest - earliest) * rng.random()
        resolve_time = resolve_times.get((channel, topic))
        if resolve_time is not None and message_time > resolve_time:
            topic = RESOLVED_TOPIC_PREFIX + topic
        reactions: dict[str, list[str]] = {}
        if rng.random() < 0.2:
            viewers = sorted(key for key in index.members if can_view(index, key, channel))
            for key in rng.sample(viewers, rng.randint(1, min(3, len(viewers)))):
                reactions.setdefault(rng.choice(FILLER_REACTION_EMOJIS), []).append(key)
        planned.append(
            PlannedMessage(
                time=message_time,
                sender=rng.choice(senders),
                text=add_filler_flair(rng, rng.choice(data.filler.sentences)),
                channel=channel,
                topic=topic,
                reactions=reactions,
            )
        )
    return planned


class DevRealmBuilder:
    def __init__(
        self,
        data: DevData,
        *,
        string_id: str,
        now: datetime,
        num_messages: int,
        extra_users: int,
        extra_streams: int,
        seed: int,
    ) -> None:
        self.data = data
        self.string_id = string_id
        self.now = now
        self.num_messages = num_messages
        self.extra_users = extra_users
        self.extra_streams = extra_streams
        self.rng = random.Random(seed)
        self.users: dict[str, UserProfile] = {}
        self.extra_user_profiles: list[UserProfile] = []
        self.streams: dict[str, Stream] = {}
        self.client = get_client("website")

    def build(self) -> Realm:
        scripted, resolves = plan_scripted_messages(self.data, self.now)
        earliest = min((message.time for message in scripted), default=self.now - timedelta(days=7))
        self.realm_created = earliest - timedelta(hours=1)
        setup_started = timezone_now()

        self.realm = self.create_realm()
        self.create_members()
        self.create_bots()
        self.create_profile_fields()
        self.create_realm_features()
        self.create_channels()
        self.create_user_groups()
        self.create_personal_data()
        self.backdate_setup(setup_started)

        filler = plan_filler_messages(
            self.data,
            self.rng,
            self.num_messages - len(scripted),
            self.realm_created + timedelta(hours=1),
            self.now - timedelta(minutes=5),
            resolves,
        )
        self.send_timeline(scripted + filler, resolves)
        return self.realm

    def create_realm(self) -> Realm:
        realm_data = self.data.org.realm
        realm = do_create_realm(
            string_id=self.string_id,
            name=realm_data.name,
            description=realm_data.description,
            emails_restricted_to_domains=False,
            # Development conveniences that differ from a new
            # organization's defaults: anyone can sign up to test
            # registration, and read receipts and spectator access
            # are on so those features can be tried out.
            invite_required=False,
            enable_read_receipts=True,
            enable_spectator_access=True,
            plan_type=Realm.PLAN_TYPE_SELF_HOSTED,
            org_type=Realm.ORG_TYPES["business"]["id"],
            default_language=DEV_REALM_LANGUAGE,
            date_created=self.realm_created,
        )
        RealmDomain.objects.create(realm=realm, domain=DEV_EMAIL_DOMAIN)
        if realm_data.welcome_message_custom_text:
            do_set_realm_property(
                realm,
                "welcome_message_custom_text",
                realm_data.welcome_message_custom_text,
                acting_user=None,
            )
        return realm

    def create_members(self) -> None:
        creator = self.data.creator
        members = [creator] + [
            member
            for member in self.data.org.members
            if member is not creator and not member.imported_stub
        ]
        for member in members:
            self.users[member.key] = do_create_user(
                member.email,
                initial_password(member.email),
                self.realm,
                member.name,
                role=ROLE_VALUES[member.role],
                tos_version=settings.TERMS_OF_SERVICE_VERSION,
                timezone=member.timezone,
                default_language=DEV_REALM_LANGUAGE,
                realm_creation=member is creator,
                acting_user=None,
            )
            if member.is_staff:
                self.users[member.key].is_staff = True
                self.users[member.key].save(update_fields=["is_staff"])

        # Imported users never went through signup, so they are
        # created the way an import creates them.
        for member in self.data.org.members:
            if not member.imported_stub:
                continue
            create_users(
                self.realm,
                [(member.name, member.email)],
                is_imported_stub=True,
                tos_version=UserProfile.TOS_VERSION_BEFORE_FIRST_LOGIN,
            )
            user = UserProfile.objects.get(realm=self.realm, delivery_email=member.email)
            user.timezone = member.timezone
            user.save(update_fields=["timezone"])
            self.users[member.key] = user

        if self.extra_users > 0:
            # The "extrauser" prefix keeps these off the main /devlogin list.
            create_users(
                self.realm,
                [
                    (f"额外用户{i:03}", f"extrauser{i}@{DEV_EMAIL_DOMAIN}")
                    for i in range(self.extra_users)
                ],
                tos_version=settings.TERMS_OF_SERVICE_VERSION,
            )
            self.extra_user_profiles = list(
                UserProfile.objects.filter(
                    realm=self.realm, delivery_email__startswith="extrauser"
                ).order_by("id")
            )

    def create_bots(self) -> None:
        for bot in self.data.org.bots:
            create_users(
                self.realm,
                [(bot.name, bot.email)],
                bot_type=BOT_TYPES[bot.email],
                bot_owner=self.users[bot.owner],
            )
            if BOT_TYPES[bot.email] == UserProfile.OUTGOING_WEBHOOK_BOT:
                add_service(
                    "outgoing-webhook",
                    user_profile=UserProfile.objects.get(
                        realm=self.realm, delivery_email=bot.email
                    ),
                    interface=Service.GENERIC,
                    base_url="http://127.0.0.1:5002",
                    token=generate_api_key(),
                )

    def create_profile_fields(self) -> None:
        field_ids: dict[str, int] = {}
        dropdown_values: dict[str, dict[str, str]] = {}
        for profile_field in self.data.org.custom_profile_fields:
            if profile_field.type == "external_account":
                github_field = try_add_realm_default_custom_profile_field(self.realm, "github")
                # The default field is named in English ("GitHub username"),
                # not in the realm's language; use the name from the data.
                github_field.name = profile_field.name
                github_field.save(update_fields=["name"])
                field_ids[profile_field.name] = github_field.id
                continue
            field_data: ProfileFieldData | None = None
            if profile_field.type == "dropdown":
                assert profile_field.options is not None
                field_data = {
                    str(i): {"text": option, "order": str(i + 1)}
                    for i, option in enumerate(profile_field.options)
                }
                dropdown_values[profile_field.name] = {
                    option: str(i) for i, option in enumerate(profile_field.options)
                }
            field_ids[profile_field.name] = try_add_realm_custom_profile_field(
                self.realm,
                profile_field.name,
                PROFILE_FIELD_TYPES[profile_field.type],
                hint=profile_field.hint,
                field_data=field_data,
            ).id

        for member in self.data.org.members:
            updates: list[ProfileDataElementUpdateDict] = []
            for field_name, value in member.profile.items():
                if isinstance(value, list):
                    updates.append(
                        {"id": field_ids[field_name], "value": [self.users[k].id for k in value]}
                    )
                elif field_name in dropdown_values:
                    updates.append(
                        {"id": field_ids[field_name], "value": dropdown_values[field_name][value]}
                    )
                else:
                    updates.append({"id": field_ids[field_name], "value": value})
            if updates:
                do_update_user_custom_profile_data_if_changed(
                    self.users[member.key], updates, acting_user=None, notify=False
                )

    def create_realm_features(self) -> None:
        for linkifier in self.data.org.linkifiers:
            do_add_linkifier(
                self.realm, linkifier.pattern, linkifier.url_template, acting_user=None
            )
        admin = self.users[(self.data.member_by_replaces("iago") or self.data.creator).key]
        with open(static_path("images/test-images/checkbox.png"), "rb") as fp:
            check_add_realm_emoji(
                self.realm, "green_tick", admin, File(fp, name="checkbox.png"), "image/png"
            )

    def create_channels(self) -> None:
        creator = self.users[self.data.creator.key]
        folder_ids = {
            folder.name: check_add_channel_folder(
                self.realm, folder.name, folder.description, acting_user=creator
            ).id
            for folder in self.data.org.channel_folders
        }
        admins_group = NamedUserGroup.objects.get(
            name=SystemGroups.ADMINISTRATORS, realm_for_sharding=self.realm, is_system_group=True
        )
        # Any matches bulk_create_streams, whose options mix strings,
        # booleans and model instances.
        stream_dict: dict[str, dict[str, Any]] = {}
        for channel in self.data.org.channels:
            options: dict[str, Any] = {
                "description": channel.description,
                "invite_only": channel.private,
                "is_web_public": channel.web_public,
            }
            if channel.creator is not None:
                options["creator"] = self.users[channel.creator]
            if channel.folder is not None:
                options["folder_id"] = folder_ids[channel.folder]
            if channel.admins_only_post:
                options["can_send_message_group"] = admins_group
            stream_dict[channel.name] = options
        extra_stream_names = [f"额外频道 {i}" for i in range(self.extra_streams)]
        for name in extra_stream_names:
            stream_dict[name] = {"description": "自动生成的额外频道，用于测试频道很多时的界面。"}
        bulk_create_streams(self.realm, stream_dict)

        self.streams = {stream.name: stream for stream in Stream.objects.filter(realm=self.realm)}
        for channel in self.data.org.channels:
            if channel.default_channel:
                do_add_default_stream(self.streams[channel.name])

        index = build_index(self.data)
        everyone_extra = self.extra_user_profiles
        for channel_name, keys in sorted(index.subscribers.items()):
            users = [self.users[key] for key in sorted(keys)]
            if channel_name in index.builtin_channels:
                # Data members already got the built-in channels at signup.
                users = []
            channel_data = next((c for c in self.data.org.channels if c.name == channel_name), None)
            if channel_data is None or channel_data.subscribers in ("everyone", "members"):
                users += everyone_extra
            if users:
                bulk_add_subscriptions(
                    self.realm, [self.streams[channel_name]], users, acting_user=None
                )
        all_humans = [self.users[member.key] for member in self.data.org.members] + everyone_extra
        for name in extra_stream_names:
            bulk_add_subscriptions(self.realm, [self.streams[name]], all_humans, acting_user=None)

    def create_user_groups(self) -> None:
        creator = self.users[self.data.creator.key]
        groups = {
            group.name: create_user_group_in_database(
                group.name,
                [self.users[key] for key in group.members],
                self.realm,
                acting_user=creator,
                description=group.description,
            )
            for group in self.data.org.user_groups
        }
        for group in self.data.org.user_groups:
            add_subgroups_to_user_group(
                groups[group.name],
                [groups[name] for name in group.subgroups],
                acting_user=creator,
            )

    def create_personal_data(self) -> None:
        org = self.data.org
        for member in org.members:
            if member.imported_stub or not org.alert_words:
                continue
            do_add_alert_words(
                self.users[member.key],
                self.rng.sample(org.alert_words, min(4, len(org.alert_words))),
            )

        for draft in org.drafts:
            owner = self.users[draft.owner]
            if isinstance(draft.to, ChannelTarget):
                draft_data = DraftData(
                    type="stream",
                    to=[self.streams[draft.to.channel].id],
                    topic=draft.to.topic,
                    content=draft.text,
                )
            elif isinstance(draft.to, DirectTarget):
                draft_data = DraftData(
                    type="private",
                    to=[self.users[key].id for key in draft.to.direct],
                    topic="",
                    content=draft.text,
                )
            else:
                draft_data = DraftData(type="", to=[], topic="", content=draft.text)
            do_create_drafts([draft_data], owner)

        for scheduled in org.scheduled_messages:
            if isinstance(scheduled.to, ChannelTarget):
                recipient_type_name = "stream"
                message_to = [self.streams[scheduled.to.channel].id]
                topic_name: str | None = scheduled.to.topic
            else:
                recipient_type_name = "private"
                message_to = [self.users[key].id for key in scheduled.to.direct]
                topic_name = None
            check_schedule_message(
                sender=self.users[scheduled.sender],
                client=self.client,
                recipient_type_name=recipient_type_name,
                message_to=message_to,
                topic_name=topic_name,
                message_content=scheduled.text,
                deliver_at=self.now + timedelta(days=scheduled.deliver_in_days),
                realm=self.realm,
            )

        # Only the organization creator sees the onboarding a new user
        # would; everyone else has them marked as seen so the pages
        # used for daily development and screenshots aren't covered
        # by popups.
        creator = self.users[self.data.creator.key]
        others = [
            user for user in [*self.users.values(), *self.extra_user_profiles] if user != creator
        ]
        OnboardingStep.objects.bulk_create(
            [
                OnboardingStep(user=user, onboarding_step=step.name)
                for user in others
                for step in ALL_ONBOARDING_STEPS
            ],
            ignore_conflicts=True,
        )
        UserPresence.objects.bulk_create(
            UserPresence(
                user_profile=user,
                realm_id=self.realm.id,
                last_active_time=self.now,
                last_connected_time=self.now,
            )
            for user in [*self.users.values(), *self.extra_user_profiles]
            if not user.is_imported_stub
        )

    def backdate_setup(self, setup_started: datetime) -> None:
        """Moves everything the setup created to the realm's creation time.

        The onboarding messages and Welcome Bot DMs are sent while
        the people are created, before any conversation; keeping
        their order but giving them the creation time keeps message
        IDs in date order.
        """
        messages = list(Message.objects.filter(realm=self.realm).order_by("id"))
        for i, message in enumerate(messages):
            message.date_sent = self.realm_created + timedelta(seconds=i)
        Message.objects.bulk_update(messages, ["date_sent"])
        self.setup_message_ids = {message.id for message in messages}
        UserProfile.objects.filter(realm=self.realm).update(date_joined=self.realm_created)
        Stream.objects.filter(realm=self.realm).update(date_created=self.realm_created)
        RealmAuditLog.objects.filter(realm=self.realm, event_time__gte=setup_started).update(
            event_time=self.realm_created
        )

    def build_message(self, planned: PlannedMessage) -> Message:
        sender = self.users[planned.sender]
        message = Message(
            realm=self.realm,
            sender=sender,
            sending_client=self.client,
            content=planned.text,
            date_sent=planned.time,
        )
        if planned.channel is not None:
            assert planned.topic is not None
            message.recipient = assert_is_not_none(self.streams[planned.channel].recipient)
            message.subject = planned.topic
            message.is_channel_message = True
        else:
            assert planned.direct_members is not None
            message.recipient = get_recipient_from_user_profiles(
                [self.users[key] for key in planned.direct_members],
                forwarder_user_profile=None,
                sender=sender,
            )
            message.subject = Message.DM_TOPIC
            message.is_channel_message = False
        return message

    def send_timeline(self, messages: list[PlannedMessage], resolves: list[PlannedResolve]) -> None:
        # Resolving a topic sends a notification message, so it has to
        # happen in date order with the other messages.
        events: list[tuple[datetime, int, PlannedMessage | PlannedResolve]] = [
            (message.time, i, message) for i, message in enumerate(messages)
        ]
        events += [(resolve.time, len(messages) + i, resolve) for i, resolve in enumerate(resolves)]
        events.sort(key=lambda event: (event[0], event[1]))

        batch: list[PlannedMessage] = []
        timeline_message_times: dict[int, datetime] = {}
        for _, _, event in events:
            if isinstance(event, PlannedMessage):
                batch.append(event)
                if len(batch) >= SEND_BATCH_SIZE:
                    self.send_batch(batch, timeline_message_times)
                    batch = []
            else:
                self.send_batch(batch, timeline_message_times)
                batch = []
                self.resolve_topic(event, timeline_message_times)
        self.send_batch(batch, timeline_message_times)

        self.add_reactions(messages)
        old_message_ids = [
            message_id
            for message_id, sent in timeline_message_times.items()
            if sent < self.now - UNREAD_WINDOW
        ]
        UserMessage.objects.filter(
            message_id__in=old_message_ids, user_profile__is_bot=False
        ).update(flags=F("flags").bitor(UserMessage.flags.read))

    def send_batch(
        self, batch: list[PlannedMessage], timeline_message_times: dict[int, datetime]
    ) -> None:
        if not batch:
            return
        built = [self.build_message(planned) for planned in batch]
        do_send_messages([build_message_send_dict(message=message) for message in built])
        for planned, message in zip(batch, built, strict=True):
            planned.message_id = message.id
            timeline_message_times[message.id] = planned.time

    def resolve_topic(
        self, resolve: PlannedResolve, timeline_message_times: dict[int, datetime]
    ) -> None:
        stream = self.streams[resolve.channel]
        first_message = Message.objects.filter(
            realm=self.realm, recipient=stream.recipient, subject=resolve.topic
        ).first()
        assert first_message is not None
        last_id_before = Message.objects.filter(realm=self.realm).order_by("-id")[0].id
        edit_started = timezone_now()
        check_update_message(
            self.users[resolve.resolver],
            first_message.id,
            topic_name=RESOLVED_TOPIC_PREFIX + resolve.topic,
            propagate_mode="change_all",
            send_notification_to_old_thread=False,
            send_notification_to_new_thread=False,
        )

        # The edit and its notification are stamped with the real
        # current time; move them to the planned resolve time.
        for notification in Message.objects.filter(realm=self.realm, id__gt=last_id_before):
            notification.date_sent = resolve.time
            notification.save(update_fields=["date_sent"])
            timeline_message_times[notification.id] = resolve.time
        resolve_timestamp = int(resolve.time.timestamp())
        edited = list(
            Message.objects.filter(
                realm=self.realm,
                recipient=stream.recipient,
                subject=RESOLVED_TOPIC_PREFIX + resolve.topic,
                last_edit_time__gte=edit_started,
            )
        )
        for message in edited:
            message.last_edit_time = resolve.time
            if message.edit_history is not None:
                history = orjson.loads(message.edit_history)
                for entry in history:
                    if entry["timestamp"] >= int(edit_started.timestamp()):
                        entry["timestamp"] = resolve_timestamp
                message.edit_history = orjson.dumps(history).decode()
        Message.objects.bulk_update(edited, ["last_edit_time", "edit_history"])

    def add_reactions(self, messages: list[PlannedMessage]) -> None:
        emoji_data: dict[str, EmojiData] = {}
        reactions: list[Reaction] = []
        for planned in messages:
            assert planned.message_id is not None
            for emoji_name, keys in planned.reactions.items():
                if emoji_name not in emoji_data:
                    emoji_data[emoji_name] = get_emoji_data(self.realm.id, emoji_name)
                reactions.extend(
                    Reaction(
                        user_profile=self.users[key],
                        message_id=planned.message_id,
                        emoji_name=emoji_name,
                        emoji_code=emoji_data[emoji_name].emoji_code,
                        reaction_type=emoji_data[emoji_name].reaction_type,
                    )
                    for key in keys
                )
        Reaction.objects.bulk_create(reactions)


def populate_dev_realm(
    data: DevData,
    *,
    string_id: str,
    now: datetime,
    num_messages: int = 0,
    extra_users: int = 0,
    extra_streams: int = 0,
    seed: int = 0,
) -> Realm:
    """Creates the organization described by data, which must already be validated.

    num_messages is the total number of conversation messages; when
    the scripted conversations have fewer, filler sentences make up
    the difference.  A fixed seed makes every rebuild look the same.
    """
    return DevRealmBuilder(
        data,
        string_id=string_id,
        now=now,
        num_messages=num_messages,
        extra_users=extra_users,
        extra_streams=extra_streams,
        seed=seed,
    ).build()


def localize_analytics_realm(analytics: AnalyticsData) -> None:
    """Renames what populate_analytics_db creates, which is in English.

    That command is upstream code, so it's left alone and its result
    is renamed afterwards.
    """
    realm = get_realm("analytics")
    realm.name = analytics.realm_name
    realm.default_language = DEV_REALM_LANGUAGE
    realm.save(update_fields=["name", "default_language"])

    for old_email, person in [
        ("shylock@analytics.ds", analytics.owner),
        ("bassanio@analytics.ds", analytics.guest),
    ]:
        user = UserProfile.objects.get(realm=realm, delivery_email=old_email)
        new_email = f"{person.key}@{ANALYTICS_EMAIL_DOMAIN}"
        if user.email == user.delivery_email:
            user.email = new_email
        user.delivery_email = new_email
        user.full_name = person.name
        user.default_language = DEV_REALM_LANGUAGE
        user.save(update_fields=["email", "delivery_email", "full_name", "default_language"])

    stream = get_stream("all", realm)
    stream.name = analytics.channel
    stream.save(update_fields=["name"])
