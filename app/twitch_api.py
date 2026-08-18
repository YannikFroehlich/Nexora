"""Server-side Twitch OAuth and cached Helix metric client."""

import json
from datetime import timedelta
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from app.models import TwitchConnection, TwitchGoalOverlay

AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
REVOKE_URL = "https://id.twitch.tv/oauth2/revoke"
USERS_URL = "https://api.twitch.tv/helix/users"
FOLLOWERS_URL = "https://api.twitch.tv/helix/channels/followers"
SUBSCRIPTIONS_URL = "https://api.twitch.tv/helix/subscriptions"

FOLLOWER_SCOPE = "moderator:read:followers"
SUBSCRIPTION_SCOPE = "channel:read:subscriptions"


class TwitchAPIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def is_configured():
    return bool(settings.TWITCH_CLIENT_ID and settings.TWITCH_CLIENT_SECRET)


def redirect_uri(request):
    return settings.TWITCH_REDIRECT_URI or request.build_absolute_uri(reverse("twitch_callback"))


def required_scope(overlay):
    return SUBSCRIPTION_SCOPE if overlay.goal_type == overlay.GOAL_SUBSCRIPTIONS else FOLLOWER_SCOPE


def connection_for_owner(owner):
    connection, _created = TwitchConnection.objects.get_or_create(owner=owner)
    TwitchGoalOverlay.objects.filter(owner=owner).exclude(connection=connection).update(
        connection=connection
    )
    return connection


def authorization_url(request, state, scopes):
    if not is_configured():
        raise TwitchAPIError(_("Twitch credentials are not configured."))
    query = urlparse.urlencode(
        {
            "response_type": "code",
            "client_id": settings.TWITCH_CLIENT_ID,
            "redirect_uri": redirect_uri(request),
            "scope": " ".join(sorted(set(scopes))),
            "state": state,
            "force_verify": "true",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_authorization_code(request, owner, code, requested_scopes):
    token_data = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(request),
        }
    )
    connection = connection_for_owner(owner)
    _store_token_response(connection, token_data, connected=True)
    validation = validate_connection(connection, force=True)
    granted = set(validation.get("scopes") or connection.scopes or [])
    if not set(requested_scopes).issubset(granted):
        raise TwitchAPIError(_("Twitch did not grant all required permissions."), 403)
    _load_channel_profile(connection)
    return connection


