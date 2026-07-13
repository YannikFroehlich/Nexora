"""Small server-side Spotify Web API client used by public overlays."""

import base64
import json
from datetime import timedelta
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _


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
    return settings.SPOTIFY_REDIRECT_URI or request.build_absolute_uri(
        reverse("spotify_callback")
    )


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


def exchange_authorization_code(request, overlay, code):
    token_data = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(request),
        }
    )
    _store_token_response(overlay, token_data, connected=True)


def disconnect(overlay):
    overlay.spotify_access_token = ""
    overlay.spotify_refresh_token = ""
    overlay.spotify_token_expires_at = None
    overlay.spotify_connected_at = None
    overlay.save(
        update_fields=(
            "spotify_access_token",
            "spotify_refresh_token",
            "spotify_token_expires_at",
            "spotify_connected_at",
        )
    )


def overlay_state_payload(overlay):
    payload = overlay.design_payload()
    payload["connected"] = overlay.is_spotify_connected
    payload["error"] = ""

    if not overlay.is_spotify_connected:
        payload["playback"] = empty_playback()
        return payload

    try:
        payload["playback"] = current_playback(overlay)
    except SpotifyAPIError as error:
        payload["error"] = _("Spotify is currently unavailable. Please reconnect if this continues.")
        payload["needs_reconnect"] = error.status_code in {400, 401, 403}
        payload["playback"] = empty_playback()

    return payload


def current_playback(overlay):
    access_token = _valid_access_token(overlay)

    try:
        response = _api_request(CURRENTLY_PLAYING_URL, access_token)
    except SpotifyAPIError as error:
        if error.status_code != 401 or not overlay.spotify_refresh_token:
            raise

        access_token = _refresh_access_token(overlay)
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
            artist.get("name", "")
            for artist in item.get("artists", [])
            if artist.get("name")
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


def _valid_access_token(overlay):
    expires_at = overlay.spotify_token_expires_at

    if (
        overlay.spotify_access_token
        and expires_at
        and expires_at > timezone.now() + timedelta(seconds=60)
    ):
        return overlay.spotify_access_token

    if overlay.spotify_refresh_token:
        return _refresh_access_token(overlay)

    if overlay.spotify_access_token:
        return overlay.spotify_access_token

    raise SpotifyAPIError(_("Spotify is not connected."), status_code=401)


def _refresh_access_token(overlay):
    token_data = _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": overlay.spotify_refresh_token,
        }
    )
    _store_token_response(overlay, token_data)
    return overlay.spotify_access_token


def _store_token_response(overlay, token_data, connected=False):
    access_token = token_data.get("access_token")

    if not access_token:
        raise SpotifyAPIError(_("Spotify returned no access token."))

    try:
        expires_in = max(int(token_data.get("expires_in", 3600)), 60)
    except (TypeError, ValueError):
        expires_in = 3600

    overlay.spotify_access_token = access_token
    overlay.spotify_token_expires_at = timezone.now() + timedelta(seconds=expires_in)

    if token_data.get("refresh_token"):
        overlay.spotify_refresh_token = token_data["refresh_token"]

    update_fields = [
        "spotify_access_token",
        "spotify_refresh_token",
        "spotify_token_expires_at",
    ]

    if connected:
        overlay.spotify_connected_at = timezone.now()
        update_fields.append("spotify_connected_at")

    overlay.save(update_fields=update_fields)


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
            message = error_payload.get("error_description") or error_payload.get("error", {}).get("message")
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
