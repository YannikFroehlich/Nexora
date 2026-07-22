"""Small server-side Spotify Web API client used by public overlays."""

import base64
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

from app.models import SpotifyConnection, SpotifyOverlay

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
CURRENTLY_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"
SCOPES = "user-read-currently-playing"


class SpotifyAPIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def is_configured():
    return bool(settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_CLIENT_SECRET)


def redirect_uri(request):
    return settings.SPOTIFY_REDIRECT_URI or request.build_absolute_uri(reverse("spotify_callback"))


def authorization_url(request, state):
    if not is_configured():
        raise SpotifyAPIError(_("Spotify credentials are not configured."))

    query = urlparse.urlencode(
        {
            "response_type": "code",
            "client_id": settings.SPOTIFY_CLIENT_ID,
            "scope": SCOPES,
            "redirect_uri": redirect_uri(request),
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def connection_for_owner(owner):
    connection, _created = SpotifyConnection.objects.get_or_create(owner=owner)
    SpotifyOverlay.objects.filter(owner=owner).exclude(connection=connection).update(
        connection=connection
    )
    return connection


def connection_for_overlay(overlay):
    if overlay.connection_id:
        return overlay.connection

    if not overlay.owner_id:
        connection = SpotifyConnection.objects.create()
        overlay.connection = connection
        overlay.save(update_fields=("connection", "updated_at"))
        return connection

    connection = connection_for_owner(overlay.owner)
    overlay.connection = connection
    return connection


@transaction.atomic
def adopt_connections(owner):
    """Consolidate ownerless legacy connections after first-user adoption."""

    linked_connections = list(
        SpotifyConnection.objects.select_for_update()
        .filter(overlays__owner=owner)
        .distinct()
        .order_by("-connected_at", "-updated_at")
    )
    primary = SpotifyConnection.objects.select_for_update().filter(owner=owner).first()

    if primary is None and linked_connections:
        primary = linked_connections[0]
        primary.owner = owner
        primary.save(update_fields=("owner", "updated_at"))
    elif primary is None:
        primary = SpotifyConnection.objects.create(owner=owner)

    if not primary.is_connected:
        donor = next(
            (
                connection
                for connection in linked_connections
                if connection.pk != primary.pk and connection.is_connected
            ),
            None,
        )
        if donor:
            primary.access_token = donor.access_token
            primary.refresh_token = donor.refresh_token
            primary.token_expires_at = donor.token_expires_at
            primary.connected_at = donor.connected_at
            primary.save(
                update_fields=(
                    "access_token",
                    "refresh_token",
                    "token_expires_at",
                    "connected_at",
                    "updated_at",
                )
            )

    SpotifyOverlay.objects.filter(owner=owner).update(connection=primary)
    redundant_ids = [
        connection.pk
        for connection in linked_connections
        if connection.pk != primary.pk and connection.owner_id is None
    ]
    SpotifyConnection.objects.filter(pk__in=redundant_ids).delete()
    return primary


def exchange_authorization_code(request, overlay, code):
    token_data = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(request),
        }
    )
    connection = connection_for_overlay(overlay)
    _store_token_response(connection, token_data, connected=True)


def disconnect(overlay):
    if not overlay.connection_id:
        return

    connection = overlay.connection
    connection.access_token = ""
    connection.refresh_token = ""
    connection.token_expires_at = None
    connection.connected_at = None
    connection.playback_cache = {}
    connection.playback_cached_at = None
    connection.playback_refresh_started_at = None
    connection.save(
        update_fields=(
            "access_token",
            "refresh_token",
            "token_expires_at",
            "connected_at",
            "playback_cache",
            "playback_cached_at",
            "playback_refresh_started_at",
            "updated_at",
        )
    )


def overlay_state_payload(overlay):
    payload = overlay.design_payload()
    payload["connected"] = overlay.is_spotify_connected
    payload["error"] = ""

    if not overlay.is_spotify_connected:
        payload["playback"] = empty_playback()
        return payload

    playback_state = cached_playback_state(overlay.connection)
    payload["playback"] = playback_state["playback"]

    if playback_state.get("error"):
        payload["error"] = _(
            "Spotify is currently unavailable. Please reconnect if this continues."
        )
        payload["needs_reconnect"] = playback_state.get("needs_reconnect", False)

    return payload


def cached_playback_state(connection):
    now = timezone.now()
    cache_seconds = settings.SPOTIFY_PLAYBACK_CACHE_SECONDS
    stale_before = now - timedelta(seconds=cache_seconds)

    if (
        connection.playback_cache
        and connection.playback_cached_at
        and connection.playback_cached_at > stale_before
    ):
        return connection.playback_cache

    lease_expired_before = now - timedelta(seconds=15)
    claimed = (
        SpotifyConnection.objects.filter(pk=connection.pk)
        .filter(Q(playback_cached_at__isnull=True) | Q(playback_cached_at__lte=stale_before))
        .filter(
            Q(playback_refresh_started_at__isnull=True)
            | Q(playback_refresh_started_at__lt=lease_expired_before)
        )
        .update(playback_refresh_started_at=now)
    )

    if not claimed:
        connection.refresh_from_db(
            fields=(
                "playback_cache",
                "playback_cached_at",
                "playback_refresh_started_at",
            )
        )
        return connection.playback_cache or {
            "playback": empty_playback(),
            "error": False,
            "needs_reconnect": False,
        }

    try:
        state = {
            "playback": current_playback(connection),
            "error": False,
            "needs_reconnect": False,
        }
    except SpotifyAPIError as error:
        state = {
            "playback": empty_playback(),
            "error": True,
            "needs_reconnect": error.status_code in {400, 401, 403},
        }

    connection.playback_cache = state
    connection.playback_cached_at = timezone.now()
    connection.playback_refresh_started_at = None
    connection.save(
        update_fields=(
            "playback_cache",
            "playback_cached_at",
            "playback_refresh_started_at",
            "updated_at",
        )
    )
    return state