def disconnect(owner):
    connection = TwitchConnection.objects.filter(owner=owner).first()
    if connection is None:
        return
    token = connection.access_token
    if token and settings.TWITCH_CLIENT_ID:
        request = urlrequest.Request(
            REVOKE_URL,
            data=urlparse.urlencode(
                {"client_id": settings.TWITCH_CLIENT_ID, "token": token}
            ).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            _read_json_response(request, allow_empty=True)
        except TwitchAPIError:
            pass
    connection.access_token = ""
    connection.refresh_token = ""
    connection.token_expires_at = None
    connection.scopes = []
    connection.twitch_user_id = ""
    connection.twitch_login = ""
    connection.display_name = ""
    connection.profile_image_url = ""
    connection.connected_at = None
    connection.validated_at = None
    connection.follower_count = None
    connection.follower_cached_at = None
    connection.subscription_count = None
    connection.subscription_points = None
    connection.subscription_cached_at = None
    connection.refresh_started_at = None
    connection.last_error = ""
    connection.needs_reconnect = False
    connection.save(
        update_fields=(
            "access_token",
            "refresh_token",
            "token_expires_at",
            "scopes",
            "twitch_user_id",
            "twitch_login",
            "display_name",
            "profile_image_url",
            "connected_at",
            "validated_at",
            "follower_count",
            "follower_cached_at",
            "subscription_count",
            "subscription_points",
            "subscription_cached_at",
            "refresh_started_at",
            "last_error",
            "needs_reconnect",
            "updated_at",
        )
    )


def validate_connection(connection, force=False):
    if not connection.access_token:
        raise TwitchAPIError(_("Twitch is not connected."), 401)
    if (
        not force
        and connection.validated_at
        and connection.validated_at > timezone.now() - timedelta(hours=1)
    ):
        return {
            "user_id": connection.twitch_user_id,
            "login": connection.twitch_login,
            "scopes": connection.scopes,
        }
    try:
        data = _validate_request(connection.access_token)
    except TwitchAPIError as error:
        if error.status_code != 401 or not connection.refresh_token:
            _record_connection_error(connection, error)
            raise
        try:
            _refresh_access_token(connection)
            data = _validate_request(connection.access_token)
        except TwitchAPIError as refresh_error:
            _record_connection_error(connection, refresh_error)
            raise

    if data.get("client_id") != settings.TWITCH_CLIENT_ID:
        error = TwitchAPIError(_("The Twitch token belongs to another application."), 401)
        _record_connection_error(connection, error)
        raise error
    connection.twitch_user_id = str(data.get("user_id") or "")
    connection.twitch_login = str(data.get("login") or "")
    connection.scopes = list(data.get("scopes") or [])
    connection.validated_at = timezone.now()
    connection.needs_reconnect = False
    connection.last_error = ""
    connection.save(
        update_fields=(
            "twitch_user_id",
            "twitch_login",
            "scopes",
            "validated_at",
            "needs_reconnect",
            "last_error",
            "updated_at",
        )
    )
    return data


def _record_connection_error(connection, error):
    connection.needs_reconnect = connection.needs_reconnect or error.status_code in {
        400,
        401,
        403,
    }
    connection.last_error = str(error)[:240]
    connection.save(update_fields=("needs_reconnect", "last_error", "updated_at"))


def cached_metric_state(connection, goal_type):
    is_followers = goal_type == TwitchGoalOverlay.GOAL_FOLLOWERS
    cached_field = "follower_cached_at" if is_followers else "subscription_cached_at"
    cached_at = getattr(connection, cached_field)
    now = timezone.now()
    stale_before = now - timedelta(seconds=settings.TWITCH_METRIC_CACHE_SECONDS)
    if cached_at and cached_at > stale_before:
        return _metric_state_from_connection(connection, is_followers)

    lease_expired_before = now - timedelta(seconds=20)
    claimed = (
        TwitchConnection.objects.filter(pk=connection.pk)
        .filter(
            Q(**{f"{cached_field}__isnull": True}) | Q(**{f"{cached_field}__lte": stale_before})
        )
        .filter(Q(refresh_started_at__isnull=True) | Q(refresh_started_at__lt=lease_expired_before))
        .update(refresh_started_at=now)
    )
    if not claimed:
        connection.refresh_from_db()
        return _metric_state_from_connection(connection, is_followers)

    error_message = ""
    needs_reconnect = False
    try:
        validate_connection(connection)
        if is_followers:
            data = _helix_metric_request(
                FOLLOWERS_URL,
                connection,
                {"broadcaster_id": connection.twitch_user_id, "first": 1},
            )
            connection.follower_count = max(int(data.get("total") or 0), 0)
            connection.follower_cached_at = timezone.now()
            update_fields = ["follower_count", "follower_cached_at"]
        else:
            data = _helix_metric_request(
                SUBSCRIPTIONS_URL,
                connection,
                {"broadcaster_id": connection.twitch_user_id, "first": 1},
            )
            connection.subscription_count = max(int(data.get("total") or 0), 0)
            connection.subscription_points = max(int(data.get("points") or 0), 0)
            connection.subscription_cached_at = timezone.now()
            update_fields = [
                "subscription_count",
                "subscription_points",
                "subscription_cached_at",
            ]
    except (TwitchAPIError, TypeError, ValueError) as error:
        error_message = str(error)[:240]
        needs_reconnect = isinstance(error, TwitchAPIError) and error.status_code in {400, 401, 403}
        setattr(connection, cached_field, timezone.now())
        update_fields = [cached_field]

    connection.refresh_started_at = None
    connection.last_error = error_message
    connection.needs_reconnect = needs_reconnect
    connection.save(
        update_fields=[
            *update_fields,
            "refresh_started_at",
            "last_error",
            "needs_reconnect",
            "updated_at",
        ]
    )
    return _metric_state_from_connection(connection, is_followers)


def _metric_state_from_connection(connection, is_followers):
    cached_at = connection.follower_cached_at if is_followers else connection.subscription_cached_at
    return {
        "follower_count": connection.follower_count,
        "subscription_count": connection.subscription_count,
        "subscription_points": connection.subscription_points,
        "cached_at": cached_at,
        "error": connection.last_error,
        "needs_reconnect": connection.needs_reconnect,
        "is_stale": bool(
            cached_at
            and cached_at
            < timezone.now() - timedelta(seconds=settings.TWITCH_METRIC_CACHE_SECONDS * 2)
        ),
    }


def _selected_metric_value(overlay, state):
    if overlay.goal_type == overlay.GOAL_FOLLOWERS:
        return state["follower_count"]
    if overlay.subscription_metric == overlay.METRIC_POINTS:
        return state["subscription_points"]
    return state["subscription_count"]


@transaction.atomic
def reconcile_goal(overlay, raw_value):
    locked = TwitchGoalOverlay.objects.select_for_update().get(pk=overlay.pk)
    if raw_value is None:
        return locked
    update_fields = []
    if locked.progress_mode == locked.MODE_CAMPAIGN and locked.campaign_baseline is None:
        locked.campaign_baseline = int(raw_value)
        update_fields.append("campaign_baseline")

    progress = locked.progress_values(raw_value)["current_value"] or 0
    if locked.last_observed_progress is None:
        locked.last_observed_progress = progress
        update_fields.append("last_observed_progress")
        if progress >= locked.target_value:
            locked.celebrated_revision = locked.goal_revision
            locked.completed_at = timezone.now()
            update_fields.extend(("celebrated_revision", "completed_at"))
    else:
        crossed = locked.last_observed_progress < locked.target_value <= progress
        if crossed and locked.celebrated_revision < locked.goal_revision:
            locked.celebrated_revision = locked.goal_revision
            locked.celebration_sequence += 1
            locked.completed_at = timezone.now()
            update_fields.extend(("celebrated_revision", "celebration_sequence", "completed_at"))
        if locked.last_observed_progress != progress:
            locked.last_observed_progress = progress
            update_fields.append("last_observed_progress")
    if update_fields:
        locked.save(update_fields=[*dict.fromkeys(update_fields), "updated_at"])
    return locked


def overlay_state_payload(overlay):
    if not overlay.connection_id or not overlay.connection.is_connected:
        state = {
            "follower_count": None,
            "subscription_count": None,
            "subscription_points": None,
            "cached_at": None,
            "error": "",
            "needs_reconnect": False,
            "is_stale": False,
        }
    else:
        state = cached_metric_state(overlay.connection, overlay.goal_type)
    raw_value = _selected_metric_value(overlay, state)
    if overlay.pk:
        overlay = reconcile_goal(overlay, raw_value)
    design = overlay.design_payload()
    values = overlay.progress_values(raw_value)
    return {
        **design,
        "title": overlay.display_title,
        "goal": {
            **values,
            "target_value": overlay.target_value,
            "status": (
                "disconnected"
                if not overlay.connection_id or not overlay.connection.is_connected
                else "reconnect"
                if state["needs_reconnect"]
                else "stale"
                if state["is_stale"] or state["error"]
                else "reached"
                if values["is_reached"]
                else "active"
            ),
            "cached_at": state["cached_at"].isoformat() if state["cached_at"] else "",
        },
        "channel": {
            "display_name": overlay.connection.display_name if overlay.connection_id else "",
            "login": overlay.connection.twitch_login if overlay.connection_id else "",
            "avatar_url": overlay.connection.profile_image_url if overlay.connection_id else "",
        },
        "celebration_sequence": overlay.celebration_sequence,
        "connected": bool(overlay.connection_id and overlay.connection.is_connected),
        "needs_reconnect": state["needs_reconnect"],
    }


def _load_channel_profile(connection):
    data = _helix_metric_request(USERS_URL, connection, {})
    user = (data.get("data") or [{}])[0]
    connection.display_name = str(user.get("display_name") or connection.twitch_login)
    connection.profile_image_url = str(user.get("profile_image_url") or "")
    connection.save(update_fields=("display_name", "profile_image_url", "updated_at"))


def _helix_metric_request(url, connection, params):
    validate_connection(connection)
    try:
        return _api_request(url, connection.access_token, params)
    except TwitchAPIError as error:
        if error.status_code != 401 or not connection.refresh_token:
            raise
        _refresh_access_token(connection)
        return _api_request(url, connection.access_token, params)


def _refresh_access_token(connection):
    data = _token_request(
        {"grant_type": "refresh_token", "refresh_token": connection.refresh_token}
    )
    _store_token_response(connection, data)
    return connection.access_token


def _store_token_response(connection, token_data, connected=False):
    access_token = token_data.get("access_token")
    if not access_token:
        raise TwitchAPIError(_("Twitch returned no access token."))
    try:
        expires_in = max(int(token_data.get("expires_in") or 3600), 60)
    except (TypeError, ValueError):
        expires_in = 3600
    connection.access_token = access_token
    if token_data.get("refresh_token"):
        connection.refresh_token = token_data["refresh_token"]
    connection.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    connection.scopes = list(token_data.get("scope") or connection.scopes or [])
    connection.validated_at = None
    connection.needs_reconnect = False
    connection.last_error = ""
    update_fields = [
        "access_token",
        "refresh_token",
        "token_expires_at",
        "scopes",
        "validated_at",
        "needs_reconnect",
        "last_error",
        "updated_at",
    ]
    if connected:
        connection.connected_at = timezone.now()
        update_fields.append("connected_at")
    connection.save(update_fields=update_fields)


def _token_request(data):
    if not is_configured():
        raise TwitchAPIError(_("Twitch credentials are not configured."))
    payload = {
        **data,
        "client_id": settings.TWITCH_CLIENT_ID,
        "client_secret": settings.TWITCH_CLIENT_SECRET,
    }
    request = urlrequest.Request(
        TOKEN_URL,
        data=urlparse.urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _read_json_response(request)


def _validate_request(access_token):
    request = urlrequest.Request(
        VALIDATE_URL,
        headers={"Authorization": f"OAuth {access_token}"},
        method="GET",
    )
    return _read_json_response(request)


def _api_request(url, access_token, params):
    query = urlparse.urlencode(params)
    request = urlrequest.Request(
        f"{url}?{query}" if query else url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Client-Id": settings.TWITCH_CLIENT_ID,
        },
        method="GET",
    )
    return _read_json_response(request)


def _read_json_response(request, allow_empty=False):
    try:
        with urlrequest.urlopen(request, timeout=10) as response:
            body = response.read()
    except urlerror.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            message = payload.get("message") or payload.get("error_description")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            message = None
        raise TwitchAPIError(message or _("Twitch request failed."), error.code) from error
    except (urlerror.URLError, TimeoutError) as error:
        raise TwitchAPIError(_("Twitch could not be reached.")) from error
    if not body:
        if allow_empty:
            return {}
        raise TwitchAPIError(_("Twitch returned an empty response."))
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TwitchAPIError(_("Twitch returned an invalid response.")) from error
