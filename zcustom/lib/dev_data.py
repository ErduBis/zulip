"""Loading and validation of the Chinese development organization data.

The data lives in zcustom/dev_data/ (format documented in its
README.md) and is consumed by zcustom.lib.dev_realm.  Validation is
strict and reports every problem at once, with the file and location,
because the data is written by hand by a separate localization session.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from django.conf import settings
from django.utils.translation import override as override_language
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zerver.lib.emoji import name_to_codepoint
from zerver.lib.topic import RESOLVED_TOPIC_PREFIX
from zerver.models import CustomProfileField, Realm, Stream, UserProfile
from zerver.models.channel_folders import ChannelFolder
from zerver.models.constants import MAX_TOPIC_NAME_LENGTH
from zerver.models.groups import NamedUserGroup

DEV_DATA_DIR = Path(__file__).resolve().parents[1] / "dev_data"
DEV_REALM_LANGUAGE = "zh-hans"
# Times in the data ("09:30") are written in the team's local time.
DEV_REALM_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEV_EMAIL_DOMAIN = "zulip.com"
ANALYTICS_EMAIL_DOMAIN = "analytics.ds"
DEFAULT_MESSAGE_INTERVAL = timedelta(minutes=2)
# The realm emoji created by the generator, usable in the data.
EXTRA_EMOJI_NAMES = {"green_tick", "zulip"}
WILDCARD_MENTION_NAMES = {"all", "everyone", "channel", "stream", "topic"}

# Each test user of upstream's populate_db has a purpose that some
# development tool or habit depends on; the data must keep one person
# for each, with the same role.
REPLACES_ROLES: dict[str, str] = {
    "desdemona": "owner",
    "iago": "administrator",
    "shiva": "moderator",
    "hamlet": "member",
    "cordelia": "member",
    "othello": "member",
    "prospero": "member",
    "aaron": "member",
    "zoe": "member",
    "polonius": "guest",
    "imported-user": "member",
}

# Bot emails are referenced by development tools, so only their
# display names are localized.  The value is the populate_db user
# whose replacement should own the bot.
BOT_TYPES: dict[str, int] = {
    "default-bot@zulip.com": UserProfile.DEFAULT_BOT,
    "webhook-bot@zulip.com": UserProfile.INCOMING_WEBHOOK_BOT,
    "outgoing-webhook@zulip.com": UserProfile.OUTGOING_WEBHOOK_BOT,
    "commit-bot@zulip.com": UserProfile.DEFAULT_BOT,
    "trac-bot@zulip.com": UserProfile.DEFAULT_BOT,
    "nagios-bot@zulip.com": UserProfile.DEFAULT_BOT,
}
BOT_EXPECTED_OWNERS: dict[str, str] = {
    "default-bot@zulip.com": "desdemona",
    "webhook-bot@zulip.com": "zoe",
    "outgoing-webhook@zulip.com": "aaron",
    "commit-bot@zulip.com": "desdemona",
    "trac-bot@zulip.com": "desdemona",
    "nagios-bot@zulip.com": "desdemona",
}

ROLE_VALUES: dict[str, int] = {
    "owner": UserProfile.ROLE_REALM_OWNER,
    "administrator": UserProfile.ROLE_REALM_ADMINISTRATOR,
    "moderator": UserProfile.ROLE_MODERATOR,
    "member": UserProfile.ROLE_MEMBER,
    "guest": UserProfile.ROLE_GUEST,
}

PROFILE_FIELD_TYPES: dict[str, int] = {
    "short_text": CustomProfileField.SHORT_TEXT,
    "paragraph": CustomProfileField.PARAGRAPH,
    "dropdown": CustomProfileField.DROPDOWN,
    "date": CustomProfileField.DATE,
    "url": CustomProfileField.URL,
    "user": CustomProfileField.USER,
    "external_account": CustomProfileField.EXTERNAL_ACCOUNT,
    "pronouns": CustomProfileField.PRONOUNS,
}
GITHUB_FIELD_NAME = "GitHub"
MIN_ALERT_WORDS = 8

Key = Annotated[str, Field(pattern=r"^[a-z0-9]+$")]
Text = Annotated[str, Field(min_length=1, max_length=settings.MAX_MESSAGE_LENGTH)]
Duration = Annotated[str, Field(pattern=r"^(\d+d)?(\d+h)?(\d+m)?(\d+s)?$", min_length=2)]
ChannelName = Annotated[str, Field(min_length=1, max_length=Stream.MAX_NAME_LENGTH)]
TopicName = Annotated[str, Field(min_length=1, max_length=MAX_TOPIC_NAME_LENGTH)]


class DevDataError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


class DataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


class RealmData(DataModel):
    name: Annotated[str, Field(min_length=1, max_length=Realm.MAX_REALM_NAME_LENGTH)]
    name_alternatives: list[str] = []
    description: Annotated[str, Field(max_length=Realm.MAX_REALM_DESCRIPTION_LENGTH)] = ""
    welcome_message_custom_text: Annotated[
        str, Field(max_length=Realm.MAX_REALM_WELCOME_MESSAGE_CUSTOM_TEXT_LENGTH)
    ] = ""


class MemberData(DataModel):
    key: Key
    name: Annotated[str, Field(min_length=1, max_length=UserProfile.MAX_NAME_LENGTH)]
    role: Literal["owner", "administrator", "moderator", "member", "guest"]
    replaces: (
        Literal[
            "desdemona",
            "iago",
            "shiva",
            "hamlet",
            "cordelia",
            "othello",
            "prospero",
            "aaron",
            "zoe",
            "polonius",
            "imported-user",
        ]
        | None
    ) = None
    timezone: str
    is_staff: bool = False
    imported_stub: bool = False
    profile: dict[str, str | list[str]] = {}

    @property
    def email(self) -> str:
        return f"{self.key}@{DEV_EMAIL_DOMAIN}"


class BotData(DataModel):
    email: Literal[
        "default-bot@zulip.com",
        "webhook-bot@zulip.com",
        "outgoing-webhook@zulip.com",
        "commit-bot@zulip.com",
        "trac-bot@zulip.com",
        "nagios-bot@zulip.com",
    ]
    name: Annotated[str, Field(min_length=1, max_length=UserProfile.MAX_NAME_LENGTH)]
    owner: str


class ProfileFieldData(DataModel):
    name: Annotated[str, Field(min_length=1, max_length=CustomProfileField.NAME_MAX_LENGTH)]
    type: Literal[
        "short_text", "paragraph", "dropdown", "date", "url", "user", "external_account", "pronouns"
    ]
    hint: Annotated[str, Field(max_length=CustomProfileField.HINT_MAX_LENGTH)] = ""
    options: list[Annotated[str, Field(min_length=1)]] | None = None


class FolderData(DataModel):
    name: Annotated[str, Field(min_length=1, max_length=ChannelFolder.MAX_NAME_LENGTH)]
    description: Annotated[str, Field(max_length=ChannelFolder.MAX_DESCRIPTION_LENGTH)] = ""


class ChannelData(DataModel):
    name: ChannelName
    description: Annotated[str, Field(max_length=Stream.MAX_DESCRIPTION_LENGTH)]
    folder: str | None = None
    creator: str | None = None
    private: bool = False
    web_public: bool = False
    admins_only_post: bool = False
    default_channel: bool = False
    subscribers: Literal["everyone", "members"] | list[str]


class UserGroupData(DataModel):
    name: Annotated[str, Field(min_length=1, max_length=NamedUserGroup.MAX_NAME_LENGTH)]
    description: str = ""
    members: list[str] = []
    subgroups: list[str] = []


class ChannelTarget(DataModel):
    channel: str
    topic: TopicName


class DirectTarget(DataModel):
    direct: Annotated[list[str], Field(min_length=1)]


class DraftData(DataModel):
    owner: str
    to: ChannelTarget | DirectTarget | None = None
    text: Text


class ScheduledMessageData(DataModel):
    sender: str = Field(alias="from")
    to: ChannelTarget | DirectTarget
    deliver_in_days: Annotated[int, Field(ge=1)]
    text: Text


class LinkifierData(DataModel):
    pattern: Annotated[str, Field(min_length=1)]
    url_template: Annotated[str, Field(min_length=1)]


class AnalyticsPersonData(DataModel):
    key: Key
    name: Annotated[str, Field(min_length=1, max_length=UserProfile.MAX_NAME_LENGTH)]


class AnalyticsData(DataModel):
    realm_name: Annotated[str, Field(min_length=1, max_length=Realm.MAX_REALM_NAME_LENGTH)]
    owner: AnalyticsPersonData
    guest: AnalyticsPersonData
    channel: ChannelName


class OrgData(DataModel):
    realm: RealmData
    members: list[MemberData]
    bots: list[BotData]
    custom_profile_fields: list[ProfileFieldData] = []
    channel_folders: list[FolderData] = []
    channels: list[ChannelData] = []
    user_groups: list[UserGroupData] = []
    drafts: list[DraftData] = []
    scheduled_messages: list[ScheduledMessageData] = []
    alert_words: list[Annotated[str, Field(min_length=1)]] = []
    linkifiers: list[LinkifierData] = []
    analytics: AnalyticsData


class DaysAgoStart(DataModel):
    days_ago: Annotated[int, Field(ge=1)]
    time: Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class HoursAgoStart(DataModel):
    hours_ago: Annotated[int, Field(ge=1)]


Start: TypeAlias = DaysAgoStart | HoursAgoStart


class MessageData(DataModel):
    sender: str = Field(alias="from")
    after: Duration | None = None
    text: Text
    reactions: dict[str, list[str]] = {}


class TopicData(DataModel):
    topic: TopicName
    start: Start
    resolved: bool = False
    resolved_by: str | None = None
    messages: Annotated[list[MessageData], Field(min_length=1)]


class ConversationFileData(DataModel):
    channel: str
    topics: list[TopicData]


class DirectConversationData(DataModel):
    members: Annotated[list[str], Field(min_length=1)]
    start: Start
    messages: Annotated[list[MessageData], Field(min_length=1)]


class FillerData(DataModel):
    topics: dict[str, list[TopicName]] = {}
    sentences: list[Text] = []


@dataclass(frozen=True)
class ConversationFile:
    filename: str
    data: ConversationFileData


@dataclass(frozen=True)
class DevData:
    org: OrgData
    conversations: list[ConversationFile]
    direct_messages: list[DirectConversationData]
    filler: FillerData

    def member_by_replaces(self, replaces: str) -> MemberData | None:
        return next((member for member in self.org.members if member.replaces == replaces), None)

    @property
    def creator(self) -> MemberData:
        creator = self.member_by_replaces("desdemona")
        assert creator is not None
        return creator


def builtin_channel_names() -> list[str]:
    """The channels do_create_realm creates, named in the realm's language."""
    with override_language(DEV_REALM_LANGUAGE):
        return [
            str(Realm.DEFAULT_NOTIFICATION_STREAM_NAME),
            str(Realm.ZULIP_SANDBOX_CHANNEL_NAME),
            str(Realm.ZULIP_DISCUSSION_CHANNEL_NAME),
        ]


