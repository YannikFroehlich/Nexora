import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from app.encrypted_fields import EncryptedTextField
from app.upload_validators import validate_overlay_asset

hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message=_("Enter a valid hex color, for example #14b8a6."),
)


def overlay_asset_upload_to(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"overlay-assets/{instance.owner_id}/{uuid.uuid4().hex}{extension}"


class OverlayAsset(models.Model):
    KIND_IMAGE = "image"
    KIND_FONT = "font"
    KIND_CHOICES = (
        (KIND_IMAGE, _("Image")),
        (KIND_FONT, _("Font")),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="overlay_assets",
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    file = models.FileField(upload_to=overlay_asset_upload_to, max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("kind", "name", "created_at")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.file:
            validate_overlay_asset(self.file, self.kind)

    @property
    def public_url(self):
        return reverse("overlay_asset_file", args=[self.public_token])


class OverlayBrandingMixin(models.Model):
    FONT_SYSTEM = "system"
    FONT_ARIAL = "arial"
    FONT_VERDANA = "verdana"
    FONT_TREBUCHET = "trebuchet"
    FONT_GEORGIA = "georgia"
    FONT_TIMES = "times"
    FONT_COURIER = "courier"
    FONT_FAMILY_CHOICES = (
        (FONT_SYSTEM, _("System default")),
        (FONT_ARIAL, "Arial"),
        (FONT_VERDANA, "Verdana"),
        (FONT_TREBUCHET, "Trebuchet MS"),
        (FONT_GEORGIA, "Georgia"),
        (FONT_TIMES, "Times New Roman"),
        (FONT_COURIER, "Courier New"),
    )
    FONT_CSS_STACKS = {
        FONT_SYSTEM: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        FONT_ARIAL: "Arial, sans-serif",
        FONT_VERDANA: "Verdana, sans-serif",
        FONT_TREBUCHET: "'Trebuchet MS', sans-serif",
        FONT_GEORGIA: "Georgia, serif",
        FONT_TIMES: "'Times New Roman', serif",
        FONT_COURIER: "'Courier New', monospace",
    }

    font_family = models.CharField(
        max_length=20,
        choices=FONT_FAMILY_CHOICES,
        default=FONT_SYSTEM,
    )
    font_asset = models.ForeignKey(
        OverlayAsset,
        on_delete=models.SET_NULL,
        related_name="+",
        blank=True,
        null=True,
        limit_choices_to={"kind": OverlayAsset.KIND_FONT},
    )
    logo_asset = models.ForeignKey(
        OverlayAsset,
        on_delete=models.SET_NULL,
        related_name="+",
        blank=True,
        null=True,
        limit_choices_to={"kind": OverlayAsset.KIND_IMAGE},
    )
    background_asset = models.ForeignKey(
        OverlayAsset,
        on_delete=models.SET_NULL,
        related_name="+",
        blank=True,
        null=True,
        limit_choices_to={"kind": OverlayAsset.KIND_IMAGE},
    )

    class Meta:
        abstract = True

    @property
    def font_css_stack(self):
        return self.FONT_CSS_STACKS.get(
            self.font_family,
            self.FONT_CSS_STACKS[self.FONT_SYSTEM],
        )

    def branding_payload(self):
        return {
            "font_family": self.font_family,
            "font_url": self.font_asset.public_url if self.font_asset_id else "",
            "logo_url": self.logo_asset.public_url if self.logo_asset_id else "",
            "background_image_url": (
                self.background_asset.public_url if self.background_asset_id else ""
            ),
        }


class OverlayVersion(models.Model):
    REASON_CREATED = "created"
    REASON_MANUAL = "manual"
    REASON_AUTOSAVE = "autosave"
    REASON_RESTORE = "restore"
    REASON_CHOICES = (
        (REASON_CREATED, _("Created")),
        (REASON_MANUAL, _("Saved manually")),
        (REASON_AUTOSAVE, _("Autosaved")),
        (REASON_RESTORE, _("Restored")),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="overlay_versions",
    )
    overlay_type = models.CharField(max_length=20)
    overlay_id = models.PositiveBigIntegerField()
    snapshot = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    reason = models.CharField(max_length=16, choices=REASON_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(
                fields=("owner", "overlay_type", "overlay_id", "-created_at"),
                name="overlay_version_lookup",
            )
        ]

    def __str__(self):
        return f"{self.overlay_type}:{self.overlay_id} @ {self.created_at}"


class OverlayPreset(models.Model):
    """Reusable branding/style snapshot that can be applied to any overlay type."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="overlay_presets",
    )
    name = models.CharField(max_length=80)
    style = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class WinChallenge(OverlayBrandingMixin, models.Model):
    """Editable win counter overlay configuration."""

    DEFAULT_OVERLAY_TITLE = _("Winchallenge")
    MAX_GAMES = 20

    TEMPLATE_MINIMAL = "minimal"
    TEMPLATE_GLASS = "glass"
    TEMPLATE_NEON = "neon"

    DESIGN_TEMPLATE_CHOICES = (
        (TEMPLATE_MINIMAL, _("Minimal")),
        (TEMPLATE_GLASS, _("Glass")),
        (TEMPLATE_NEON, _("Neon")),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="win_challenges",
        blank=True,
        null=True,
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    title = models.CharField(max_length=120, blank=True)

    design_template = models.CharField(
        max_length=20,
        choices=DESIGN_TEMPLATE_CHOICES,
        default=TEMPLATE_GLASS,
    )
    background_color = models.CharField(
        max_length=7,
        default="#111827",
        validators=[hex_color_validator],
    )
    background_opacity = models.PositiveSmallIntegerField(
        default=82,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    text_color = models.CharField(
        max_length=7,
        default="#f8fafc",
        validators=[hex_color_validator],
    )
    accent_color = models.CharField(
        max_length=7,
        default="#14b8a6",
        validators=[hex_color_validator],
    )
    border_color = models.CharField(
        max_length=7,
        default="#2dd4bf",
        validators=[hex_color_validator],
    )
    corner_radius = models.PositiveSmallIntegerField(
        default=22,
        validators=[MinValueValidator(0), MaxValueValidator(64)],
    )
    border_width = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(12)],
    )
    padding = models.PositiveSmallIntegerField(
        default=24,
        validators=[MinValueValidator(8), MaxValueValidator(64)],
    )
    overlay_width = models.PositiveSmallIntegerField(
        default=460,
        validators=[MinValueValidator(260), MaxValueValidator(1200)],
    )
    overlay_height = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1000)],
    )
    text_size = models.PositiveSmallIntegerField(
        default=16,
        validators=[MinValueValidator(10), MaxValueValidator(36)],
    )
    label_text_size = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(6), MaxValueValidator(32)],
    )
    title_text_size = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(10), MaxValueValidator(64)],
    )
    total_text_size = models.PositiveSmallIntegerField(
        default=14,
        validators=[MinValueValidator(8), MaxValueValidator(40)],
    )
    game_text_size = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(8), MaxValueValidator(48)],
    )
    game_score_text_size = models.PositiveSmallIntegerField(
        default=12,
        validators=[MinValueValidator(8), MaxValueValidator(36)],
    )
    pager_text_size = models.PositiveSmallIntegerField(
        default=12,
        validators=[MinValueValidator(8), MaxValueValidator(32)],
    )
    page_interval_seconds = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    item_spacing = models.PositiveSmallIntegerField(
        default=9,
        validators=[MinValueValidator(4), MaxValueValidator(28)],
    )
    shadow_enabled = models.BooleanField(default=True)
    show_games_list = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        return str(self.display_title)

    @property
    def display_title(self):
        return self.title or self.DEFAULT_OVERLAY_TITLE

    @property
    def ordered_games(self):
        if self.pk is None:
            return []

        cached_games = getattr(self, "_prefetched_objects_cache", {}).get("games")

        if cached_games is not None:
            return sorted(
                cached_games, key=lambda game: (game.sort_order, game.created_at, game.pk)
            )

        return self.games.order_by("sort_order", "created_at", "pk")

    @property
    def total_wins(self):
        if self.pk is None:
            return 0

        cached_games = getattr(self, "_prefetched_objects_cache", {}).get("games")

        if cached_games is not None:
            return sum(game.wins for game in cached_games)

        return self.games.aggregate(total=Sum("wins"))["total"] or 0

    @property
    def games_count(self):
        if self.pk is None:
            return 0

        cached_games = getattr(self, "_prefetched_objects_cache", {}).get("games")

        if cached_games is not None:
            return len(cached_games)

        return self.games.count()

    @property
    def game_pages(self):
        games = list(self.ordered_games)

        return [games[index : index + 3] for index in range(0, len(games), 3)]

    @property
    def game_page_count(self):
        return len(self.game_pages)

    @property
    def background_rgba(self):
        red = int(self.background_color[1:3], 16)
        green = int(self.background_color[3:5], 16)
        blue = int(self.background_color[5:7], 16)
        alpha = self.background_opacity / 100

        return f"rgba({red}, {green}, {blue}, {alpha:.2f})"

    @property
    def shadow_css(self):
        if not self.shadow_enabled:
            return "none"

        return "0 18px 48px rgba(0, 0, 0, 0.35)"

    def state_payload(self):
        return {
            "title": self.display_title,
            "total_wins": self.total_wins,
            "updated_at": self.updated_at.isoformat(),
            "games_per_page": 3,
            "games": [
                {
                    "id": game.pk,
                    "name": game.name,
                    "wins": game.wins,
                    "target_wins": game.target_wins,
                    "progress_percent": game.progress_percent,
                    "is_complete": game.is_complete,
                }
                for game in self.ordered_games
            ],
            "design": {
                "template": self.design_template,
                "background_color": self.background_color,
                "background_opacity": self.background_opacity,
                "background_rgba": self.background_rgba,
                "text_color": self.text_color,
                "accent_color": self.accent_color,
                "border_color": self.border_color,
                "border_width": self.border_width,
                "corner_radius": self.corner_radius,
                "padding": self.padding,
                "overlay_width": self.overlay_width,
                "overlay_height": self.overlay_height,
                "text_size": self.text_size,
                "label_text_size": self.label_text_size,
                "title_text_size": self.title_text_size,
                "total_text_size": self.total_text_size,
                "game_text_size": self.game_text_size,
                "game_score_text_size": self.game_score_text_size,
                "pager_text_size": self.pager_text_size,
                "page_interval_seconds": self.page_interval_seconds,
                "item_spacing": self.item_spacing,
                "shadow_enabled": self.shadow_enabled,
                "shadow_css": self.shadow_css,
                "show_games_list": self.show_games_list,
                **self.branding_payload(),
            },
        }


class WinChallengeGame(models.Model):
    """Single game row with its own atomic win counter."""

    MAX_WINS = 99999

    challenge = models.ForeignKey(
        WinChallenge,
        on_delete=models.CASCADE,
        related_name="games",
    )
    name = models.CharField(max_length=120)
    wins = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(MAX_WINS)],
    )
    target_wins = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_WINS)],
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sort_order", "created_at", "pk")

    def __str__(self):
        return f"{self.name} ({self.wins})"

    @property
    def remaining_wins(self):
        return max(self.target_wins - self.wins, 0)

    @property
    def is_complete(self):
        return self.target_wins > 0 and self.wins >= self.target_wins

    @property
    def progress_percent(self):
        if self.target_wins <= 0:
            return 0

        return min(round((self.wins / self.target_wins) * 100), 100)


def default_spotify_elements():
    """Starter layout used by new Spotify overlays."""

    return [
        {
            "id": "artwork",
            "type": "artwork",
            "x": 24,
            "y": 24,
            "width": 172,
            "height": 172,
            "font_size": 16,
            "color": "#1db954",
            "background_color": "#282828",
            "border_radius": 18,
        },
        {
            "id": "title",
            "type": "title",
            "x": 220,
            "y": 38,
            "width": 460,
            "height": 52,
            "font_size": 30,
            "color": "#ffffff",
            "background_color": "#535353",
            "border_radius": 8,
        },
        {
            "id": "artist",
            "type": "artist",
            "x": 220,
            "y": 93,
            "width": 460,
            "height": 34,
            "font_size": 18,
            "color": "#b3b3b3",
            "background_color": "#535353",
            "border_radius": 8,
        },
        {
            "id": "progress",
            "type": "progress",
            "x": 220,
            "y": 154,
            "width": 460,
            "height": 12,
            "font_size": 14,
            "color": "#1ed760",
            "background_color": "#535353",
            "border_radius": 8,
        },
        {
            "id": "elapsed",
            "type": "elapsed",
            "x": 220,
            "y": 176,
            "width": 70,
            "height": 24,
            "font_size": 13,
            "color": "#b3b3b3",
            "background_color": "#535353",
            "border_radius": 6,
        },
        {
            "id": "duration",
            "type": "duration",
            "x": 610,
            "y": 176,
            "width": 70,
            "height": 24,
            "font_size": 13,
            "color": "#b3b3b3",
            "background_color": "#535353",
            "border_radius": 6,
        },
    ]


GOAL_LAYOUT_HORIZONTAL = "horizontal"
GOAL_LAYOUT_COMPACT = "compact"
GOAL_LAYOUT_CARD = "card"
GOAL_LAYOUT_RADIAL = "radial"
GOAL_LAYOUT_CUSTOM = "custom"

GOAL_LAYOUT_CHOICES = (
    (GOAL_LAYOUT_HORIZONTAL, _("Horizontal bar")),
    (GOAL_LAYOUT_COMPACT, _("Compact bar")),
    (GOAL_LAYOUT_CARD, _("Vertical card")),
    (GOAL_LAYOUT_RADIAL, _("Radial goal")),
    (GOAL_LAYOUT_CUSTOM, _("Custom")),
)

GOAL_LAYOUT_DIMENSIONS = {
    GOAL_LAYOUT_HORIZONTAL: (900, 160),
    GOAL_LAYOUT_COMPACT: (720, 110),
    GOAL_LAYOUT_CARD: (480, 320),
    GOAL_LAYOUT_RADIAL: (420, 420),
    GOAL_LAYOUT_CUSTOM: (900, 160),
}


def _goal_element(element_id, element_type, **values):
    return {
        "id": element_id,
        "type": element_type,
        "font_size": 20,
        "font_weight": 700,
        "color": "#ffffff",
        "background_color": "#27213f",
        "border_radius": 12,
        "text_align": "left",
        "z_index": 1,
        "visible": True,
        "stroke_width": 9,
        **values,
    }


def goal_elements_for_layout(layout_mode=GOAL_LAYOUT_HORIZONTAL):
    """Return a fresh, freely editable starter layout for Twitch goals."""

    if layout_mode == GOAL_LAYOUT_COMPACT:
        return [
            _goal_element(
                "icon",
                "icon",
                x=18,
                y=18,
                width=74,
                height=74,
                font_size=34,
                background_color="#9146ff",
                border_radius=22,
                text_align="center",
            ),
            _goal_element(
                "title",
                "title",
                x=112,
                y=16,
                width=340,
                height=32,
                font_size=20,
            ),
            _goal_element(
                "progress",
                "progress_bar",
                x=112,
                y=58,
                width=430,
                height=22,
                color="#bf94ff",
                background_color="#2c2440",
                border_radius=999,
            ),
            _goal_element(
                "progress-text",
                "progress_text",
                x=558,
                y=43,
                width=144,
                height=44,
                font_size=22,
                text_align="right",
            ),
        ]

    if layout_mode == GOAL_LAYOUT_CARD:
        return [
            _goal_element(
                "avatar",
                "channel_avatar",
                x=30,
                y=28,
                width=78,
                height=78,
                background_color="#9146ff",
                border_radius=24,
                text_align="center",
            ),
            _goal_element(
                "channel",
                "channel_name",
                x=128,
                y=34,
                width=310,
                height=32,
                font_size=18,
                color="#c4b5fd",
            ),
            _goal_element(
                "title",
                "title",
                x=128,
                y=67,
                width=310,
                height=42,
                font_size=28,
            ),
            _goal_element(
                "progress",
                "progress_bar",
                x=30,
                y=144,
                width=420,
                height=34,
                color="#9146ff",
                background_color="#2c2440",
                border_radius=999,
            ),
            _goal_element(
                "progress-text",
                "progress_text",
                x=30,
                y=198,
                width=260,
                height=56,
                font_size=38,
            ),
            _goal_element(
                "percentage",
                "percentage",
                x=312,
                y=201,
                width=138,
                height=48,
                font_size=30,
                color="#bf94ff",
                text_align="right",
            ),
            _goal_element(
                "remaining",
                "remaining",
                x=30,
                y=270,
                width=420,
                height=24,
                font_size=14,
                color="#ddd6fe",
            ),
        ]

    if layout_mode == GOAL_LAYOUT_RADIAL:
        return [
            _goal_element(
                "ring",
                "progress_ring",
                x=40,
                y=40,
                width=340,
                height=340,
                color="#9146ff",
                background_color="#2c2440",
                border_radius=999,
            ),
            _goal_element(
                "percentage",
                "percentage",
                x=110,
                y=151,
                width=200,
                height=64,
                font_size=48,
                text_align="center",
                z_index=2,
            ),
            _goal_element(
                "progress-text",
                "progress_text",
                x=90,
                y=218,
                width=240,
                height=38,
                font_size=22,
                color="#ddd6fe",
                text_align="center",
                z_index=2,
            ),
            _goal_element(
                "title",
                "title",
                x=60,
                y=326,
                width=300,
                height=36,
                font_size=20,
                text_align="center",
                z_index=2,
            ),
        ]

    return [
        _goal_element(
            "avatar",
            "channel_avatar",
            x=24,
            y=24,
            width=112,
            height=112,
            background_color="#9146ff",
            border_radius=28,
            text_align="center",
        ),
        _goal_element(
            "title",
            "title",
            x=162,
            y=22,
            width=430,
            height=42,
            font_size=28,
        ),
        _goal_element(
            "channel",
            "channel_name",
            x=608,
            y=30,
            width=266,
            height=28,
            font_size=16,
            color="#c4b5fd",
            text_align="right",
        ),
        _goal_element(
            "progress",
            "progress_bar",
            x=162,
            y=78,
            width=540,
            height=34,
            color="#9146ff",
            background_color="#2c2440",
            border_radius=999,
        ),
        _goal_element(
            "progress-text",
            "progress_text",
            x=720,
            y=69,
            width=154,
            height=52,
            font_size=28,
            text_align="right",
        ),
        _goal_element(
            "remaining",
            "remaining",
            x=162,
            y=124,
            width=540,
            height=22,
            font_size=13,
            color="#ddd6fe",
        ),
    ]


def default_goal_elements():
    return goal_elements_for_layout(GOAL_LAYOUT_HORIZONTAL)


SCORE_LAYOUT_BROADCAST_DUEL = "broadcast_duel"
SCORE_LAYOUT_BROADCAST_LIST = "broadcast_list"
SCORE_LAYOUT_CUSTOM = "custom"
SCORE_STRUCTURED_LAYOUTS = {SCORE_LAYOUT_BROADCAST_DUEL, SCORE_LAYOUT_BROADCAST_LIST}
SCORE_LAYOUT_CHOICES = (
    (SCORE_LAYOUT_BROADCAST_DUEL, _("Broadcast duel")),
    (SCORE_LAYOUT_BROADCAST_LIST, _("Broadcast list")),
    (SCORE_LAYOUT_CUSTOM, _("Custom")),
)
SCORE_DEFAULT_ACCENTS = (
    "#38bdf8",
    "#fb7185",
    "#22c55e",
    "#f59e0b",
    "#8b5cf6",
    "#06b6d4",
    "#f97316",
    "#a3e635",
)
SCORE_DUEL_CANVAS = (960, 200)
SCORE_LIST_CANVAS_WIDTH = 960
SCORE_LIST_ROW_HEIGHT = 72
SCORE_LIST_VERTICAL_PADDING = 16


def score_layout_mode_for_participant_count(participant_count):
    return (
        SCORE_LAYOUT_BROADCAST_DUEL
        if int(participant_count or 0) <= 2
        else SCORE_LAYOUT_BROADCAST_LIST
    )


def score_layout_dimensions(layout_mode, participant_count=2):
    if layout_mode == SCORE_LAYOUT_BROADCAST_LIST:
        row_count = max(int(participant_count or 0), 2)
        return (
            SCORE_LIST_CANVAS_WIDTH,
            (SCORE_LIST_VERTICAL_PADDING * 2) + (row_count * SCORE_LIST_ROW_HEIGHT),
        )
    return SCORE_DUEL_CANVAS


def default_score_participants():
    return [
        {
            "id": f"slot-{index}",
            "name": f"Player {index}",
            "score": 0,
            "accent_color": SCORE_DEFAULT_ACCENTS[index - 1],
            "initials": f"P{index}",
            "image_url": "",
        }
        for index in range(1, 3)
    ]


def _score_participant_id(participant, index):
    if isinstance(participant, dict):
        return str(participant.get("id") or participant.get("public_id") or f"slot-{index + 1}")
    return str(getattr(participant, "public_id", f"slot-{index + 1}"))


def _score_participant_accent(participant, index):
    if isinstance(participant, dict):
        accent = participant.get("accent_color")
    else:
        accent = getattr(participant, "accent_color", "")
    return accent or SCORE_DEFAULT_ACCENTS[index % len(SCORE_DEFAULT_ACCENTS)]


def _score_participant_layout_data(participants=None):
    source = [] if participants is None else list(participants)
    if not source:
        source = default_score_participants()

    return [
        {
            "id": _score_participant_id(participant, index),
            "accent_color": _score_participant_accent(participant, index),
        }
        for index, participant in enumerate(source[:8])
    ]


def _score_element(element_id, element_type, participant, **values):
    return {
        "id": element_id,
        "type": element_type,
        "participant_id": participant["id"],
        **values,
    }


def broadcast_duel_score_elements(participants=None):
    participant_data = _score_participant_layout_data(participants)
    if len(participant_data) < 2:
        participant_data.extend(_score_participant_layout_data()[len(participant_data) : 2])

    elements = []
    slots = (
        {
            "prefix": "participant-1",
            "image_x": 32,
            "name_x": 152,
            "score_x": 366,
            "align": "left",
        },
        {
            "prefix": "participant-2",
            "image_x": 820,
            "name_x": 608,
            "score_x": 490,
            "align": "right",
        },
    )
    for participant, slot in zip(participant_data[:2], slots, strict=False):
        elements.extend(
            [
                _score_element(
                    f"{slot['prefix']}-image",
                    "participant_image",
                    participant,
                    x=slot["image_x"],
                    y=40,
                    width=108,
                    height=108,
                    font_size=34,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=26,
                    text_align="center",
                ),
                _score_element(
                    f"{slot['prefix']}-name",
                    "participant_name",
                    participant,
                    x=slot["name_x"],
                    y=46,
                    width=200,
                    height=38,
                    font_size=26,
                    color="#ffffff",
                    background_color="#0b1020",
                    border_radius=14,
                    text_align=slot["align"],
                ),
                _score_element(
                    f"{slot['prefix']}-score",
                    "participant_score",
                    participant,
                    x=slot["score_x"],
                    y=58,
                    width=104,
                    height=84,
                    font_size=58,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=18,
                    text_align="center",
                ),
            ]
        )
    return elements


def broadcast_list_score_elements(participants=None):
    participant_data = _score_participant_layout_data(participants)
    elements = []

    for index, participant in enumerate(participant_data):
        row_y = SCORE_LIST_VERTICAL_PADDING + (index * SCORE_LIST_ROW_HEIGHT)
        prefix = f"participant-{index + 1}"
        elements.extend(
            [
                _score_element(
                    f"{prefix}-image",
                    "participant_image",
                    participant,
                    x=32,
                    y=row_y + 8,
                    width=56,
                    height=56,
                    font_size=22,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=16,
                    text_align="center",
                ),
                _score_element(
                    f"{prefix}-name",
                    "participant_name",
                    participant,
                    x=104,
                    y=row_y + 13,
                    width=680,
                    height=46,
                    font_size=28,
                    color="#ffffff",
                    background_color="#0b1020",
                    border_radius=14,
                    text_align="left",
                ),
                _score_element(
                    f"{prefix}-score",
                    "participant_score",
                    participant,
                    x=808,
                    y=row_y + 8,
                    width=120,
                    height=56,
                    font_size=42,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=16,
                    text_align="center",
                ),
            ]
        )
    return elements


def score_elements_for_layout(participants=None, layout_mode=SCORE_LAYOUT_BROADCAST_DUEL):
    if layout_mode == SCORE_LAYOUT_BROADCAST_LIST:
        return broadcast_list_score_elements(participants)
    return broadcast_duel_score_elements(participants)


def default_score_elements(participants=None):
    """Starter layout used by new score HUD overlays."""

    return score_elements_for_layout(participants, SCORE_LAYOUT_BROADCAST_DUEL)


class SpotifyConnection(models.Model):
    """One encrypted Spotify authorization and playback cache per account."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="spotify_connection",
        blank=True,
        null=True,
    )
    access_token = EncryptedTextField(blank=True)
    refresh_token = EncryptedTextField(blank=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    connected_at = models.DateTimeField(blank=True, null=True)
    playback_cache = models.JSONField(default=dict, blank=True)
    playback_cached_at = models.DateTimeField(blank=True, null=True)
    playback_refresh_started_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        if self.owner_id:
            return f"Spotify: {self.owner}"
        return f"Spotify connection {self.pk or 'new'}"

    @property
    def is_connected(self):
        return bool(self.access_token or self.refresh_token)


class SpotifyOverlay(OverlayBrandingMixin, models.Model):
    """A freely composed browser-source overlay for Spotify playback."""

    DEFAULT_NAME = _("Spotify-Overlay")
    SOURCE_EXTRA_WIDTH = 80
    SOURCE_EXTRA_HEIGHT = 96

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="spotify_overlays",
        blank=True,
        null=True,
    )
    connection = models.ForeignKey(
        SpotifyConnection,
        on_delete=models.SET_NULL,
        related_name="overlays",
        blank=True,
        null=True,
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    name = models.CharField(max_length=120, default="Spotify-Overlay", blank=True)
    canvas_width = models.PositiveSmallIntegerField(
        default=720,
        validators=[MinValueValidator(240), MaxValueValidator(1920)],
    )
    canvas_height = models.PositiveSmallIntegerField(
        default=220,
        validators=[MinValueValidator(120), MaxValueValidator(1080)],
    )
    background_color = models.CharField(
        max_length=7,
        default="#121212",
        validators=[hex_color_validator],
    )
    background_opacity = models.PositiveSmallIntegerField(
        default=94,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    border_color = models.CharField(
        max_length=7,
        default="#1ed760",
        validators=[hex_color_validator],
    )
    border_width = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    corner_radius = models.PositiveSmallIntegerField(
        default=26,
        validators=[MinValueValidator(0), MaxValueValidator(80)],
    )
    elements = models.JSONField(default=default_spotify_elements)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        return str(self.display_name)

    @property
    def display_name(self):
        return self.name or self.DEFAULT_NAME

    @property
    def is_spotify_connected(self):
        return bool(self.connection_id and self.connection.is_connected)

    @property
    def background_rgba(self):
        red = int(self.background_color[1:3], 16)
        green = int(self.background_color[3:5], 16)
        blue = int(self.background_color[5:7], 16)
        alpha = self.background_opacity / 100

        return f"rgba({red}, {green}, {blue}, {alpha:.2f})"

    @property
    def browser_source_width(self):
        return self.canvas_width + self.SOURCE_EXTRA_WIDTH

    @property
    def browser_source_height(self):
        return self.canvas_height + self.SOURCE_EXTRA_HEIGHT

    def design_payload(self):
        return {
            "name": self.display_name,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "browser_source_width": self.browser_source_width,
            "browser_source_height": self.browser_source_height,
            "background_color": self.background_color,
            "background_opacity": self.background_opacity,
            "background_rgba": self.background_rgba,
            "border_color": self.border_color,
            "border_width": self.border_width,
            "corner_radius": self.corner_radius,
            "elements": self.elements,
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            **self.branding_payload(),
        }


class TwitchConnection(models.Model):
    """One encrypted Twitch authorization and shared metric cache per account."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="twitch_connection",
    )
    access_token = EncryptedTextField(blank=True)
    refresh_token = EncryptedTextField(blank=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    scopes = models.JSONField(default=list, blank=True)
    twitch_user_id = models.CharField(max_length=40, blank=True)
    twitch_login = models.CharField(max_length=80, blank=True)
    display_name = models.CharField(max_length=120, blank=True)
    profile_image_url = models.URLField(max_length=500, blank=True)
    connected_at = models.DateTimeField(blank=True, null=True)
    validated_at = models.DateTimeField(blank=True, null=True)
    follower_count = models.PositiveBigIntegerField(blank=True, null=True)
    follower_cached_at = models.DateTimeField(blank=True, null=True)
    subscription_count = models.PositiveBigIntegerField(blank=True, null=True)
    subscription_points = models.PositiveBigIntegerField(blank=True, null=True)
    subscription_cached_at = models.DateTimeField(blank=True, null=True)
    refresh_started_at = models.DateTimeField(blank=True, null=True)
    last_error = models.CharField(max_length=240, blank=True)
    needs_reconnect = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        return f"Twitch: {self.display_name or self.twitch_login or self.owner}"

    @property
    def is_connected(self):
        return bool(self.access_token or self.refresh_token)

    def has_scope(self, scope):
        return scope in set(self.scopes or [])


class TwitchGoalOverlay(OverlayBrandingMixin, models.Model):
    """Responsive Twitch follower or subscription browser-source goal."""

    DEFAULT_NAME = _("Twitch Goal")
    SOURCE_EXTRA_WIDTH = 0
    SOURCE_EXTRA_HEIGHT = 0

    GOAL_FOLLOWERS = "followers"
    GOAL_SUBSCRIPTIONS = "subscriptions"
    GOAL_TYPE_CHOICES = (
        (GOAL_FOLLOWERS, _("Follower goal")),
        (GOAL_SUBSCRIPTIONS, _("Subscription goal")),
    )

    METRIC_SUBSCRIPTIONS = "subscriptions"
    METRIC_POINTS = "points"
    SUBSCRIPTION_METRIC_CHOICES = (
        (METRIC_SUBSCRIPTIONS, _("Active subscriptions")),
        (METRIC_POINTS, _("Subscription points")),
    )

    MODE_TOTAL = "total"
    MODE_CAMPAIGN = "campaign"
    PROGRESS_MODE_CHOICES = (
        (MODE_TOTAL, _("Total count")),
        (MODE_CAMPAIGN, _("Campaign growth")),
    )

    LAYOUT_HORIZONTAL = GOAL_LAYOUT_HORIZONTAL
    LAYOUT_COMPACT = GOAL_LAYOUT_COMPACT
    LAYOUT_CARD = GOAL_LAYOUT_CARD
    LAYOUT_RADIAL = GOAL_LAYOUT_RADIAL
    LAYOUT_CUSTOM = GOAL_LAYOUT_CUSTOM
    LAYOUT_CHOICES = GOAL_LAYOUT_CHOICES

    ANIMATION_NONE = "none"
    ANIMATION_CONFETTI = "confetti"
    ANIMATION_FIREWORKS = "fireworks"
    ANIMATION_NEON = "neon"
    ANIMATION_BOUNCE = "bounce"
    ANIMATION_PARTICLES = "particles"
    ANIMATION_CHOICES = (
        (ANIMATION_NONE, _("None")),
        (ANIMATION_CONFETTI, _("Confetti")),
        (ANIMATION_FIREWORKS, _("Fireworks")),
        (ANIMATION_NEON, _("Neon burst")),
        (ANIMATION_BOUNCE, _("Bounce and pulse")),
        (ANIMATION_PARTICLES, _("Particle rain")),
    )

    INTENSITY_LOW = "low"
    INTENSITY_MEDIUM = "medium"
    INTENSITY_HIGH = "high"
    INTENSITY_CHOICES = (
        (INTENSITY_LOW, _("Low")),
        (INTENSITY_MEDIUM, _("Medium")),
        (INTENSITY_HIGH, _("High")),
    )

    SOUND_NONE = "none"
    SOUND_CHIME = "chime"
    SOUND_FANFARE = "fanfare"
    SOUND_ARCADE = "arcade"
    SOUND_SPARKLE = "sparkle"
    SOUND_CHOICES = (
        (SOUND_NONE, _("None")),
        (SOUND_CHIME, _("Chime")),
        (SOUND_FANFARE, _("Fanfare")),
        (SOUND_ARCADE, _("Arcade win")),
        (SOUND_SPARKLE, _("Sparkle")),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="twitch_goal_overlays",
    )
    connection = models.ForeignKey(
        TwitchConnection,
        on_delete=models.SET_NULL,
        related_name="overlays",
        blank=True,
        null=True,
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    name = models.CharField(max_length=120, default="Twitch Goal", blank=True)
    title = models.CharField(max_length=120, default="Road to the next milestone", blank=True)
    goal_type = models.CharField(
        max_length=20,
        choices=GOAL_TYPE_CHOICES,
        default=GOAL_FOLLOWERS,
    )
    subscription_metric = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_METRIC_CHOICES,
        default=METRIC_SUBSCRIPTIONS,
    )
    progress_mode = models.CharField(
        max_length=20,
        choices=PROGRESS_MODE_CHOICES,
        default=MODE_TOTAL,
    )
    target_value = models.PositiveBigIntegerField(
        default=1000,
        validators=[MinValueValidator(1), MaxValueValidator(999999999999)],
    )
    campaign_baseline = models.PositiveBigIntegerField(blank=True, null=True)

    layout_mode = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default=LAYOUT_HORIZONTAL,
    )
    canvas_width = models.PositiveSmallIntegerField(
        default=900,
        validators=[MinValueValidator(240), MaxValueValidator(1920)],
    )
    canvas_height = models.PositiveSmallIntegerField(
        default=160,
        validators=[MinValueValidator(100), MaxValueValidator(1080)],
    )
    background_color = models.CharField(
        max_length=7, default="#120c24", validators=[hex_color_validator]
    )
    background_opacity = models.PositiveSmallIntegerField(
        default=94, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    text_color = models.CharField(max_length=7, default="#ffffff", validators=[hex_color_validator])
    accent_color = models.CharField(
        max_length=7, default="#9146ff", validators=[hex_color_validator]
    )
    secondary_color = models.CharField(
        max_length=7, default="#bf94ff", validators=[hex_color_validator]
    )
    track_color = models.CharField(
        max_length=7, default="#2c2440", validators=[hex_color_validator]
    )
    border_color = models.CharField(
        max_length=7, default="#a970ff", validators=[hex_color_validator]
    )
    border_width = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(0), MaxValueValidator(24)]
    )
    corner_radius = models.PositiveSmallIntegerField(
        default=28, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    use_gradient = models.BooleanField(default=True)
    shadow_enabled = models.BooleanField(default=True)
    number_prefix = models.CharField(max_length=20, blank=True)
    number_suffix = models.CharField(max_length=20, blank=True)
    elements = models.JSONField(default=default_goal_elements)

    animation_type = models.CharField(
        max_length=20,
        choices=ANIMATION_CHOICES,
        default=ANIMATION_CONFETTI,
    )
    animation_duration = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    animation_intensity = models.CharField(
        max_length=12,
        choices=INTENSITY_CHOICES,
        default=INTENSITY_MEDIUM,
    )
    animation_primary_color = models.CharField(
        max_length=7, default="#9146ff", validators=[hex_color_validator]
    )
    animation_secondary_color = models.CharField(
        max_length=7, default="#ffffff", validators=[hex_color_validator]
    )
    sound_type = models.CharField(max_length=20, choices=SOUND_CHOICES, default=SOUND_NONE)
    sound_volume = models.PositiveSmallIntegerField(
        default=70, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    goal_revision = models.PositiveIntegerField(default=1)
    celebrated_revision = models.PositiveIntegerField(default=0)
    last_observed_progress = models.PositiveBigIntegerField(blank=True, null=True)
    celebration_sequence = models.PositiveBigIntegerField(default=0)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        return str(self.display_name)

    @property
    def display_name(self):
        return self.name or self.DEFAULT_NAME

    @property
    def display_title(self):
        if self.title.strip():
            return self.title.strip()
        return _("Follower goal") if self.goal_type == self.GOAL_FOLLOWERS else _("Sub goal")

    @property
    def background_rgba(self):
        red = int(self.background_color[1:3], 16)
        green = int(self.background_color[3:5], 16)
        blue = int(self.background_color[5:7], 16)
        return f"rgba({red}, {green}, {blue}, {self.background_opacity / 100:.2f})"

    @property
    def browser_source_width(self):
        return self.canvas_width + self.SOURCE_EXTRA_WIDTH

    @property
    def browser_source_height(self):
        return self.canvas_height + self.SOURCE_EXTRA_HEIGHT

    @property
    def shadow_css(self):
        return "0 22px 64px rgba(0, 0, 0, 0.42)" if self.shadow_enabled else "none"

    def required_scope(self):
        if self.goal_type == self.GOAL_SUBSCRIPTIONS:
            return "channel:read:subscriptions"
        return "moderator:read:followers"

    def raw_connection_value(self):
        if not self.connection_id:
            return None
        if self.goal_type == self.GOAL_FOLLOWERS:
            return self.connection.follower_count
        if self.subscription_metric == self.METRIC_POINTS:
            return self.connection.subscription_points
        return self.connection.subscription_count

    def progress_values(self, raw_value):
        if raw_value is None:
            return {
                "raw_value": None,
                "current_value": None,
                "remaining": self.target_value,
                "progress_percent": 0,
                "is_reached": False,
            }
        current = int(raw_value)
        if self.progress_mode == self.MODE_CAMPAIGN:
            if self.campaign_baseline is None:
                progress = 0
            else:
                progress = max(current - self.campaign_baseline, 0)
        else:
            progress = current
        return {
            "raw_value": current,
            "current_value": progress,
            "remaining": max(self.target_value - progress, 0),
            "progress_percent": min(round((progress / self.target_value) * 100, 2), 100),
            "is_reached": progress >= self.target_value,
        }

    def design_payload(self):
        return {
            "name": self.display_name,
            "title": self.display_title,
            "goal_type": self.goal_type,
            "subscription_metric": self.subscription_metric,
            "progress_mode": self.progress_mode,
            "target_value": self.target_value,
            "layout_mode": self.layout_mode,
            "layout_dimensions": GOAL_LAYOUT_DIMENSIONS,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "browser_source_width": self.browser_source_width,
            "browser_source_height": self.browser_source_height,
            "background_color": self.background_color,
            "background_opacity": self.background_opacity,
            "background_rgba": self.background_rgba,
            "text_color": self.text_color,
            "accent_color": self.accent_color,
            "secondary_color": self.secondary_color,
            "track_color": self.track_color,
            "border_color": self.border_color,
            "border_width": self.border_width,
            "corner_radius": self.corner_radius,
            "use_gradient": self.use_gradient,
            "shadow_enabled": self.shadow_enabled,
            "shadow_css": self.shadow_css,
            "number_prefix": self.number_prefix,
            "number_suffix": self.number_suffix,
            "elements": self.elements,
            "animation": {
                "type": self.animation_type,
                "duration": self.animation_duration,
                "intensity": self.animation_intensity,
                "primary_color": self.animation_primary_color,
                "secondary_color": self.animation_secondary_color,
                "sound": self.sound_type,
                "volume": self.sound_volume,
            },
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            **self.branding_payload(),
        }


class ScoreOverlay(OverlayBrandingMixin, models.Model):
    """Freely composed score HUD for players or teams."""

    DEFAULT_NAME = _("Score HUD")
    LAYOUT_BROADCAST_DUEL = SCORE_LAYOUT_BROADCAST_DUEL
    LAYOUT_BROADCAST_LIST = SCORE_LAYOUT_BROADCAST_LIST
    LAYOUT_CUSTOM = SCORE_LAYOUT_CUSTOM
    LAYOUT_CHOICES = SCORE_LAYOUT_CHOICES
    STRUCTURED_LAYOUTS = SCORE_STRUCTURED_LAYOUTS
    MAX_PARTICIPANTS = 8
    MIN_PARTICIPANTS = 2
    MAX_SCORE = 99999
    MIN_SCORE = -99999
    SOURCE_EXTRA_WIDTH = 80
    SOURCE_EXTRA_HEIGHT = 96

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="score_overlays",
        blank=True,
        null=True,
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    name = models.CharField(max_length=120, default="Score HUD", blank=True)
    layout_mode = models.CharField(
        max_length=24,
        choices=LAYOUT_CHOICES,
        default=LAYOUT_BROADCAST_DUEL,
    )
    canvas_width = models.PositiveSmallIntegerField(
        default=SCORE_DUEL_CANVAS[0],
        validators=[MinValueValidator(320), MaxValueValidator(1920)],
    )
    canvas_height = models.PositiveSmallIntegerField(
        default=SCORE_DUEL_CANVAS[1],
        validators=[MinValueValidator(140), MaxValueValidator(1080)],
    )
    background_color = models.CharField(
        max_length=7,
        default="#0f172a",
        validators=[hex_color_validator],
    )
    background_opacity = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    border_color = models.CharField(
        max_length=7,
        default="#38bdf8",
        validators=[hex_color_validator],
    )
    border_width = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    corner_radius = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(80)],
    )
    allow_negative_scores = models.BooleanField(default=False)
    elements = models.JSONField(default=default_score_elements)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        return str(self.display_name)

    @property
    def display_name(self):
        return self.name or self.DEFAULT_NAME

    @property
    def ordered_participants(self):
        if self.pk is None:
            return []

        cached_participants = getattr(self, "_prefetched_objects_cache", {}).get("participants")
        if cached_participants is not None:
            return sorted(
                cached_participants,
                key=lambda participant: (
                    participant.sort_order,
                    participant.created_at,
                    participant.pk,
                ),
            )

        return self.participants.order_by("sort_order", "created_at", "pk")

    @property
    def participant_count(self):
        if self.pk is None:
            return 0

        cached_participants = getattr(self, "_prefetched_objects_cache", {}).get("participants")
        if cached_participants is not None:
            return len(cached_participants)

        return self.participants.count()

    @property
    def background_rgba(self):
        red = int(self.background_color[1:3], 16)
        green = int(self.background_color[3:5], 16)
        blue = int(self.background_color[5:7], 16)
        alpha = self.background_opacity / 100
        return f"rgba({red}, {green}, {blue}, {alpha:.2f})"

    @property
    def browser_source_width(self):
        return self.canvas_width + self.SOURCE_EXTRA_WIDTH

    @property
    def browser_source_height(self):
        return self.canvas_height + self.SOURCE_EXTRA_HEIGHT

    def layout_templates_payload(self):
        participants = list(self.ordered_participants) if self.pk else default_score_participants()
        return {
            self.LAYOUT_BROADCAST_DUEL: {
                "canvas_width": SCORE_DUEL_CANVAS[0],
                "canvas_height": SCORE_DUEL_CANVAS[1],
                "background_color": "#0f172a",
                "background_opacity": 0,
                "border_color": "#38bdf8",
                "border_width": 0,
                "corner_radius": 0,
                "elements": score_elements_for_layout(participants, self.LAYOUT_BROADCAST_DUEL),
            },
            self.LAYOUT_BROADCAST_LIST: {
                "canvas_width": score_layout_dimensions(
                    self.LAYOUT_BROADCAST_LIST,
                    len(participants),
                )[0],
                "canvas_height": score_layout_dimensions(
                    self.LAYOUT_BROADCAST_LIST,
                    len(participants),
                )[1],
                "background_color": "#0f172a",
                "background_opacity": 0,
                "border_color": "#38bdf8",
                "border_width": 0,
                "corner_radius": 0,
                "elements": score_elements_for_layout(participants, self.LAYOUT_BROADCAST_LIST),
            },
        }

    def design_payload(self):
        return {
            "name": self.display_name,
            "layout_mode": self.layout_mode,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "browser_source_width": self.browser_source_width,
            "browser_source_height": self.browser_source_height,
            "background_color": self.background_color,
            "background_opacity": self.background_opacity,
            "background_rgba": self.background_rgba,
            "border_color": self.border_color,
            "border_width": self.border_width,
            "corner_radius": self.corner_radius,
            "allow_negative_scores": self.allow_negative_scores,
            "elements": self.elements,
            "layout_templates": self.layout_templates_payload(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            **self.branding_payload(),
        }

    def state_payload(self):
        participants = []
        for participant in self.ordered_participants:
            participants.append(
                {
                    "id": str(participant.public_id),
                    "name": participant.name,
                    "score": participant.score,
                    "accent_color": participant.accent_color,
                    "initials": participant.initials,
                    "image_url": (
                        participant.image_asset.public_url if participant.image_asset_id else ""
                    ),
                }
            )

        return {
            **self.design_payload(),
            "participants": participants,
        }


class ScoreParticipant(models.Model):
    """Single player or team row with an atomic score counter."""

    overlay = models.ForeignKey(
        ScoreOverlay,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    score = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(ScoreOverlay.MIN_SCORE),
            MaxValueValidator(ScoreOverlay.MAX_SCORE),
        ],
    )
    accent_color = models.CharField(
        max_length=7,
        default="#38bdf8",
        validators=[hex_color_validator],
    )
    image_asset = models.ForeignKey(
        OverlayAsset,
        on_delete=models.SET_NULL,
        related_name="+",
        blank=True,
        null=True,
        limit_choices_to={"kind": OverlayAsset.KIND_IMAGE},
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sort_order", "created_at", "pk")

    def __str__(self):
        return f"{self.name} ({self.score})"

    @property
    def initials(self):
        words = [word for word in self.name.strip().split() if word]
        if not words:
            return "?"
        if len(words) == 1:
            return words[0][:2].upper()
        return f"{words[0][0]}{words[-1][0]}".upper()


class TimerOverlay(OverlayBrandingMixin, models.Model):
    """Persistent countdown or stopwatch browser-source overlay."""

    DEFAULT_NAME = _("Stream Timer")
    MAX_SECONDS = (100 * 60 * 60) - 1

    MODE_COUNTDOWN = "countdown"
    MODE_STOPWATCH = "stopwatch"
    MODE_CHOICES = (
        (MODE_COUNTDOWN, _("Countdown")),
        (MODE_STOPWATCH, _("Stopwatch")),
    )

    TEMPLATE_MINIMAL = "minimal"
    TEMPLATE_GLASS = "glass"
    TEMPLATE_NEON = "neon"
    DESIGN_TEMPLATE_CHOICES = (
        (TEMPLATE_MINIMAL, _("Minimal")),
        (TEMPLATE_GLASS, _("Glass")),
        (TEMPLATE_NEON, _("Neon")),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="timer_overlays",
        blank=True,
        null=True,
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    name = models.CharField(max_length=120, default="Stream Timer", blank=True)
    label = models.CharField(max_length=120, default="Starting soon", blank=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_COUNTDOWN)
    duration_seconds = models.PositiveIntegerField(
        default=300,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_SECONDS)],
    )
    accumulated_seconds = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(MAX_SECONDS)],
    )
    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(blank=True, null=True)

    design_template = models.CharField(
        max_length=20,
        choices=DESIGN_TEMPLATE_CHOICES,
        default=TEMPLATE_GLASS,
    )
    background_color = models.CharField(
        max_length=7,
        default="#111827",
        validators=[hex_color_validator],
    )
    background_opacity = models.PositiveSmallIntegerField(
        default=86,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    text_color = models.CharField(
        max_length=7,
        default="#f8fafc",
        validators=[hex_color_validator],
    )
    accent_color = models.CharField(
        max_length=7,
        default="#8b5cf6",
        validators=[hex_color_validator],
    )
    border_color = models.CharField(
        max_length=7,
        default="#a78bfa",
        validators=[hex_color_validator],
    )
    border_width = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(12)],
    )
    corner_radius = models.PositiveSmallIntegerField(
        default=24,
        validators=[MinValueValidator(0), MaxValueValidator(64)],
    )
    overlay_width = models.PositiveSmallIntegerField(
        default=520,
        validators=[MinValueValidator(260), MaxValueValidator(1200)],
    )
    overlay_height = models.PositiveSmallIntegerField(
        default=230,
        validators=[MinValueValidator(140), MaxValueValidator(600)],
    )
    label_text_size = models.PositiveSmallIntegerField(
        default=16,
        validators=[MinValueValidator(10), MaxValueValidator(40)],
    )
    timer_text_size = models.PositiveSmallIntegerField(
        default=76,
        validators=[MinValueValidator(36), MaxValueValidator(160)],
    )
    show_progress = models.BooleanField(default=True)
    shadow_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        return str(self.display_name)

    @property
    def display_name(self):
        return self.name or self.DEFAULT_NAME

    @property
    def display_label(self):
        return self.label.strip()

    @property
    def background_rgba(self):
        red = int(self.background_color[1:3], 16)
        green = int(self.background_color[3:5], 16)
        blue = int(self.background_color[5:7], 16)
        alpha = self.background_opacity / 100
        return f"rgba({red}, {green}, {blue}, {alpha:.2f})"

    @property
    def shadow_css(self):
        if not self.shadow_enabled:
            return "none"
        return "0 20px 52px rgba(0, 0, 0, 0.38)"

    def elapsed_seconds(self, now=None):
        elapsed = self.accumulated_seconds
        if self.is_running and self.started_at:
            now = now or timezone.now()
            elapsed += max(0, int((now - self.started_at).total_seconds()))

        limit = self.duration_seconds if self.mode == self.MODE_COUNTDOWN else self.MAX_SECONDS
        return min(elapsed, limit)

    def display_seconds(self, now=None):
        elapsed = self.elapsed_seconds(now)
        if self.mode == self.MODE_COUNTDOWN:
            return max(self.duration_seconds - elapsed, 0)
        return elapsed

    def effective_is_running(self, now=None):
        if not self.is_running or not self.started_at:
            return False
        limit = self.duration_seconds if self.mode == self.MODE_COUNTDOWN else self.MAX_SECONDS
        return self.elapsed_seconds(now) < limit

    def progress_percent(self, now=None):
        if self.mode != self.MODE_COUNTDOWN or self.duration_seconds <= 0:
            return 0
        return min(round((self.elapsed_seconds(now) / self.duration_seconds) * 100), 100)

    def formatted_time(self, now=None):
        seconds = self.display_seconds(now)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours or self.duration_seconds >= 3600:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def state_payload(self):
        now = timezone.now()
        return {
            "name": self.display_name,
            "label": self.display_label,
            "mode": self.mode,
            "duration_seconds": self.duration_seconds,
            "display_seconds": self.display_seconds(now),
            "is_running": self.effective_is_running(now),
            "is_complete": (self.mode == self.MODE_COUNTDOWN and self.display_seconds(now) == 0),
            "progress_percent": self.progress_percent(now),
            "server_time": now.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            "design": {
                "template": self.design_template,
                "background_color": self.background_color,
                "background_opacity": self.background_opacity,
                "background_rgba": self.background_rgba,
                "text_color": self.text_color,
                "accent_color": self.accent_color,
                "border_color": self.border_color,
                "border_width": self.border_width,
                "corner_radius": self.corner_radius,
                "overlay_width": self.overlay_width,
                "overlay_height": self.overlay_height,
                "label_text_size": self.label_text_size,
                "timer_text_size": self.timer_text_size,
                "show_progress": self.show_progress,
                "shadow_enabled": self.shadow_enabled,
                "shadow_css": self.shadow_css,
                **self.branding_payload(),
            },
        }
