from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy
from django.views.decorators.csrf import csrf_exempt
from django_stubs_ext import StrPromise

from confirmation.models import Confirmation, ConfirmationKeyError, get_object_from_key
from zerver.actions.user_settings import do_change_user_setting
from zerver.context_processors import common_context
from zerver.lib.send_email import clear_scheduled_emails
from zerver.models import ScheduledEmail, UserProfile


def process_unsubscribe(
    request: HttpRequest,
    confirmation_key: str,
    email_type: str,
    subscription_type: StrPromise,
    unsubscribe_function: Callable[[UserProfile], None],
) -> HttpResponse:
    try:
        user_profile = get_object_from_key(
            confirmation_key, [Confirmation.UNSUBSCRIBE], mark_object_used=False
        )
    except ConfirmationKeyError:
        return render(request, "zerver/unsubscribe_link_error.html")

    assert isinstance(user_profile, UserProfile)
    unsubscribe_function(user_profile)
    context = common_context(user_profile)
    context.update(email_type=email_type, subscription_type=subscription_type)
    return render(request, "zerver/unsubscribe_success.html", context=context)


# Email unsubscribe functions. All have the function signature
# processor(user_profile).


def do_missedmessage_unsubscribe(user_profile: UserProfile) -> None:
    do_change_user_setting(
        user_profile, "enable_offline_email_notifications", False, acting_user=user_profile
    )


def do_welcome_unsubscribe(user_profile: UserProfile) -> None:
    clear_scheduled_emails([user_profile.id], ScheduledEmail.WELCOME)


def do_digest_unsubscribe(user_profile: UserProfile) -> None:
    do_change_user_setting(user_profile, "enable_digest_emails", False, acting_user=user_profile)


def do_login_unsubscribe(user_profile: UserProfile) -> None:
    do_change_user_setting(user_profile, "enable_login_emails", False, acting_user=user_profile)


def do_marketing_unsubscribe(user_profile: UserProfile) -> None:
    do_change_user_setting(user_profile, "enable_marketing_emails", False, acting_user=user_profile)


# The keys are part of the URL for the unsubscribe link and must be valid
# without encoding.
# The values are a tuple of (display name, unsubscribe function), where the
# display name is what we call this class of email in user-visible text.
email_unsubscribers = {
    "missed_messages": (gettext_lazy("missed messages"), do_missedmessage_unsubscribe),
    "welcome": (gettext_lazy("welcome"), do_welcome_unsubscribe),
    "digest": (gettext_lazy("digest"), do_digest_unsubscribe),
    "login": (gettext_lazy("login"), do_login_unsubscribe),
    "marketing": (gettext_lazy("marketing"), do_marketing_unsubscribe),
}


# Login NOT required. These are for one-click unsubscribes.
@csrf_exempt
def email_unsubscribe(request: HttpRequest, email_type: str, confirmation_key: str) -> HttpResponse:
    if email_type in email_unsubscribers:
        display_name, unsubscribe_function = email_unsubscribers[email_type]
        return process_unsubscribe(
            request, confirmation_key, email_type, display_name, unsubscribe_function
        )

    return render(request, "zerver/unsubscribe_link_error.html")