def parse_duration(duration: str) -> timedelta:
    amounts = {unit: int(amount) for amount, unit in re.findall(r"(\d+)([dhms])", duration)}
    return timedelta(
        days=amounts.get("d", 0),
        hours=amounts.get("h", 0),
        minutes=amounts.get("m", 0),
        seconds=amounts.get("s", 0),
    )


def message_offsets(messages: list[MessageData]) -> list[timedelta]:
    """Offsets of each message from the conversation start."""
    offsets = [timedelta(0)]
    for message in messages[1:]:
        interval = (
            DEFAULT_MESSAGE_INTERVAL if message.after is None else parse_duration(message.after)
        )
        offsets.append(offsets[-1] + interval)
    return offsets


def conversation_start_time(start: Start, now: datetime) -> datetime:
    if isinstance(start, HoursAgoStart):
        return now - timedelta(hours=start.hours_ago)
    local_date = now.astimezone(DEV_REALM_TIMEZONE).date() - timedelta(days=start.days_ago)
    hour, minute = (int(part) for part in start.time.split(":"))
    local_start = datetime.combine(local_date, time(hour, minute), tzinfo=DEV_REALM_TIMEZONE)
    return local_start.astimezone(timezone.utc)


def format_validation_error(filename: str, error: ValidationError) -> list[str]:
    return [
        f"{filename}: {'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    ]


def parse_dev_data(
    org: object,
    conversations: Iterable[tuple[str, object]],
    direct_messages: object,
    filler: object,
) -> DevData:
    """Builds DevData from already-loaded YAML values, checking only their shape."""
    errors: list[str] = []

    def parse(model: type[DataModel], filename: str, value: object) -> DataModel | None:
        try:
            return model.model_validate(value)
        except ValidationError as e:
            errors.extend(format_validation_error(filename, e))
            return None

    org_data = parse(OrgData, "org.yaml", org)
    conversation_files = []
    for filename, value in conversations:
        conversation = parse(ConversationFileData, filename, value)
        if conversation is not None:
            assert isinstance(conversation, ConversationFileData)
            conversation_files.append(ConversationFile(filename, conversation))
    direct_message_list = []
    if not isinstance(direct_messages, list):
        errors.append("direct_messages.yaml: 顶层应当是列表")
    else:
        for i, value in enumerate(direct_messages):
            conversation = parse(DirectConversationData, f"direct_messages.yaml: [{i}]", value)
            if conversation is not None:
                assert isinstance(conversation, DirectConversationData)
                direct_message_list.append(conversation)
    filler_data = parse(FillerData, "filler.yaml", filler)

    if errors:
        raise DevDataError(errors)
    assert isinstance(org_data, OrgData)
    assert isinstance(filler_data, FillerData)
    return DevData(org_data, conversation_files, direct_message_list, filler_data)


def load_dev_data(data_dir: Path = DEV_DATA_DIR) -> DevData:
    def load(path: Path) -> object:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.load(f, Loader=yaml.CSafeLoader)
        except (OSError, yaml.YAMLError) as e:
            raise DevDataError([f"{path.relative_to(data_dir)}: {e}"])

    conversations = [
        (str(path.relative_to(data_dir)), load(path))
        for path in sorted((data_dir / "conversations").glob("*.yaml"))
    ]
    return parse_dev_data(
        load(data_dir / "org.yaml"),
        conversations,
        load(data_dir / "direct_messages.yaml"),
        load(data_dir / "filler.yaml"),
    )


@dataclass
class DataIndex:
    """Lookups shared by the validation checks."""

    members: dict[str, MemberData]
    display_names: set[str]
    group_names: set[str]
    builtin_channels: list[str]
    channels: dict[str, ChannelData | None]
    subscribers: dict[str, set[str]]
    scripted_topics: dict[tuple[str, str], bool] = field(default_factory=dict)


def channel_subscriber_keys(data: DevData) -> dict[str, set[str]]:
    """Member keys subscribed to each channel, including the built-in ones.

    Imported stub users never signed up, so they don't get the
    built-in default channels.
    """
    members = data.org.members
    subscribers: dict[str, set[str]] = {
        name: {member.key for member in members if not member.imported_stub}
        for name in builtin_channel_names()
    }
    for channel in data.org.channels:
        if channel.subscribers == "everyone":
            keys = {member.key for member in members}
        elif channel.subscribers == "members":
            keys = {member.key for member in members if member.role != "guest"}
        else:
            keys = set(channel.subscribers)
        if channel.creator is not None:
            keys.add(channel.creator)
        subscribers[channel.name] = keys
    return subscribers


def can_post(index: DataIndex, key: str, channel_name: str) -> bool:
    member = index.members.get(key)
    if member is None or member.imported_stub:
        return False
    if key not in index.subscribers.get(channel_name, set()):
        return False
    channel = index.channels.get(channel_name)
    return not (
        channel is not None
        and channel.admins_only_post
        and member.role not in ("owner", "administrator")
    )


def can_view(index: DataIndex, key: str, channel_name: str) -> bool:
    member = index.members.get(key)
    return (
        member is not None
        and not member.imported_stub
        and key in index.subscribers.get(channel_name, set())
    )


def find_duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates = []
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            duplicates.append(value)
        seen.add(normalized)
    return duplicates


def check_text(text: str, where: str, index: DataIndex, errors: list[str]) -> None:
    errors.extend(
        f"{where}: 提及的「{name}」不是成员或机器人的显示名"
        for name in re.findall(r"@_?\*\*([^*|\n]+?)(?:\|\d+)?\*\*", text)
        if name not in index.display_names and name not in WILDCARD_MENTION_NAMES
    )
    errors.extend(
        f"{where}: 提及的用户组「{name}」不存在"
        for name in re.findall(r"@_?\*(?!\*)([^*\n]+)\*(?!\*)", text)
        if name not in index.group_names
    )
    for channel, topic in re.findall(r"#\*\*([^*>\n]+?)(?:>([^*\n]+?))?\*\*", text):
        if channel not in index.channels:
            errors.append(f"{where}: 链接的频道「{channel}」不存在")
        elif topic and (channel, topic) not in index.scripted_topics:
            errors.append(f"{where}: 链接的话题「{channel}>{topic}」不存在")
        elif topic and index.scripted_topics[(channel, topic)]:
            errors.append(f"{where}: 链接的话题「{channel}>{topic}」已标记解决，标记后链接会失效")
    errors.extend(
        f"{where}: 图片「{path}」在仓库里不存在"
        for path in re.findall(r"\]\((/static/[^)\s]+)\)", text)
        if not (Path(settings.DEPLOY_ROOT) / path.removeprefix("/")).is_file()
    )
    errors.extend(
        f"{where}: 表情「:{name}:」不存在"
        for name in re.findall(r"(?<![\w:]):([a-z0-9_+\-]+):(?![\w:])", text)
        if name not in name_to_codepoint and name not in EXTRA_EMOJI_NAMES
    )


def check_reactions(
    message: MessageData,
    where: str,
    may_react: dict[str, bool],
    errors: list[str],
) -> None:
    for emoji_name, keys in message.reactions.items():
        if emoji_name not in name_to_codepoint and emoji_name not in EXTRA_EMOJI_NAMES:
            errors.append(f"{where}: 表情回应「{emoji_name}」不存在")
        errors.extend(
            f"{where}: 「{key}」不能对这条消息做表情回应（不存在或看不到这条消息）"
            for key in keys
            if not may_react.get(key, False)
        )
        errors.extend(
            f"{where}: 「{key}」重复回应了「{emoji_name}」" for key in find_duplicates(keys)
        )


def check_conversation_duration(
    start: Start, messages: list[MessageData], where: str, errors: list[str]
) -> None:
    duration = message_offsets(messages)[-1]
    if isinstance(start, HoursAgoStart):
        if duration >= timedelta(hours=start.hours_ago):
            errors.append(f"{where}: 整段对话时长 {duration} 不小于 hours_ago，会排到生成时刻之后")
        return
    hour, minute = (int(part) for part in start.time.split(":"))
    if timedelta(hours=hour, minutes=minute) + duration >= timedelta(days=1):
        errors.append(f"{where}: 整段对话会跨过当天 24:00，可能排到生成时刻之后")


def validate_members(data: DevData, require_complete: bool, errors: list[str]) -> None:
    org = data.org
    errors.extend(
        f"org.yaml: members: key「{key}」重复"
        for key in find_duplicates(member.key for member in org.members)
    )
    errors.extend(
        f"org.yaml: 显示名「{name}」重复（成员和机器人的显示名都不能重复）"
        for name in find_duplicates(
            [member.name for member in org.members] + [bot.name for bot in org.bots]
        )
    )

    replaced = [member.replaces for member in org.members if member.replaces is not None]
    errors.extend(
        f"org.yaml: members: 「replaces: {replaces}」出现了不止一次"
        for replaces in find_duplicates(replaced)
    )
    if "desdemona" not in replaced:
        errors.append("org.yaml: members: 缺少「replaces: desdemona」的成员（组织创建者）")
    if require_complete:
        missing = [replaces for replaces in REPLACES_ROLES if replaces not in replaced]
        if missing:
            errors.append(f"org.yaml: members: replaces 未覆盖: {', '.join(missing)}")

    field_names = {profile_field.name: profile_field for profile_field in org.custom_profile_fields}
    member_keys = {member.key for member in org.members}
    for i, member in enumerate(org.members):
        where = f"org.yaml: members[{i}]（{member.key}）"
        if member.replaces is not None and member.role != REPLACES_ROLES[member.replaces]:
            errors.append(
                f"{where}: 代替 {member.replaces} 的成员角色应当是 {REPLACES_ROLES[member.replaces]}"
            )
        if member.is_staff != (member.replaces == "iago"):
            errors.append(f"{where}: is_staff 只给代替 iago 的成员设为 true，而且必须设")
        if member.imported_stub != (member.replaces == "imported-user"):
            errors.append(
                f"{where}: imported_stub 只给代替 imported-user 的成员设为 true，而且必须设"
            )
        try:
            ZoneInfo(member.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"{where}: 时区「{member.timezone}」不存在")
        for field_name, value in member.profile.items():
            profile_field = field_names.get(field_name)
            if profile_field is None:
                errors.append(
                    f"{where}: profile: 资料字段「{field_name}」没有在 custom_profile_fields 里声明"
                )
                continue
            check_profile_value(
                profile_field, value, f"{where}: profile.{field_name}", member_keys, errors
            )


def check_profile_value(
    profile_field: ProfileFieldData,
    value: str | list[str],
    where: str,
    member_keys: set[str],
    errors: list[str],
) -> None:
    if profile_field.type == "user":
        if not isinstance(value, list) or not value:
            errors.append(f"{where}: 应当是成员 key 的列表")
        elif not set(value) <= member_keys:
            errors.append(f"{where}: 列表里有不存在的成员 key")
        return
    if not isinstance(value, str) or value == "":
        errors.append(f"{where}: 应当是非空字符串")
        return
    if profile_field.type == "dropdown":
        assert profile_field.options is not None
        if value not in profile_field.options:
            errors.append(f"{where}: 「{value}」不在 options 里")
    elif profile_field.type == "date":
        try:
            valid_date = re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and date.fromisoformat(value)
        except ValueError:
            valid_date = None
        if not valid_date:
            errors.append(f'{where}: 日期应当写成带引号的 "YYYY-MM-DD"')
    elif profile_field.type == "url" and not re.match(r"^https?://", value):
        errors.append(f"{where}: 链接应当以 http:// 或 https:// 开头")


def validate_org_settings(data: DevData, require_complete: bool, errors: list[str]) -> None:
    org = data.org
    members = {member.key: member for member in org.members}

    if sorted(bot.email for bot in org.bots) != sorted(BOT_TYPES):
        errors.append(f"org.yaml: bots: 必须恰好是这 6 个邮箱: {', '.join(BOT_TYPES)}")
    for i, bot in enumerate(org.bots):
        where = f"org.yaml: bots[{i}]（{bot.email}）"
        owner = members.get(bot.owner)
        if owner is None or owner.imported_stub or owner.role == "guest":
            errors.append(f"{where}: owner「{bot.owner}」不存在，或者是访客、导入占位用户")
        elif require_complete and owner.replaces != BOT_EXPECTED_OWNERS[bot.email]:
            errors.append(f"{where}: owner 应当是代替 {BOT_EXPECTED_OWNERS[bot.email]} 的成员")

    errors.extend(
        f"org.yaml: custom_profile_fields: 字段名「{name}」重复"
        for name in find_duplicates(
            profile_field.name for profile_field in org.custom_profile_fields
        )
    )
    for i, profile_field in enumerate(org.custom_profile_fields):
        where = f"org.yaml: custom_profile_fields[{i}]（{profile_field.name}）"
        if profile_field.type == "dropdown":
            if not profile_field.options or find_duplicates(profile_field.options):
                errors.append(f"{where}: dropdown 需要 options，且选项不能重复")
        elif profile_field.options is not None:
            errors.append(f"{where}: 只有 dropdown 类型可以写 options")
        if profile_field.type == "external_account" and profile_field.name != GITHUB_FIELD_NAME:
            errors.append(f"{where}: external_account 字段的 name 固定为 {GITHUB_FIELD_NAME}")
    if [f.type for f in org.custom_profile_fields].count("external_account") > 1:
        errors.append("org.yaml: custom_profile_fields: external_account 字段只能有一个")
    if require_complete:
        missing_types = set(PROFILE_FIELD_TYPES) - {f.type for f in org.custom_profile_fields}
        if missing_types:
            errors.append(
                f"org.yaml: custom_profile_fields: 缺少这些类型: {', '.join(sorted(missing_types))}"
            )

    errors.extend(
        f"org.yaml: channel_folders: 文件夹名「{name}」重复"
        for name in find_duplicates(folder.name for folder in org.channel_folders)
    )
    folder_names = {folder.name for folder in org.channel_folders}

    builtin = builtin_channel_names()
    errors.extend(
        f"org.yaml: channels: 频道名「{name}」重复（「全员」「沙盒」「Zulip」由建组织流程创建，不要再声明）"
        for name in find_duplicates([channel.name for channel in org.channels] + builtin)
    )
    for i, channel in enumerate(org.channels):
        where = f"org.yaml: channels[{i}]（{channel.name}）"
        if channel.folder is not None and channel.folder not in folder_names:
            errors.append(f"{where}: 文件夹「{channel.folder}」没有声明")
        if channel.creator is not None:
            creator = members.get(channel.creator)
            if creator is None or creator.imported_stub or creator.role == "guest":
                errors.append(
                    f"{where}: creator「{channel.creator}」不存在，或者是访客、导入占位用户"
                )
        if channel.private and channel.web_public:
            errors.append(f"{where}: private 和 web_public 不能同时为 true")
        if isinstance(channel.subscribers, list):
            errors.extend(
                f"{where}: subscribers 里的「{key}」不存在"
                for key in channel.subscribers
                if key not in members
            )
            errors.extend(
                f"{where}: subscribers 里的「{key}」重复"
                for key in find_duplicates(channel.subscribers)
            )

    group_names = {group.name for group in org.user_groups}
    errors.extend(
        f"org.yaml: user_groups: 组名「{name}」重复"
        for name in find_duplicates(group.name for group in org.user_groups)
    )
    subgroup_map = {group.name: group.subgroups for group in org.user_groups}
    for i, group in enumerate(org.user_groups):
        where = f"org.yaml: user_groups[{i}]（{group.name}）"
        errors.extend(
            f"{where}: 组名不能以「{prefix}」开头"
            for prefix in NamedUserGroup.INVALID_NAME_PREFIXES
            if group.name.startswith(prefix)
        )
        errors.extend(
            f"{where}: members 里的「{key}」不存在" for key in group.members if key not in members
        )
        errors.extend(
            f"{where}: subgroups 里的「{subgroup}」不存在"
            for subgroup in group.subgroups
            if subgroup not in group_names
        )
        if group_contains_itself(group.name, subgroup_map):
            errors.append(f"{where}: 子组形成了循环")

    if len(set(org.alert_words)) != len(org.alert_words):
        errors.append("org.yaml: alert_words: 有重复的词")
    if require_complete and len(org.alert_words) < MIN_ALERT_WORDS:
        errors.append(f"org.yaml: alert_words: 至少 {MIN_ALERT_WORDS} 个词")

    for i, linkifier in enumerate(org.linkifiers):
        try:
            re.compile(linkifier.pattern)
        except re.error as e:
            errors.append(f"org.yaml: linkifiers[{i}]: 正则表达式有误: {e}")
        if not linkifier.url_template.startswith(("https://example.com/", "http://example.com/")):
            errors.append(f"org.yaml: linkifiers[{i}]: url_template 只能用 example.com")

    analytics = org.analytics
    if analytics.owner.key == analytics.guest.key:
        errors.append("org.yaml: analytics: owner 和 guest 的 key 不能相同")


def group_contains_itself(name: str, subgroup_map: dict[str, list[str]]) -> bool:
    pending = list(subgroup_map.get(name, []))
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == name:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(subgroup_map.get(current, []))
    return False


def check_target(
    target: ChannelTarget | DirectTarget | None,
    sender: str,
    where: str,
    index: DataIndex,
    errors: list[str],
) -> None:
    if isinstance(target, ChannelTarget):
        if target.channel not in index.channels:
            errors.append(f"{where}: 频道「{target.channel}」不存在")
        elif not can_post(index, sender, target.channel):
            errors.append(f"{where}: 「{sender}」不能在「{target.channel}」发言")
    elif isinstance(target, DirectTarget):
        errors.extend(
            f"{where}: 私信对象「{key}」不存在" for key in target.direct if key not in index.members
        )


def validate_drafts_and_scheduled(
    data: DevData, index: DataIndex, require_complete: bool, errors: list[str]
) -> None:
    org = data.org
    for i, draft in enumerate(org.drafts):
        where = f"org.yaml: drafts[{i}]"
        owner = index.members.get(draft.owner)
        if owner is None or owner.imported_stub:
            errors.append(f"{where}: owner「{draft.owner}」不存在或是导入占位用户")
            continue
        check_target(draft.to, draft.owner, where, index, errors)
        check_text(draft.text, where, index, errors)
    for i, scheduled in enumerate(org.scheduled_messages):
        where = f"org.yaml: scheduled_messages[{i}]"
        sender = index.members.get(scheduled.sender)
        if sender is None or sender.imported_stub:
            errors.append(f"{where}: from「{scheduled.sender}」不存在或是导入占位用户")
            continue
        check_target(scheduled.to, scheduled.sender, where, index, errors)
        check_text(scheduled.text, where, index, errors)

    admin = data.member_by_replaces("iago")
    if require_complete and admin is not None:
        drafts = [draft for draft in org.drafts if draft.owner == admin.key]
        admin_scheduled = [
            message for message in org.scheduled_messages if message.sender == admin.key
        ]
        if len(drafts) < 2:
            errors.append("org.yaml: drafts: 代替 iago 的成员至少要有两条草稿")
        if not any(isinstance(message.to, ChannelTarget) for message in admin_scheduled) or not any(
            isinstance(message.to, DirectTarget) and message.to.direct == [admin.key]
            for message in admin_scheduled
        ):
            errors.append(
                "org.yaml: scheduled_messages: 代替 iago 的成员至少要有一条发往频道、一条发给自己的定时消息"
            )


def validate_conversations(data: DevData, index: DataIndex, errors: list[str]) -> None:
    for conversation in data.conversations:
        channel_name = conversation.data.channel
        if channel_name not in index.channels:
            errors.append(f"{conversation.filename}: channel「{channel_name}」不存在")
            continue
        topic_names = [topic.topic for topic in conversation.data.topics]
        errors.extend(
            f"{conversation.filename}: 话题「{topic_name}」重复"
            for topic_name in find_duplicates(topic_names)
        )
        may_react = {key: can_view(index, key, channel_name) for key in index.members}
        for i, topic in enumerate(conversation.data.topics):
            where = f"{conversation.filename}: topics[{i}]（{topic.topic}）"
            if topic.topic.startswith(RESOLVED_TOPIC_PREFIX.strip()):
                errors.append(f"{where}: 话题名不要自己加「✔」，用 resolved: true")
            if topic.resolved_by is not None and not topic.resolved:
                errors.append(f"{where}: 写了 resolved_by 但没有 resolved: true")
            if topic.resolved:
                resolver = topic.resolved_by or topic.messages[-1].sender
                member = index.members.get(resolver)
                if (
                    member is None
                    or member.role == "guest"
                    or not can_post(index, resolver, channel_name)
                ):
                    errors.append(f"{where}: 「{resolver}」不能标记这个话题为已解决")
            check_conversation_duration(topic.start, topic.messages, where, errors)
            for j, message in enumerate(topic.messages):
                message_where = f"{where}: messages[{j}]"
                if not can_post(index, message.sender, channel_name):
                    errors.append(
                        f"{message_where}: 「{message.sender}」不能在「{channel_name}」发言"
                    )
                check_text(message.text, message_where, index, errors)
                check_reactions(message, message_where, may_react, errors)


def validate_direct_messages(data: DevData, index: DataIndex, errors: list[str]) -> None:
    for i, conversation in enumerate(data.direct_messages):
        where = f"direct_messages.yaml: [{i}]"
        errors.extend(
            f"{where}: members 里的「{key}」重复" for key in find_duplicates(conversation.members)
        )
        valid_members = True
        for key in conversation.members:
            member = index.members.get(key)
            if member is None or member.imported_stub:
                errors.append(f"{where}: 「{key}」不存在或是导入占位用户")
                valid_members = False
        if not valid_members:
            continue
        may_react = {key: key in conversation.members for key in index.members}
        check_conversation_duration(conversation.start, conversation.messages, where, errors)
        for j, message in enumerate(conversation.messages):
            message_where = f"{where}: messages[{j}]"
            if message.sender not in conversation.members:
                errors.append(f"{message_where}: 发言人「{message.sender}」不是这段私信的成员")
            check_text(message.text, message_where, index, errors)
            check_reactions(message, message_where, may_react, errors)


def validate_filler(data: DevData, index: DataIndex, errors: list[str]) -> None:
    for channel_name, topics in data.filler.topics.items():
        where = f"filler.yaml: topics.{channel_name}"
        if channel_name not in index.channels:
            errors.append(f"{where}: 频道不存在")
            continue
        if not topics:
            errors.append(f"{where}: 至少一个话题名")
        if not any(can_post(index, key, channel_name) for key in index.members):
            errors.append(f"{where}: 没有成员能在这个频道发言")
        errors.extend(
            f"{where}: 话题名不要自己加「✔」"
            for topic in topics
            if topic.startswith(RESOLVED_TOPIC_PREFIX.strip())
        )
    if data.filler.topics and not data.filler.sentences:
        errors.append("filler.yaml: sentences: 列出了话题就至少要有一个短句")
    for i, sentence in enumerate(data.filler.sentences):
        check_text(sentence, f"filler.yaml: sentences[{i}]", index, errors)


def build_index(data: DevData) -> DataIndex:
    builtin = builtin_channel_names()
    channels: dict[str, ChannelData | None] = dict.fromkeys(builtin)
    channels.update({channel.name: channel for channel in data.org.channels})
    index = DataIndex(
        members={member.key: member for member in data.org.members},
        display_names={member.name for member in data.org.members}
        | {bot.name for bot in data.org.bots},
        group_names={group.name for group in data.org.user_groups},
        builtin_channels=builtin,
        channels=channels,
        subscribers=channel_subscriber_keys(data),
    )
    for conversation in data.conversations:
        for topic in conversation.data.topics:
            key = (conversation.data.channel, topic.topic)
            index.scripted_topics[key] = index.scripted_topics.get(key, False) or topic.resolved
    return index


def validate_dev_data(data: DevData, *, require_complete: bool) -> list[str]:
    """Returns every problem found in the data, as messages for its authors.

    require_complete additionally checks that the data covers
    everything the development environment relies on; tests use small
    incomplete data sets without it.
    """
    errors: list[str] = []
    validate_members(data, require_complete, errors)
    validate_org_settings(data, require_complete, errors)
    index = build_index(data)
    validate_drafts_and_scheduled(data, index, require_complete, errors)
    validate_conversations(data, index, errors)
    validate_direct_messages(data, index, errors)
    validate_filler(data, index, errors)
    return errors


def load_and_validate_dev_data(
    data_dir: Path = DEV_DATA_DIR, *, require_complete: bool = True
) -> DevData:
    data = load_dev_data(data_dir)
    errors = validate_dev_data(data, require_complete=require_complete)
    if errors:
        raise DevDataError(errors)
    return data
