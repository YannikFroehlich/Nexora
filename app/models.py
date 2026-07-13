import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _


hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message=_("Enter a valid hex color, for example #14b8a6."),
)


class WinChallenge(models.Model):
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
            return sorted(cached_games, key=lambda game: (game.sort_order, game.created_at, game.pk))

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

        return [
            games[index:index + 3]
            for index in range(0, len(games), 3)
        ]

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
            },
        }


class WinChallengeGame(models.Model):
    """Single game row with its own atomic win counter."""

    challenge = models.ForeignKey(
        WinChallenge,
        on_delete=models.CASCADE,
        related_name="games",
    )
    name = models.CharField(max_length=120)
    wins = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(99999)],
    )
    target_wins = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(99999)],
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
    def progress_percent(self):
        if self.target_wins <= 0:
            return 0

        return min(round((self.wins / self.target_wins) * 100), 100)