def current_playback(connection):
    access_token = _valid_access_token(connection)

    try:
        response = _api_request(CURRENTLY_PLAYING_URL, access_token)
    except SpotifyAPIError as error:
        if error.status_code != 401 or not connection.refresh_token:
            raise

        access_token = _refresh_access_token(connection)
        response = _api_request(CURRENTLY_PLAYING_URL, access_token)

    if response is None or not response.get("item"):
        return empty_playback()

    item = response["item"]
    item_type = item.get("type")

    if item_type == "episode":
        show = item.get("show") or {}
        artists = show.get("name") or item.get("publisher") or _("Podcast")
        album = show.get("name") or ""
        images = item.get("images") or show.get("images") or []
    else:
        artists = ", ".join(
            artist.get("name", "") for artist in item.get("artists", []) if artist.get("name")
        )
        album_data = item.get("album") or {}
        album = album_data.get("name") or ""
        images = album_data.get("images") or []

    duration_ms = max(int(item.get("duration_ms") or 0), 0)
    progress_ms = max(int(response.get("progress_ms") or 0), 0)
    image_url = images[0].get("url", "") if images else ""

    return {
        "title": item.get("name") or _("Unknown title"),
        "artist": artists or _("Unknown artist"),
        "album": album,
        "image_url": image_url,
        "progress_ms": min(progress_ms, duration_ms) if duration_ms else progress_ms,
        "duration_ms": duration_ms,
        "is_playing": bool(response.get("is_playing")),
        "fetched_at": int(timezone.now().timestamp() * 1000),
    }


def empty_playback():
    return {
        "title": _("Nothing playing"),
        "artist": _("Start playback in Spotify"),
        "album": "",
        "image_url": "",
        "progress_ms": 0,
        "duration_ms": 0,
        "is_playing": False,
        "fetched_at": int(timezone.now().timestamp() * 1000),
    }


def _valid_access_token(connection):
    expires_at = connection.token_expires_at

    if (
        connection.access_token
        and expires_at
        and expires_at > timezone.now() + timedelta(seconds=60)
    ):
        return connection.access_token

    if connection.refresh_token:
        return _refresh_access_token(connection)

    if connection.access_token:
        return connection.access_token

    raise SpotifyAPIError(_("Spotify is not connected."), status_code=401)


def _refresh_access_token(connection):
    token_data = _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
        }
    )
    _store_token_response(connection, token_data)
    return connection.access_token


def _store_token_response(connection, token_data, connected=False):
    access_token = token_data.get("access_token")

    if not access_token:
        raise SpotifyAPIError(_("Spotify returned no access token."))

    try:
        expires_in = max(int(token_data.get("expires_in", 3600)), 60)
    except (TypeError, ValueError):
        expires_in = 3600

    connection.access_token = access_token
    connection.token_expires_at = timezone.now() + timedelta(seconds=expires_in)

    if token_data.get("refresh_token"):
        connection.refresh_token = token_data["refresh_token"]

    update_fields = [
        "access_token",
        "refresh_token",
        "token_expires_at",
        "updated_at",
    ]

    if connected:
        connection.connected_at = timezone.now()
        update_fields.append("connected_at")

    connection.playback_cache = {}
    connection.playback_cached_at = None
    connection.playback_refresh_started_at = None
    update_fields.extend(
        (
            "playback_cache",
            "playback_cached_at",
            "playback_refresh_started_at",
        )
    )
    connection.save(update_fields=update_fields)


def _token_request(data):
    if not is_configured():
        raise SpotifyAPIError(_("Spotify credentials are not configured."))

    credentials = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    request = urlrequest.Request(
        TOKEN_URL,
        data=urlparse.urlencode(data).encode("utf-8"),
        headers={
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    return _read_json_response(request)


def _api_request(url, access_token):
    request = urlrequest.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    return _read_json_response(request, allow_empty=True)


def _read_json_response(request, allow_empty=False):
    try:
        with urlrequest.urlopen(request, timeout=10) as response:
            body = response.read()
    except urlerror.HTTPError as error:
        try:
            body = error.read().decode("utf-8")
            error_payload = json.loads(body)
            message = error_payload.get("error_description") or error_payload.get("error", {}).get(
                "message"
            )
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
            message = None

        raise SpotifyAPIError(
            message or _("Spotify request failed."),
            status_code=error.code,
        ) from error
    except (urlerror.URLError, TimeoutError) as error:
        raise SpotifyAPIError(_("Spotify could not be reached.")) from error

    if not body:
        if allow_empty:
            return None
        raise SpotifyAPIError(_("Spotify returned an empty response."))

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpotifyAPIError(_("Spotify returned an invalid response.")) from error
