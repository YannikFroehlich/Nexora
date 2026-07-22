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
