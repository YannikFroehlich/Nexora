"""Twitch OAuth callback shared by every overlay type that connects the owner's Twitch account."""

import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from app import twitch_api
from app.views.twitch_alert import activate_alerts, get_manageable_twitch_alert
from app.views.twitch_goal import get_manageable_twitch_goal


def _link_goal(request, overlay, connection):
    overlay.connection = connection
    overlay.save(update_fields=("connection", "updated_at"))


def _activate_alerts(request, overlay, connection):
    # Without a public HTTPS callback Twitch cannot deliver; the editor already says so and
    # test alerts still work, so connecting must not end in an activation error.
    if twitch_api.eventsub_callback_url(request).startswith("https://"):
        activate_alerts(request, connection)


# Session key set by the connect view -> (getter, manage URL name, dashboard section, on connect).
OAUTH_TARGETS = {
    "overlay_id": (
        get_manageable_twitch_goal,
        "twitch_goal_manage",
        "twitch-goal-overlays",
        _link_goal,
    ),
    "alert_id": (
        get_manageable_twitch_alert,
        "twitch_alert_manage",
        "twitch-alert-overlays",
        _activate_alerts,
    ),
}


@login_required
def twitch_callback(request):
    oauth_session = request.session.pop("twitch_oauth", None) or {}
    target_key = next((key for key in OAUTH_TARGETS if oauth_session.get(key)), None)
    get_overlay, manage_url, section, on_connected = OAUTH_TARGETS[target_key or "overlay_id"]
    received_state = request.GET.get("state", "")
    if (
        target_key is None
        or not received_state
        or not secrets.compare_digest(received_state, oauth_session.get("state", ""))
    ):
        messages.error(request, _("The Twitch connection could not be verified."))
        return redirect(f"{reverse('overlay_dashboard')}#{section}")
    overlay = get_overlay(request, oauth_session[target_key])
    if request.GET.get("error"):
        messages.error(request, _("Twitch access was not granted."))
        return redirect(manage_url, pk=overlay.pk)
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, _("Twitch returned no authorization code."))
        return redirect(manage_url, pk=overlay.pk)
    try:
        connection = twitch_api.exchange_authorization_code(
            request,
            request.user,
            code,
            oauth_session.get("scopes") or [],
        )
    except twitch_api.TwitchAPIError:
        messages.error(request, _("Twitch could not be connected. Check the app settings."))
    else:
        messages.success(request, _("Twitch connected successfully."))
        on_connected(request, overlay, connection)
    return redirect(manage_url, pk=overlay.pk)
