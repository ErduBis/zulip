import copy
import random
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from unittest import mock

import orjson
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.timezone import now as timezone_now

from zcustom.lib.dev_data import (
    BOT_TYPES,
    REPLACES_ROLES,
    DevDataError,
    load_and_validate_dev_data,
    parse_dev_data,
    validate_dev_data,
)
from zcustom.lib.dev_realm import (
    PlannedResolve,
    localize_analytics_realm,
    plan_filler_messages,
    populate_dev_realm,
)
from zerver.actions.create_realm import do_create_realm
from zerver.lib.server_initialization import create_users
from zerver.lib.streams import ensure_stream
from zerver.lib.test_classes import ZulipTestCase
from zerver.lib.topic import messages_for_topic
from zerver.models import (
    CustomProfileField,
    CustomProfileFieldValue,
    DefaultStream,
    Draft,
    Message,
    NamedUserGroup,
    OnboardingUserMessage,
    Reaction,
    RealmAuditLog,
    ScheduledMessage,
    Stream,
    SubMessage,
    Subscription,
    UserMessage,
    UserProfile,
)
from zerver.models.alert_words import AlertWord
from zerver.models.groups import SystemGroups
from zerver.models.onboarding_steps import OnboardingStep
from zerver.models.realm_audit_logs import AuditLogEventType
from zerver.models.realms import get_realm
from zerver.models.streams import get_stream
from zerver.models.users import get_system_bot

# Any: these mirror untyped YAML documents.
RawData = tuple[dict[str, Any], dict[str, Any], list[Any], dict[str, Any]]


