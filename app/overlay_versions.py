import copy
import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction

from app import overlay_transfer
from app.forms import SpotifyOverlayForm, TimerOverlayForm
from app.models import (
    OverlayAsset,
    OverlayVersion,
    SpotifyOverlay,
    TimerOverlay,
    WinChallenge,
    WinChallengeGame,
)

MAX_VERSIONS_PER_OVERLAY = 30
BRANDING_FIELDS = ("font_asset", "logo_asset", "background_asset")


class OverlayVersionError(ValueError):
    pass


def overlay_type_for(overlay):
    if isinstance(overlay, SpotifyOverlay):
        return overlay_transfer.SPOTIFY_TYPE
    if isinstance(overlay, TimerOverlay):
        return overlay_transfer.TIMER_TYPE
    if isinstance(overlay, WinChallenge):
        return overlay_transfer.WINCHALLENGE_TYPE
    raise TypeError("Unsupported overlay model")


def _snapshot(overlay):
    return {
        "payload": overlay_transfer.export_payload(overlay),
        "assets": {field: getattr(overlay, f"{field}_id") for field in BRANDING_FIELDS},
    }


def _fingerprint(snapshot):
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def versions_for(overlay):
    if not overlay.pk or not overlay.owner_id:
        return OverlayVersion.objects.none()
    return OverlayVersion.objects.filter(
        owner_id=overlay.owner_id,
        overlay_type=overlay_type_for(overlay),
        overlay_id=overlay.pk,
    )


def editor_version_context(overlay):
    versions = versions_for(overlay)
    if overlay.pk and overlay.owner_id and not versions.exists():
        record_version(overlay, OverlayVersion.REASON_CREATED)
        versions = versions_for(overlay)
    return {
        "overlay_versions": list(versions[:MAX_VERSIONS_PER_OVERLAY]),
        "version_overlay_type": overlay_type_for(overlay),
    }


@transaction.atomic
def record_version(overlay, reason=OverlayVersion.REASON_AUTOSAVE):
    if not overlay.pk or not overlay.owner_id:
        return None, False

    overlay_type = overlay_type_for(overlay)
    snapshot = _snapshot(overlay)
    fingerprint = _fingerprint(snapshot)
    versions = OverlayVersion.objects.filter(
        owner_id=overlay.owner_id,
        overlay_type=overlay_type,
        overlay_id=overlay.pk,
    )
    latest = versions.first()

    if latest and latest.fingerprint == fingerprint:
        return latest, False

    version = OverlayVersion.objects.create(
        owner_id=overlay.owner_id,
        overlay_type=overlay_type,
        overlay_id=overlay.pk,
        snapshot=snapshot,
        fingerprint=fingerprint,
        reason=reason,
    )
    stale_ids = list(
        versions.order_by("-created_at", "-pk").values_list("pk", flat=True)[
            MAX_VERSIONS_PER_OVERLAY:
        ]
    )
    if stale_ids:
        OverlayVersion.objects.filter(pk__in=stale_ids).delete()
    return version, True


def delete_versions(overlay):
    versions_for(overlay).delete()


def _asset_id(owner, assets, field_name, kind):
    asset_id = assets.get(field_name)
    if not asset_id:
        return ""
    return (
        OverlayAsset.objects.filter(owner=owner, kind=kind, pk=asset_id)
        .values_list("pk", flat=True)
        .first()
        or ""
    )


def _branding_data(owner, assets):
    return {
        "font_asset": _asset_id(owner, assets, "font_asset", OverlayAsset.KIND_FONT),
        "logo_asset": _asset_id(owner, assets, "logo_asset", OverlayAsset.KIND_IMAGE),
        "background_asset": _asset_id(
            owner,
            assets,
            "background_asset",
            OverlayAsset.KIND_IMAGE,
        ),
    }


def _restore_spotify(overlay, payload, assets):
    form_data = copy.deepcopy(payload["overlay"])
    form_data.setdefault("font_family", overlay.FONT_SYSTEM)
    form_data["elements"] = json.dumps(
        form_data["elements"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    form_data.update(_branding_data(overlay.owner, assets))
    form = SpotifyOverlayForm(
        data=form_data,
        instance=overlay,
        asset_owner=overlay.owner,
    )
    if not form.is_valid():
        raise OverlayVersionError("Invalid Spotify version")
    return form.save()


def _restore_timer(overlay, payload, assets):
    form_data = copy.deepcopy(payload["overlay"])
    form_data.setdefault("font_family", overlay.FONT_SYSTEM)
    duration_seconds = form_data.pop("duration_seconds")
    hours, remainder = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    form_data.update(
        {
            "duration_hours": hours,
            "duration_minutes": minutes,
            "duration_seconds_part": seconds,
            **_branding_data(overlay.owner, assets),
        }
    )
    form = TimerOverlayForm(
        data=form_data,
        instance=overlay,
        asset_owner=overlay.owner,
    )
    if not form.is_valid():
        raise OverlayVersionError("Invalid timer version")
    return form.save()


def _restore_winchallenge(overlay, payload, assets):
    overlay_data = copy.deepcopy(payload["overlay"])
    overlay_data.setdefault("font_family", overlay.FONT_SYSTEM)
    games_data = payload["games"]
    if not isinstance(games_data, list) or len(games_data) > WinChallenge.MAX_GAMES:
        raise OverlayVersionError("Invalid Win Challenge version")

    asset_data = _branding_data(overlay.owner, assets)
    candidate = WinChallenge(
        owner=overlay.owner,
        **overlay_data,
        **{f"{field_name}_id": asset_id or None for field_name, asset_id in asset_data.items()},
    )
    try:
        candidate.full_clean()
    except ValidationError as error:
        raise OverlayVersionError("Invalid Win Challenge version") from error

    for field_name in overlay_transfer.WINCHALLENGE_FIELDS:
        setattr(overlay, field_name, copy.deepcopy(overlay_data[field_name]))
    for field_name, asset_id in asset_data.items():
        setattr(overlay, f"{field_name}_id", asset_id or None)
    overlay.save(
        update_fields=[
            *overlay_transfer.WINCHALLENGE_FIELDS,
            *BRANDING_FIELDS,
            "updated_at",
        ]
    )

    restored_games = []
    for sort_order, game_data in enumerate(games_data):
        game = WinChallengeGame(
            challenge=overlay,
            sort_order=sort_order,
            **game_data,
        )
        try:
            game.full_clean(exclude=("challenge",))
        except ValidationError as error:
            raise OverlayVersionError("Invalid Win Challenge version") from error
        restored_games.append(game)

    overlay.games.all().delete()
    WinChallengeGame.objects.bulk_create(restored_games)
    return overlay


@transaction.atomic
def restore_version(overlay, version):
    overlay_type = overlay_type_for(overlay)
    if (
        version.owner_id != overlay.owner_id
        or version.overlay_type != overlay_type
        or version.overlay_id != overlay.pk
    ):
        raise OverlayVersionError("Version does not belong to this overlay")

    record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    snapshot = version.snapshot
    payload = snapshot.get("payload", {})
    assets = snapshot.get("assets", {})

    if payload.get("type") != overlay_type:
        raise OverlayVersionError("Version type does not match overlay")

    if isinstance(overlay, SpotifyOverlay):
        restored = _restore_spotify(overlay, payload, assets)
    elif isinstance(overlay, TimerOverlay):
        restored = _restore_timer(overlay, payload, assets)
    else:
        restored = _restore_winchallenge(overlay, payload, assets)

    record_version(restored, OverlayVersion.REASON_RESTORE)
    return restored
