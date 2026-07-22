import copy
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from app.forms import SpotifyOverlayForm, TimerOverlayForm
from app.models import (
    OverlayBrandingMixin,
    SpotifyConnection,
    SpotifyOverlay,
    TimerOverlay,
    WinChallenge,
    WinChallengeGame,
)

FORMAT_NAME = "nexora-overlay"
FORMAT_VERSION = 1
MAX_IMPORT_BYTES = 256 * 1024

SPOTIFY_TYPE = "spotify"
TIMER_TYPE = "timer"
WINCHALLENGE_TYPE = "winchallenge"

SPOTIFY_FIELDS = (
    "name",
    "canvas_width",
    "canvas_height",
    "background_color",
    "background_opacity",
    "border_color",
    "border_width",
    "corner_radius",
    "elements",
    "font_family",
)

WINCHALLENGE_FIELDS = (
    "title",
    "design_template",
    "background_color",
    "background_opacity",
    "text_color",
    "accent_color",
    "border_color",
    "corner_radius",
    "border_width",
    "padding",
    "overlay_width",
    "overlay_height",
    "text_size",
    "label_text_size",
    "title_text_size",
    "total_text_size",
    "game_text_size",
    "game_score_text_size",
    "pager_text_size",
    "page_interval_seconds",
    "item_spacing",
    "shadow_enabled",
    "show_games_list",
    "font_family",
)

GAME_FIELDS = ("name", "wins", "target_wins")

TIMER_FIELDS = (
    "name",
    "label",
    "mode",
    "duration_seconds",
    "design_template",
    "background_color",
    "background_opacity",
    "text_color",
    "accent_color",
    "border_color",
    "border_width",
    "corner_radius",
    "overlay_width",
    "overlay_height",
    "label_text_size",
    "timer_text_size",
    "show_progress",
    "shadow_enabled",
    "font_family",
)


class OverlayTransferError(ValueError):
    """Safe, user-facing error for invalid import files."""


def _model_fields(instance, field_names):
    return {field_name: copy.deepcopy(getattr(instance, field_name)) for field_name in field_names}


def spotify_export_payload(overlay):
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "type": SPOTIFY_TYPE,
        "overlay": _model_fields(overlay, SPOTIFY_FIELDS),
    }


def winchallenge_export_payload(challenge):
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "type": WINCHALLENGE_TYPE,
        "overlay": _model_fields(challenge, WINCHALLENGE_FIELDS),
        "games": [_model_fields(game, GAME_FIELDS) for game in challenge.ordered_games],
    }


def timer_export_payload(timer):
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "type": TIMER_TYPE,
        "overlay": _model_fields(timer, TIMER_FIELDS),
    }


def export_payload(overlay):
    if isinstance(overlay, SpotifyOverlay):
        return spotify_export_payload(overlay)

    if isinstance(overlay, WinChallenge):
        return winchallenge_export_payload(overlay)

    if isinstance(overlay, TimerOverlay):
        return timer_export_payload(overlay)

    raise TypeError("Unsupported overlay model")