def make_raw_data() -> RawData:
    """A small organization exercising every feature of the data format."""
    org: dict[str, Any] = {
        "realm": {
            "name": "取经项目组（测试）",
            "description": "测试用的组织。",
            "welcome_message_custom_text": "欢迎加入取经项目组！",
        },
        "members": [
            {
                "key": "tangseng",
                "name": "唐僧",
                "role": "owner",
                "replaces": "desdemona",
                "timezone": "Asia/Shanghai",
                "profile": {
                    "职务": "项目负责人",
                    "常用兵器": "九环锡杖",
                    "生日": "1990-04-08",
                    "GitHub": "zulip",
                },
            },
            {
                "key": "sunwukong",
                "name": "孙悟空",
                "role": "administrator",
                "replaces": "iago",
                "is_staff": True,
                "timezone": "Asia/Shanghai",
                "profile": {"常用兵器": "金箍棒", "导师": ["tangseng"]},
            },
            {
                "key": "zhubajie",
                "name": "猪八戒",
                "role": "member",
                "replaces": "hamlet",
                "timezone": "America/Los_Angeles",
            },
            {"key": "shaseng", "name": "沙僧", "role": "member", "timezone": "Asia/Shanghai"},
            {
                "key": "guanyin",
                "name": "观音",
                "role": "guest",
                "replaces": "polonius",
                "timezone": "Asia/Shanghai",
            },
            {
                "key": "tudi",
                "name": "土地",
                "role": "member",
                "replaces": "imported-user",
                "imported_stub": True,
                "timezone": "Asia/Shanghai",
            },
        ],
        "bots": [
            {"email": email, "name": f"机器人{i}", "owner": "tangseng"}
            for i, email in enumerate(BOT_TYPES)
        ],
        "custom_profile_fields": [
            {"name": "职务", "type": "short_text", "hint": "你负责什么？"},
            {"name": "常用兵器", "type": "dropdown", "options": ["九环锡杖", "金箍棒"]},
            {"name": "生日", "type": "date"},
            {"name": "导师", "type": "user"},
            {"name": "GitHub", "type": "external_account"},
        ],
        "channel_folders": [{"name": "取经事务", "description": "正事"}],
        "channels": [
            {
                "name": "取经路线",
                "description": "路线规划",
                "folder": "取经事务",
                "creator": "tangseng",
                "subscribers": "members",
                "default_channel": True,
            },
            {
                "name": "天庭公告",
                "description": "只有管理员能发言",
                "admins_only_post": True,
                "subscribers": "everyone",
            },
            {
                "name": "核心小组",
                "description": "私有频道",
                "private": True,
                "subscribers": ["sunwukong"],
                "creator": "tangseng",
            },
            {
                "name": "西行见闻",
                "description": "网络公开",
                "web_public": True,
                "subscribers": "everyone",
            },
        ],
        "user_groups": [
            {"name": "取经团队", "members": ["tangseng"], "subgroups": ["徒弟"]},
            {"name": "徒弟", "description": "三个徒弟", "members": ["sunwukong", "zhubajie"]},
        ],
        "drafts": [
            {
                "owner": "sunwukong",
                "to": {"channel": "取经路线", "topic": "借扇"},
                "text": "草稿一",
            },
            {"owner": "sunwukong", "to": {"direct": ["tangseng"]}, "text": "草稿二"},
            {"owner": "sunwukong", "text": "草稿三"},
        ],
        "scheduled_messages": [
            {
                "from": "sunwukong",
                "to": {"channel": "取经路线", "topic": "周年"},
                "deliver_in_days": 365,
                "text": "一周年",
            },
            {
                "from": "sunwukong",
                "to": {"direct": ["sunwukong"]},
                "deliver_in_days": 30,
                "text": "备忘",
            },
        ],
        "alert_words": ["妖怪", "斋饭", "师父", "火焰山", "芭蕉扇"],
        "linkifiers": [
            {"pattern": "文牒#(?P<id>[0-9]+)", "url_template": "https://example.com/wendie/{id}"}
        ],
        "analytics": {
            "realm_name": "天庭数据司",
            "owner": {"key": "taibai", "name": "太白金星"},
            "guest": {"key": "tudigong", "name": "土地公"},
            "channel": "全天庭",
        },
    }
    conversation: dict[str, Any] = {
        "channel": "取经路线",
        "topics": [
            {
                "topic": "过火焰山",
                "start": {"days_ago": 3, "time": "09:30"},
                "resolved": True,
                "resolved_by": "tangseng",
                "messages": [
                    {"from": "tangseng", "text": "@**孙悟空** 今天能过去吗？"},
                    {
                        "from": "sunwukong",
                        "after": "5m",
                        "text": "我去借**芭蕉扇** :fire:",
                        "reactions": {"+1": ["tangseng", "zhubajie"], "green_tick": ["tangseng"]},
                    },
                    {
                        "from": "zhubajie",
                        "after": "1h",
                        "text": "@*取经团队* 看图 [示意](/static/images/characters/seahorse.png)",
                    },
                ],
            },
            {
                "topic": "今晚住哪",
                "start": {"hours_ago": 3},
                "messages": [
                    {"from": "sunwukong", "text": "/poll 今晚住哪？\n客栈\n寺庙"},
                    {"from": "zhubajie", "after": "30m", "text": "详见 #**取经路线**"},
                ],
            },
        ],
    }
    builtin_conversation: dict[str, Any] = {
        "channel": "全员",
        "topics": [
            {
                "topic": "问候",
                "start": {"days_ago": 2, "time": "08:00"},
                "messages": [{"from": "guanyin", "text": "各位好。"}],
            },
        ],
    }
    private_conversation: dict[str, Any] = {
        "channel": "核心小组",
        "topics": [
            {
                "topic": "机密",
                "start": {"days_ago": 1, "time": "20:00"},
                "messages": [{"from": "tangseng", "text": "只有我们看得到。"}],
            },
        ],
    }
    direct_messages: list[Any] = [
        {
            "members": ["tangseng", "sunwukong"],
            "start": {"days_ago": 2, "time": "21:00"},
            "messages": [
                {"from": "tangseng", "text": "悟空，明天的行程？"},
                {
                    "from": "sunwukong",
                    "after": "10m",
                    "text": "已发",
                    "reactions": {"heart": ["tangseng"]},
                },
            ],
        },
        {
            "members": ["tangseng", "sunwukong", "zhubajie"],
            "start": {"hours_ago": 2},
            "messages": [{"from": "zhubajie", "text": "开饭了"}],
        },
        {
            "members": ["shaseng"],
            "start": {"hours_ago": 1},
            "messages": [{"from": "shaseng", "text": "备忘：挑担"}],
        },
    ]
    filler: dict[str, Any] = {
        "topics": {"取经路线": ["问路"], "天庭公告": ["通知"]},
        "sentences": ["收到。", "好的", "多行\n- 一\n- 二"],
    }
    return (
        org,
        {
            "conversations/qujing.yaml": conversation,
            "conversations/quanyuan.yaml": builtin_conversation,
            "conversations/hexin.yaml": private_conversation,
        },
        direct_messages,
        filler,
    )


