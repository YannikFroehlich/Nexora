import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WinChallenge",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "public_token",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("title", models.CharField(blank=True, max_length=120)),
                (
                    "target_wins",
                    models.PositiveIntegerField(
                        default=10,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(9999),
                        ],
                    ),
                ),
                (
                    "design_template",
                    models.CharField(
                        choices=[
                            ("minimal", "Minimal"),
                            ("glass", "Glass"),
                            ("neon", "Neon"),
                        ],
                        default="glass",
                        max_length=20,
                    ),
                ),
                (
                    "background_color",
                    models.CharField(
                        default="#111827",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Enter a valid hex color, for example #14b8a6.",
                                regex="^#[0-9A-Fa-f]{6}$",
                            )
                        ],
                    ),
                ),
                (
                    "background_opacity",
                    models.PositiveSmallIntegerField(
                        default=82,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "text_color",
                    models.CharField(
                        default="#f8fafc",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Enter a valid hex color, for example #14b8a6.",
                                regex="^#[0-9A-Fa-f]{6}$",
                            )
                        ],
                    ),
                ),
                (
                    "accent_color",
                    models.CharField(
                        default="#14b8a6",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Enter a valid hex color, for example #14b8a6.",
                                regex="^#[0-9A-Fa-f]{6}$",
                            )
                        ],
                    ),
                ),
                (
                    "border_color",
                    models.CharField(
                        default="#2dd4bf",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Enter a valid hex color, for example #14b8a6.",
                                regex="^#[0-9A-Fa-f]{6}$",
                            )
                        ],
                    ),
                ),
                (
                    "corner_radius",
                    models.PositiveSmallIntegerField(
                        default=22,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(64),
                        ],
                    ),
                ),
                (
                    "border_width",
                    models.PositiveSmallIntegerField(
                        default=1,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(12),
                        ],
                    ),
                ),
                (
                    "padding",
                    models.PositiveSmallIntegerField(
                        default=24,
                        validators=[
                            django.core.validators.MinValueValidator(8),
                            django.core.validators.MaxValueValidator(64),
                        ],
                    ),
                ),
                ("shadow_enabled", models.BooleanField(default=True)),
                ("show_games_list", models.BooleanField(default=True)),
                ("show_progress_bar", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="win_challenges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at", "-created_at"),
            },
        ),
        migrations.CreateModel(
            name="WinChallengeGame",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                (
                    "wins",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(99999),
                        ],
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="games",
                        to="app.winchallenge",
                    ),
                ),
            ],
            options={
                "ordering": ("sort_order", "created_at", "pk"),
            },
        ),
    ]