def load_payload(uploaded_file):
    raw_content = uploaded_file.read(MAX_IMPORT_BYTES + 1)

    if len(raw_content) > MAX_IMPORT_BYTES:
        raise OverlayTransferError(_("The import file is too large."))

    try:
        payload = json.loads(raw_content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OverlayTransferError(_("The selected file is not valid JSON.")) from error

    if not isinstance(payload, dict):
        raise OverlayTransferError(_("The import file has an invalid structure."))

    return payload


def _require_exact_keys(data, expected_keys):
    if not isinstance(data, dict) or set(data) != set(expected_keys):
        raise OverlayTransferError(_("The import file has an invalid structure."))


def _overlay_data_with_defaults(data):
    if not isinstance(data, dict):
        raise OverlayTransferError(_("The import file has an invalid structure."))
    normalized = copy.deepcopy(data)
    normalized.setdefault("font_family", OverlayBrandingMixin.FONT_SYSTEM)
    return normalized


def _validate_envelope(payload):
    overlay_type = payload.get("type")
    expected_root_keys = {"format", "version", "type", "overlay"}

    if overlay_type == WINCHALLENGE_TYPE:
        expected_root_keys.add("games")

    _require_exact_keys(payload, expected_root_keys)

    if payload["format"] != FORMAT_NAME:
        raise OverlayTransferError(_("This is not a Nexora overlay export."))

    if payload["version"] != FORMAT_VERSION:
        raise OverlayTransferError(_("This overlay export version is not supported."))

    if overlay_type not in {SPOTIFY_TYPE, TIMER_TYPE, WINCHALLENGE_TYPE}:
        raise OverlayTransferError(_("The overlay type is not supported."))

    return overlay_type


def _import_spotify(payload, owner):
    overlay_data = _overlay_data_with_defaults(payload["overlay"])
    _require_exact_keys(overlay_data, SPOTIFY_FIELDS)
    form_data = copy.deepcopy(overlay_data)
    form_data["elements"] = json.dumps(
        form_data["elements"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    form = SpotifyOverlayForm(data=form_data, asset_owner=owner)

    if not form.is_valid():
        raise OverlayTransferError(_("The Spotify overlay data is invalid."))

    overlay = form.save(commit=False)
    overlay.owner = owner
    overlay.connection, _created = SpotifyConnection.objects.get_or_create(owner=owner)
    overlay.save()
    return overlay


def _validated_game(game_data, challenge, sort_order):
    _require_exact_keys(game_data, GAME_FIELDS)
    game = WinChallengeGame(
        challenge=challenge,
        sort_order=sort_order,
        **game_data,
    )

    try:
        game.full_clean(exclude=("challenge",))
    except ValidationError as error:
        raise OverlayTransferError(_("The Win Challenge game data is invalid.")) from error

    return game


def _import_timer(payload, owner):
    overlay_data = _overlay_data_with_defaults(payload["overlay"])
    _require_exact_keys(overlay_data, TIMER_FIELDS)
    form_data = copy.deepcopy(overlay_data)
    duration_seconds = form_data.pop("duration_seconds")

    if not isinstance(duration_seconds, int):
        raise OverlayTransferError(_("The timer overlay data is invalid."))

    hours, remainder = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    form_data.update(
        {
            "duration_hours": hours,
            "duration_minutes": minutes,
            "duration_seconds_part": seconds,
        }
    )
    form = TimerOverlayForm(data=form_data, asset_owner=owner)

    if not form.is_valid():
        raise OverlayTransferError(_("The timer overlay data is invalid."))

    timer = form.save(commit=False)
    timer.owner = owner
    timer.save()
    return timer


def _import_winchallenge(payload, owner):
    overlay_data = _overlay_data_with_defaults(payload["overlay"])
    games_data = payload["games"]
    _require_exact_keys(overlay_data, WINCHALLENGE_FIELDS)

    if not isinstance(games_data, list) or len(games_data) > WinChallenge.MAX_GAMES:
        raise OverlayTransferError(_("The Win Challenge game list is invalid."))

    challenge = WinChallenge(owner=owner, **overlay_data)

    try:
        challenge.full_clean()
    except ValidationError as error:
        raise OverlayTransferError(_("The Win Challenge overlay data is invalid.")) from error

    challenge.save()
    games = [
        _validated_game(game_data, challenge, sort_order)
        for sort_order, game_data in enumerate(games_data)
    ]
    WinChallengeGame.objects.bulk_create(games)
    return challenge


@transaction.atomic
def import_payload(payload, owner):
    overlay_type = _validate_envelope(payload)

    if overlay_type == SPOTIFY_TYPE:
        return _import_spotify(payload, owner)

    if overlay_type == TIMER_TYPE:
        return _import_timer(payload, owner)

    return _import_winchallenge(payload, owner)


def _copy_label(value, suffix, maximum_length=120):
    value = str(value).strip()
    suffix = f" ({suffix})"
    return f"{value[: maximum_length - len(suffix)]}{suffix}"


def duplicate_overlay(overlay, owner, copy_suffix):
    payload = export_payload(overlay)

    if isinstance(overlay, SpotifyOverlay):
        payload["overlay"]["name"] = _copy_label(
            overlay.display_name,
            copy_suffix,
        )
    elif isinstance(overlay, WinChallenge):
        payload["overlay"]["title"] = _copy_label(
            overlay.display_title,
            copy_suffix,
        )
    else:
        payload["overlay"]["name"] = _copy_label(
            overlay.display_name,
            copy_suffix,
        )

    duplicate = import_payload(payload, owner)
    branding_fields = ("font_asset", "logo_asset", "background_asset")
    for field_name in branding_fields:
        asset = getattr(overlay, field_name, None)
        if asset and asset.owner_id == owner.pk:
            setattr(duplicate, field_name, asset)
    duplicate.save(update_fields=[*branding_fields, "updated_at"])
    return duplicate