def make_complete_raw_data() -> RawData:
    """Extends make_raw_data with everything require_complete demands."""
    org, conversations, direct_messages, filler = make_raw_data()
    present = {member.get("replaces") for member in org["members"]}
    for replaces, role in REPLACES_ROLES.items():
        if replaces not in present:
            key = "x" + replaces.replace("-", "")
            org["members"].append(
                {
                    "key": key,
                    "name": f"补充{key}",
                    "role": role,
                    "replaces": replaces,
                    "timezone": "Asia/Shanghai",
                }
            )
    owners = {"default-bot@zulip.com": "tangseng", "webhook-bot@zulip.com": "xzoe"}
    owners["outgoing-webhook@zulip.com"] = "xaaron"
    for bot in org["bots"]:
        bot["owner"] = owners.get(bot["email"], "tangseng")
    org["custom_profile_fields"] += [
        {"name": "简介", "type": "paragraph"},
        {"name": "主页", "type": "url"},
        {"name": "称谓", "type": "pronouns"},
    ]
    org["alert_words"] += ["紧箍咒", "通关文牒", "化缘"]
    return org, conversations, direct_messages, filler


def parse_raw(raw: RawData) -> Any:
    org, conversations, direct_messages, filler = raw
    return parse_dev_data(org, conversations.items(), direct_messages, filler)


