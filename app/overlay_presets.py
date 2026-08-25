from app import overlay_transfer
from app.models import (
    ScoreOverlay,
    SpotifyOverlay,
    TimerOverlay,
    TwitchGoalOverlay,
    WinChallenge,
)
from app.overlay_versions import BRANDING_FIELDS, _branding_data

STYLE_FIELDS = (
    "background_color",
    "background_opacity",
    "border_color",
    "border_width",
    "corner_radius",
)

MODEL_BY_TYPE = {
    overlay_transfer.SPOTIFY_TYPE: SpotifyOverlay,
    overlay_transfer.TIMER_TYPE: TimerOverlay,
    overlay_transfer.WINCHALLENGE_TYPE: WinChallenge,
    overlay_transfer.SCORE_TYPE: ScoreOverlay,
    overlay_transfer.TWITCH_GOAL_TYPE: TwitchGoalOverlay,
}


class OverlayPresetError(ValueError):
    pass


def model_for(overlay_type):
    model = MODEL_BY_TYPE.get(overlay_type)
    if model is None:
        raise OverlayPresetError("Unknown overlay type")
    return model


def capture_style(overlay):
    style = {field: getattr(overlay, field) for field in STYLE_FIELDS}
    style["font_family"] = overlay.font_family
    style["assets"] = {field: getattr(overlay, f"{field}_id") for field in BRANDING_FIELDS}
    return style


def _clamped(overlay, field_name, value):
    field = overlay._meta.get_field(field_name)
    for validator in field.validators:
        limit = getattr(validator, "limit_value", None)
        if limit is None:
            continue
        if validator.code == "min_value":
            value = max(limit, value)
        elif validator.code == "max_value":
            value = min(limit, value)
    return value


def apply_style(overlay, preset):
    style = preset.style
    overlay.background_color = style["background_color"]
    overlay.border_color = style["border_color"]
    overlay.background_opacity = _clamped(
        overlay, "background_opacity", style["background_opacity"]
    )
    overlay.border_width = _clamped(overlay, "border_width", style["border_width"])
    overlay.corner_radius = _clamped(overlay, "corner_radius", style["corner_radius"])
    overlay.font_family = style.get("font_family", overlay.FONT_SYSTEM)

    asset_data = _branding_data(overlay.owner, style.get("assets", {}))
    for field_name, asset_id in asset_data.items():
        setattr(overlay, f"{field_name}_id", asset_id or None)

    overlay.full_clean()
    overlay.save(
        update_fields=[
            *STYLE_FIELDS,
            "font_family",
            *BRANDING_FIELDS,
            "updated_at",
        ]
    )
    return overlay