def write_raw(raw: RawData, data_dir: Path) -> None:
    org, conversations, direct_messages, filler = raw

    def dump(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")

    dump(data_dir / "org.yaml", org)
    for filename, conversation in conversations.items():
        dump(data_dir / filename, conversation)
    dump(data_dir / "direct_messages.yaml", direct_messages)
    dump(data_dir / "filler.yaml", filler)


class DevRealmDataTest(ZulipTestCase):
    def validation_errors(self, raw: RawData, *, require_complete: bool = False) -> list[str]:
        return validate_dev_data(parse_raw(raw), require_complete=require_complete)

    def assert_error(self, raw: RawData, expected: str) -> None:
        errors = self.validation_errors(raw)
        self.assertTrue(
            any(expected in error for error in errors), f"{expected!r} not in {errors!r}"
        )

    def test_valid_data(self) -> None:
        self.assertEqual(self.validation_errors(make_raw_data()), [])
        self.assertEqual(
            self.validation_errors(make_complete_raw_data(), require_complete=True), []
        )

    def test_require_complete(self) -> None:
        errors = self.validation_errors(make_raw_data(), require_complete=True)
        self.assertIn(
            "org.yaml: members: replaces 未覆盖: shiva, cordelia, othello, prospero, aaron, zoe",
            errors,
        )
        self.assertTrue(any("缺少这些类型: paragraph, pronouns, url" in error for error in errors))
        self.assertTrue(any("alert_words: 至少 8 个词" in error for error in errors))

        org, conversations, direct_messages, filler = make_complete_raw_data()
        org["drafts"] = []
        org["scheduled_messages"] = []
        org["bots"][1]["owner"] = "tangseng"
        errors = self.validation_errors(
            (org, conversations, direct_messages, filler), require_complete=True
        )
        self.assertTrue(any("至少要有两条草稿" in error for error in errors))
        self.assertTrue(any("一条发给自己的定时消息" in error for error in errors))
        self.assertTrue(any("owner 应当是代替 zoe 的成员" in error for error in errors))

    def test_shape_errors(self) -> None:
        org, conversations, direct_messages, filler = make_raw_data()
        org["members"][0]["role"] = "boss"
        conversations["conversations/qujing.yaml"]["topics"][0]["start"]["time"] = 570
        with self.assertRaises(DevDataError) as e:
            parse_raw((org, conversations, direct_messages, filler))
        self.assertTrue(
            any(error.startswith("org.yaml: members.0.role:") for error in e.exception.errors)
        )
        self.assertTrue(
            any(
                error.startswith("conversations/qujing.yaml: topics.0.start.DaysAgoStart.time:")
                for error in e.exception.errors
            )
        )

        with self.assertRaises(DevDataError) as e:
            parse_dev_data(org, [], {"members": []}, {})
        self.assertIn("direct_messages.yaml: 顶层应当是列表", e.exception.errors)

    def test_member_errors(self) -> None:
        raw = make_raw_data()
        raw[0]["members"][1]["role"] = "member"
        self.assert_error(raw, "代替 iago 的成员角色应当是 administrator")

        raw = make_raw_data()
        raw[0]["members"][2]["is_staff"] = True
        self.assert_error(raw, "is_staff 只给代替 iago 的成员设为 true")

        raw = make_raw_data()
        raw[0]["members"][3]["imported_stub"] = True
        self.assert_error(raw, "imported_stub 只给代替 imported-user 的成员设为 true")

        raw = make_raw_data()
        raw[0]["members"][0]["replaces"] = None
        self.assert_error(raw, "缺少「replaces: desdemona」的成员")

        raw = make_raw_data()
        raw[0]["members"][3]["replaces"] = "hamlet"
        self.assert_error(raw, "「replaces: hamlet」出现了不止一次")

        raw = make_raw_data()
        raw[0]["members"][3]["key"] = "zhubajie"
        raw[0]["members"][3]["name"] = "猪八戒"
        self.assert_error(raw, "key「zhubajie」重复")
        self.assert_error(raw, "显示名「猪八戒」重复")

        raw = make_raw_data()
        raw[0]["members"][3]["timezone"] = "Mars/Olympus"
        self.assert_error(raw, "时区「Mars/Olympus」不存在")

    def test_profile_errors(self) -> None:
        raw = make_raw_data()
        profile = raw[0]["members"][0]["profile"]
        profile["常用兵器"] = "金箍棒2"
        profile["生日"] = "1990/04/08"
        profile["导师"] = ["nobody"]
        profile["未知"] = "x"
        raw[0]["custom_profile_fields"].append({"name": "主页", "type": "url"})
        profile["主页"] = "example.com"
        self.assert_error(raw, "「金箍棒2」不在 options 里")
        self.assert_error(raw, "日期应当写成带引号的")
        self.assert_error(raw, "列表里有不存在的成员 key")
        self.assert_error(raw, "资料字段「未知」没有在 custom_profile_fields 里声明")
        self.assert_error(raw, "链接应当以 http:// 或 https:// 开头")

        raw = make_raw_data()
        raw[0]["members"][0]["profile"]["导师"] = "tangseng"
        raw[0]["members"][1]["profile"]["常用兵器"] = ["金箍棒"]
        self.assert_error(raw, "应当是成员 key 的列表")
        self.assert_error(raw, "应当是非空字符串")

        raw = make_raw_data()
        fields = raw[0]["custom_profile_fields"]
        fields[0]["options"] = ["a"]
        fields[1]["options"] = ["九环锡杖", "九环锡杖"]
        fields[4]["name"] = "Github"
        fields.append({"name": "职务", "type": "external_account"})
        self.assert_error(raw, "只有 dropdown 类型可以写 options")
        self.assert_error(raw, "dropdown 需要 options，且选项不能重复")
        self.assert_error(raw, "external_account 字段的 name 固定为 GitHub")
        self.assert_error(raw, "external_account 字段只能有一个")
        self.assert_error(raw, "字段名「职务」重复")

    def test_org_errors(self) -> None:
        raw = make_raw_data()
        raw[0]["bots"].pop()
        raw[0]["bots"][0]["owner"] = "guanyin"
        self.assert_error(raw, "bots: 必须恰好是这 6 个邮箱")
        self.assert_error(raw, "owner「guanyin」不存在，或者是访客、导入占位用户")

        raw = make_raw_data()
        channels = raw[0]["channels"]
        channels[0]["folder"] = "不存在"
        channels[0]["creator"] = "tudi"
        channels[2]["web_public"] = True
        channels[2]["subscribers"] = ["sunwukong", "sunwukong", "nobody"]
        channels.append({"name": "全员", "description": "", "subscribers": "everyone"})
        raw[0]["channel_folders"].append({"name": "取经事务"})
        self.assert_error(raw, "文件夹「不存在」没有声明")
        self.assert_error(raw, "creator「tudi」不存在")
        self.assert_error(raw, "private 和 web_public 不能同时为 true")
        self.assert_error(raw, "subscribers 里的「nobody」不存在")
        self.assert_error(raw, "subscribers 里的「sunwukong」重复")
        self.assert_error(raw, "频道名「全员」重复")
        self.assert_error(raw, "文件夹名「取经事务」重复")

        raw = make_raw_data()
        groups = raw[0]["user_groups"]
        groups[1]["subgroups"] = ["取经团队", "不存在"]
        groups[1]["members"].append("nobody")
        groups.append({"name": "role:x"})
        self.assert_error(raw, "子组形成了循环")
        self.assert_error(raw, "subgroups 里的「不存在」不存在")
        self.assert_error(raw, "members 里的「nobody」不存在")
        self.assert_error(raw, "组名不能以「role:」开头")
        groups.append({"name": "徒弟"})
        self.assert_error(raw, "组名「徒弟」重复")

        raw = make_raw_data()
        raw[0]["alert_words"].append("妖怪")
        raw[0]["linkifiers"] = [{"pattern": "(", "url_template": "https://zulip.com/{id}"}]
        raw[0]["analytics"]["guest"]["key"] = "taibai"
        self.assert_error(raw, "alert_words: 有重复的词")
        self.assert_error(raw, "正则表达式有误")
        self.assert_error(raw, "url_template 只能用 example.com")
        self.assert_error(raw, "owner 和 guest 的 key 不能相同")

    def test_draft_and_scheduled_errors(self) -> None:
        raw = make_raw_data()
        raw[0]["drafts"] = [
            {"owner": "tudi", "text": "x"},
            {"owner": "guanyin", "to": {"channel": "取经路线", "topic": "t"}, "text": "x"},
            {"owner": "shaseng", "to": {"channel": "不存在", "topic": "t"}, "text": "x"},
            {"owner": "shaseng", "to": {"direct": ["nobody"]}, "text": "@**无名**"},
        ]
        raw[0]["scheduled_messages"] = [
            {"from": "nobody", "to": {"direct": ["shaseng"]}, "deliver_in_days": 1, "text": "x"},
            {
                "from": "shaseng",
                "to": {"channel": "天庭公告", "topic": "t"},
                "deliver_in_days": 1,
                "text": "x",
            },
        ]
        self.assert_error(raw, "drafts[0]: owner「tudi」不存在或是导入占位用户")
        self.assert_error(raw, "drafts[1]: 「guanyin」不能在「取经路线」发言")
        self.assert_error(raw, "drafts[2]: 频道「不存在」不存在")
        self.assert_error(raw, "drafts[3]: 私信对象「nobody」不存在")
        self.assert_error(raw, "drafts[3]: 提及的「无名」不是成员或机器人的显示名")
        self.assert_error(raw, "scheduled_messages[0]: from「nobody」不存在")
        self.assert_error(raw, "scheduled_messages[1]: 「shaseng」不能在「天庭公告」发言")

    def test_conversation_errors(self) -> None:
        raw = make_raw_data()
        topics = raw[1]["conversations/qujing.yaml"]["topics"]
        topics[1]["topic"] = "过火焰山"
        topics[1]["resolved_by"] = "zhubajie"
        topics[1]["start"] = {"hours_ago": 1}
        topics[1]["messages"][1]["after"] = "1h"
        topics[0]["start"]["time"] = "23:30"
        messages = topics[0]["messages"]
        messages[0]["from"] = "guanyin"
        messages[0]["text"] = (
            "@*无组* #**无频道** #**取经路线>无话题** #**取经路线>过火焰山** "
            "[图](/static/images/nothing.png) :no_such_emoji: 3:2:1"
        )
        messages[1]["reactions"] = {
            "no_such": ["tangseng"],
            "+1": ["guanyin", "tangseng", "tangseng"],
        }
        raw[1]["conversations/bad.yaml"] = {"channel": "不存在", "topics": []}
        raw[1]["conversations/resolved.yaml"] = {
            "channel": "西行见闻",
            "topics": [
                {
                    "topic": "✔ 已解决",
                    "start": {"days_ago": 1, "time": "08:00"},
                    "resolved": True,
                    "resolved_by": "guanyin",
                    "messages": [{"from": "guanyin", "text": "x"}],
                }
            ],
        }
        self.assert_error(raw, "conversations/bad.yaml: channel「不存在」不存在")
        self.assert_error(raw, "话题「过火焰山」重复")
        self.assert_error(raw, "写了 resolved_by 但没有 resolved: true")
        self.assert_error(raw, "整段对话时长 1:00:00 不小于 hours_ago")
        self.assert_error(raw, "整段对话会跨过当天 24:00")
        self.assert_error(raw, "messages[0]: 「guanyin」不能在「取经路线」发言")
        self.assert_error(raw, "提及的用户组「无组」不存在")
        self.assert_error(raw, "链接的频道「无频道」不存在")
        self.assert_error(raw, "链接的话题「取经路线>无话题」不存在")
        self.assert_error(raw, "链接的话题「取经路线>过火焰山」已标记解决")
        self.assert_error(raw, "图片「/static/images/nothing.png」在仓库里不存在")
        self.assert_error(raw, "表情「:no_such_emoji:」不存在")
        self.assert_error(raw, "表情回应「no_such」不存在")
        self.assert_error(raw, "「guanyin」不能对这条消息做表情回应")
        self.assert_error(raw, "「tangseng」重复回应了「+1」")
        self.assert_error(raw, "话题名不要自己加「✔」")
        self.assert_error(raw, "「guanyin」不能标记这个话题为已解决")
        errors = self.validation_errors(raw)
        self.assertFalse(any("「:2:」" in error for error in errors))

    def test_direct_message_and_filler_errors(self) -> None:
        raw = make_raw_data()
        raw[2][0]["members"] = ["tangseng", "tangseng", "tudi"]
        raw[2][1]["messages"][0]["from"] = "shaseng"
        raw[2][1]["messages"][0]["reactions"] = {"heart": ["guanyin"]}
        raw[3]["topics"] = {"不存在": ["x"], "核心小组": [], "取经路线": ["✔ x"]}
        raw[3]["sentences"] = ["@**无名**"]
        self.assert_error(raw, "members 里的「tangseng」重复")
        self.assert_error(raw, "「tudi」不存在或是导入占位用户")
        self.assert_error(raw, "发言人「shaseng」不是这段私信的成员")
        self.assert_error(raw, "「guanyin」不能对这条消息做表情回应")
        self.assert_error(raw, "filler.yaml: topics.不存在: 频道不存在")
        self.assert_error(raw, "filler.yaml: topics.核心小组: 至少一个话题名")
        self.assert_error(raw, "filler.yaml: topics.取经路线: 话题名不要自己加「✔」")
        self.assert_error(raw, "filler.yaml: sentences[0]: 提及的「无名」")

        raw = make_raw_data()
        raw[0]["channels"][2]["subscribers"] = []
        raw[0]["channels"][2]["creator"] = None
        raw[1].pop("conversations/hexin.yaml")
        raw[3]["topics"] = {"核心小组": ["x"]}
        raw[3]["sentences"] = []
        self.assert_error(raw, "filler.yaml: topics.核心小组: 没有成员能在这个频道发言")
        self.assert_error(raw, "列出了话题就至少要有一个短句")

    def test_load_from_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_raw(make_raw_data(), data_dir)
            data = load_and_validate_dev_data(data_dir, require_complete=False)
            self.assertEqual(data.creator.key, "tangseng")
            self.assertEqual(
                [conversation.filename for conversation in data.conversations],
                [
                    "conversations/hexin.yaml",
                    "conversations/quanyuan.yaml",
                    "conversations/qujing.yaml",
                ],
            )
            with self.assertRaises(DevDataError) as e:
                load_and_validate_dev_data(data_dir)
            self.assertTrue(any("replaces 未覆盖" in error for error in e.exception.errors))

            (data_dir / "filler.yaml").write_text("topics: [\n", encoding="utf-8")
            with self.assertRaises(DevDataError) as e:
                load_and_validate_dev_data(data_dir, require_complete=False)
            self.assertTrue(e.exception.errors[0].startswith("filler.yaml: "))

    def test_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_raw(make_raw_data(), data_dir)
            with self.assertRaisesRegex(CommandError, "replaces 未覆盖"):
                call_command("populate_dev_zh", "--check", "--data-dir", str(data_dir))

            write_raw(make_complete_raw_data(), data_dir)
            stdout = StringIO()
            call_command("populate_dev_zh", "--check", "--data-dir", str(data_dir), stdout=stdout)
            self.assertEqual(stdout.getvalue(), "Organization data is valid.\n")
            with self.assertRaisesRegex(CommandError, "only builds the development database"):
                call_command("populate_dev_zh", "--data-dir", str(data_dir))

    def test_repository_data_is_complete(self) -> None:
        load_and_validate_dev_data()


class DevRealmGenerationTest(ZulipTestCase):
    def test_populate_dev_realm(self) -> None:
        data = parse_raw(make_raw_data())
        self.assertEqual(validate_dev_data(data, require_complete=False), [])
        now = timezone_now()
        scripted_count = 8
        # A small batch size checks that batching keeps messages in date order.
        with mock.patch("zcustom.lib.dev_realm.SEND_BATCH_SIZE", 3):
            realm = populate_dev_realm(
                data,
                string_id="zhdev",
                now=now,
                num_messages=scripted_count + 6,
                extra_users=2,
                extra_streams=1,
            )
        realm.refresh_from_db()
        self.assertEqual(realm.name, "取经项目组（测试）")
        self.assertEqual(realm.default_language, "zh-hans")
        self.assertFalse(realm.invite_required)

        def user(key: str) -> UserProfile:
            return UserProfile.objects.get(realm=realm, delivery_email=f"{key}@zulip.com")

        tangseng, sunwukong, zhubajie = user("tangseng"), user("sunwukong"), user("zhubajie")
        guanyin, tudi = user("guanyin"), user("tudi")
        self.assertTrue(tangseng.is_realm_owner)
        self.assertTrue(sunwukong.is_realm_admin)
        self.assertTrue(sunwukong.is_staff)
        self.assertTrue(guanyin.is_guest)
        self.assertTrue(tudi.is_imported_stub)
        self.assertEqual(zhubajie.timezone, "America/Los_Angeles")
        self.assertEqual(zhubajie.default_language, "zh-hans")
        self.assertEqual(zhubajie.date_joined, realm.date_created)
        self.assertEqual(
            UserProfile.objects.get(realm=realm, delivery_email="default-bot@zulip.com").full_name,
            "机器人0",
        )
        self.assertEqual(
            UserProfile.objects.filter(realm=realm, delivery_email__startswith="extrauser").count(),
            2,
        )

        # The real organization creation flow ran.
        creation = RealmAuditLog.objects.get(
            realm=realm, event_type=AuditLogEventType.REALM_CREATED
        )
        self.assertEqual(creation.acting_user, tangseng)
        self.assertTrue(OnboardingUserMessage.objects.filter(realm=realm).exists())
        default_channels = {
            default.stream.name for default in DefaultStream.objects.filter(realm=realm)
        }
        self.assertEqual(default_channels, {"全员", "沙盒", "Zulip", "取经路线"})
        self.assertEqual(realm.new_stream_announcements_stream, get_stream("全员", realm))
        welcome_bot = get_system_bot("welcome-bot@zulip.com", realm.id)
        for human in [tangseng, sunwukong, zhubajie, guanyin]:
            self.assertTrue(
                UserMessage.objects.filter(
                    user_profile=human,
                    message__sender=welcome_bot,
                    message__is_channel_message=False,
                ).exists()
            )
        self.assertFalse(
            UserMessage.objects.filter(user_profile=tudi, message__sender=welcome_bot).exists()
        )

        # Only the creator gets the onboarding a new user sees.
        self.assertEqual(
            list(
                OnboardingStep.objects.filter(user=tangseng).values_list(
                    "onboarding_step", flat=True
                )
            ),
            ["visibility_policy_banner"],
        )
        self.assertGreater(OnboardingStep.objects.filter(user=zhubajie).count(), 5)

        # Channels and subscriptions.
        def subscriber_emails(name: str) -> set[str]:
            return set(
                Subscription.objects.filter(
                    recipient__type_id=get_stream(name, realm).id, recipient__type=2, active=True
                ).values_list("user_profile__delivery_email", flat=True)
            )

        self.assertEqual(
            subscriber_emails("核心小组"), {"sunwukong@zulip.com", "tangseng@zulip.com"}
        )
        self.assertIn("extrauser0@zulip.com", subscriber_emails("全员"))
        self.assertIn("extrauser1@zulip.com", subscriber_emails("取经路线"))
        self.assertNotIn("guanyin@zulip.com", subscriber_emails("取经路线"))
        self.assertIn("tudi@zulip.com", subscriber_emails("天庭公告"))
        self.assertNotIn("tudi@zulip.com", subscriber_emails("全员"))
        self.assertTrue(get_stream("核心小组", realm).invite_only)
        self.assertTrue(get_stream("西行见闻", realm).is_web_public)
        self.assertEqual(get_stream("取经路线", realm).folder.name, "取经事务")  # type: ignore[union-attr] # set by the data
        self.assertEqual(
            get_stream("天庭公告", realm).can_send_message_group_id,
            NamedUserGroup.objects.get(
                realm_for_sharding=realm, name=SystemGroups.ADMINISTRATORS
            ).id,
        )
        self.assertTrue(Stream.objects.filter(realm=realm, name="额外频道 0").exists())

        # Groups, profile fields and personal data.
        team = NamedUserGroup.objects.get(realm_for_sharding=realm, name="取经团队")
        self.assertEqual(
            [subgroup.named_user_group.name for subgroup in team.direct_subgroups.all()], ["徒弟"]
        )
        github = CustomProfileField.objects.get(realm=realm, name="GitHub")
        self.assertEqual(github.field_type, CustomProfileField.EXTERNAL_ACCOUNT)
        self.assertEqual(
            CustomProfileFieldValue.objects.get(user_profile=tangseng, field=github).value, "zulip"
        )
        weapon = CustomProfileField.objects.get(realm=realm, name="常用兵器")
        self.assertEqual(
            CustomProfileFieldValue.objects.get(user_profile=sunwukong, field=weapon).value, "1"
        )
        mentor = CustomProfileField.objects.get(realm=realm, name="导师")
        self.assertEqual(
            CustomProfileFieldValue.objects.get(user_profile=sunwukong, field=mentor).value,
            f"[{tangseng.id}]",
        )
        self.assertEqual(Draft.objects.filter(user_profile=sunwukong).count(), 3)
        self.assertEqual(ScheduledMessage.objects.filter(sender=sunwukong).count(), 2)
        self.assertEqual(AlertWord.objects.filter(user_profile=zhubajie).count(), 4)
        self.assertFalse(AlertWord.objects.filter(user_profile=tudi).exists())

        # Messages: IDs are in date order, as on a real server.
        messages = list(Message.objects.filter(realm=realm).order_by("id"))
        dates = [message.date_sent for message in messages]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(
            Message.objects.filter(realm=realm, sending_client__name="website").count(),
            scripted_count + 6,
        )

        channel = get_stream("取经路线", realm)
        assert channel.recipient_id is not None
        resolved = messages_for_topic(realm.id, channel.recipient_id, "✔ 过火焰山").order_by("id")
        self.assertEqual(resolved.count(), 4)
        notification = resolved.last()
        assert notification is not None
        self.assertEqual(notification.sender.delivery_email, "notification-bot@zulip.com")
        first = resolved.first()
        assert first is not None
        assert first.last_edit_time is not None and first.edit_history is not None
        self.assertLess(first.last_edit_time, now - timedelta(days=1))
        self.assertLess(
            orjson.loads(first.edit_history)[0]["timestamp"], (now - timedelta(days=1)).timestamp()
        )

        reply = resolved[1]
        reactions = Reaction.objects.filter(message=reply)
        self.assertEqual(reactions.count(), 3)
        self.assertEqual(reactions.get(emoji_name="green_tick").reaction_type, Reaction.REALM_EMOJI)
        poll = Message.objects.get(realm=realm, content__startswith="/poll")
        self.assertTrue(SubMessage.objects.filter(message=poll, msg_type="widget").exists())

        # Messages from the last day stay unread; older ones are read.
        self.assertTrue(
            UserMessage.objects.get(user_profile=zhubajie, message=reply).flags.read.is_set
        )
        self.assertFalse(
            UserMessage.objects.get(user_profile=zhubajie, message=poll).flags.read.is_set
        )
        onboarding_ids = OnboardingUserMessage.objects.filter(realm=realm).values_list(
            "message_id", flat=True
        )
        self.assertFalse(
            UserMessage.objects.filter(
                user_profile=tangseng, message_id__in=onboarding_ids, flags=UserMessage.flags.read
            ).exists()
        )

        self_dm = Message.objects.get(realm=realm, content="备忘：挑担")
        self.assertEqual(
            list(
                UserMessage.objects.filter(message=self_dm).values_list("user_profile", flat=True)
            ),
            [user("shaseng").id],
        )

    def test_plan_filler_messages(self) -> None:
        data = parse_raw(make_raw_data())
        now = timezone_now()
        earliest = now - timedelta(days=5)
        resolve = PlannedResolve(
            time=now - timedelta(days=2), channel="取经路线", topic="问路", resolver="tangseng"
        )
        planned = plan_filler_messages(data, random.Random(0), 300, earliest, now, [resolve])
        self.assert_length(planned, 300)
        self.assertTrue(all(earliest <= message.time <= now for message in planned))
        # Only administrators may post in 天庭公告.
        self.assertTrue(
            all(
                message.sender in ("tangseng", "sunwukong")
                for message in planned
                if message.channel == "天庭公告"
            )
        )
        for message in planned:
            if message.channel == "取经路线":
                expected_topic = "✔ 问路" if message.time > resolve.time else "问路"
                self.assertEqual(message.topic, expected_topic)
        texts = [message.text for message in planned]
        self.assertTrue(any(text.startswith("**") for text in texts))
        self.assertTrue(any(text.startswith("> ") for text in texts))
        self.assertIn("多行\n- 一\n- 二", texts)
        self.assertTrue(any(message.reactions for message in planned))
        self.assertEqual(plan_filler_messages(data, random.Random(0), 0, earliest, now, []), [])

    def test_localize_analytics_realm(self) -> None:
        realm = do_create_realm(string_id="analytics", name="Analytics")
        create_users(
            realm, [("Shylock", "shylock@analytics.ds"), ("Bassanio", "bassanio@analytics.ds")]
        )
        ensure_stream(realm, "all", acting_user=None)
        # One user with a visible email address, one with a hidden one.
        UserProfile.objects.filter(delivery_email="shylock@analytics.ds").update(
            email="shylock@analytics.ds"
        )
        UserProfile.objects.filter(delivery_email="bassanio@analytics.ds").update(
            email="user-hidden@example.com"
        )
        analytics = copy.deepcopy(parse_raw(make_raw_data()).org.analytics)

        localize_analytics_realm(analytics)

        realm = get_realm("analytics")
        self.assertEqual(realm.name, "天庭数据司")
        self.assertEqual(realm.default_language, "zh-hans")
        owner = UserProfile.objects.get(realm=realm, delivery_email="taibai@analytics.ds")
        self.assertEqual(owner.full_name, "太白金星")
        self.assertEqual(owner.email, "taibai@analytics.ds")
        guest = UserProfile.objects.get(realm=realm, delivery_email="tudigong@analytics.ds")
        self.assertEqual(guest.full_name, "土地公")
        self.assertEqual(guest.email, "user-hidden@example.com")
        self.assertEqual(get_stream("全天庭", realm).name, "全天庭")
