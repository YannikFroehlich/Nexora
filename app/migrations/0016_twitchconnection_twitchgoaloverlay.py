import app.encrypted_fields
import app.models
import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0015_score_broadcast_layout"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TwitchConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("access_token", app.encrypted_fields.EncryptedTextField(blank=True)),
                ("refresh_token", app.encrypted_fields.EncryptedTextField(blank=True)),
                ("token_expires_at", models.DateTimeField(blank=True, null=True)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("twitch_user_id", models.CharField(blank=True, max_length=40)),
                ("twitch_login", models.CharField(blank=True, max_length=80)),
                ("display_name", models.CharField(blank=True, max_length=120)),
                ("profile_image_url", models.URLField(blank=True, max_length=500)),
                ("connected_at", models.DateTimeField(blank=True, null=True)),
                ("validated_at", models.DateTimeField(blank=True, null=True)),
                ("follower_count", models.PositiveBigIntegerField(blank=True, null=True)),
                ("follower_cached_at", models.DateTimeField(blank=True, null=True)),
                ("subscription_count", models.PositiveBigIntegerField(blank=True, null=True)),
                ("subscription_points", models.PositiveBigIntegerField(blank=True, null=True)),
                ("subscription_cached_at", models.DateTimeField(blank=True, null=True)),
                ("refresh_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=240)),
                ("needs_reconnect", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="twitch_connection", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-updated_at", "-created_at")},
        ),
        migrations.CreateModel(
            name="TwitchGoalOverlay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("font_family", models.CharField(choices=[("system", "System default"), ("arial", "Arial"), ("verdana", "Verdana"), ("trebuchet", "Trebuchet MS"), ("georgia", "Georgia"), ("times", "Times New Roman"), ("courier", "Courier New")], default="system", max_length=20)),
                ("public_token", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("name", models.CharField(blank=True, default="Twitch Goal", max_length=120)),
                ("title", models.CharField(blank=True, default="Road to the next milestone", max_length=120)),
                ("goal_type", models.CharField(choices=[("followers", "Follower goal"), ("subscriptions", "Subscription goal")], default="followers", max_length=20)),
                ("subscription_metric", models.CharField(choices=[("subscriptions", "Active subscriptions"), ("points", "Subscription points")], default="subscriptions", max_length=20)),
                ("progress_mode", models.CharField(choices=[("total", "Total count"), ("campaign", "Campaign growth")], default="total", max_length=20)),
                ("target_value", models.PositiveBigIntegerField(default=1000, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(999999999999)])),
                ("campaign_baseline", models.PositiveBigIntegerField(blank=True, null=True)),
                ("layout_mode", models.CharField(choices=[("horizontal", "Horizontal bar"), ("compact", "Compact bar"), ("card", "Vertical card"), ("radial", "Radial goal"), ("custom", "Custom")], default="horizontal", max_length=20)),
                ("canvas_width", models.PositiveSmallIntegerField(default=900, validators=[django.core.validators.MinValueValidator(240), django.core.validators.MaxValueValidator(1920)])),
                ("canvas_height", models.PositiveSmallIntegerField(default=160, validators=[django.core.validators.MinValueValidator(100), django.core.validators.MaxValueValidator(1080)])),
                ("background_color", models.CharField(default="#120c24", max_length=7, validators=[django.core.validators.RegexValidator(message="Enter a valid hex color, for example #14b8a6.", regex="^#[0-9A-Fa-f]{6}$")])),
                ("background_opacity", models.PositiveSmallIntegerField(default=94, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("text_color", models.CharField(default="#ffffff", max_length=7, validators=[app.models.hex_color_validator])),
                ("accent_color", models.CharField(default="#9146ff", max_length=7, validators=[app.models.hex_color_validator])),
                ("secondary_color", models.CharField(default="#bf94ff", max_length=7, validators=[app.models.hex_color_validator])),
                ("track_color", models.CharField(default="#2c2440", max_length=7, validators=[app.models.hex_color_validator])),
                ("border_color", models.CharField(default="#a970ff", max_length=7, validators=[app.models.hex_color_validator])),
                ("border_width", models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(24)])),
                ("corner_radius", models.PositiveSmallIntegerField(default=28, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("use_gradient", models.BooleanField(default=True)),
                ("shadow_enabled", models.BooleanField(default=True)),
                ("number_prefix", models.CharField(blank=True, max_length=20)),
                ("number_suffix", models.CharField(blank=True, max_length=20)),
                ("elements", models.JSONField(default=app.models.default_goal_elements)),
                ("animation_type", models.CharField(choices=[("none", "None"), ("confetti", "Confetti"), ("fireworks", "Fireworks"), ("neon", "Neon burst"), ("bounce", "Bounce and pulse"), ("particles", "Particle rain")], default="confetti", max_length=20)),
                ("animation_duration", models.PositiveSmallIntegerField(default=5, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)])),
                ("animation_intensity", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=12)),
                ("animation_primary_color", models.CharField(default="#9146ff", max_length=7, validators=[app.models.hex_color_validator])),
                ("animation_secondary_color", models.CharField(default="#ffffff", max_length=7, validators=[app.models.hex_color_validator])),
                ("sound_type", models.CharField(choices=[("none", "None"), ("chime", "Chime"), ("fanfare", "Fanfare"), ("arcade", "Arcade win"), ("sparkle", "Sparkle")], default="none", max_length=20)),
                ("sound_volume", models.PositiveSmallIntegerField(default=70, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("goal_revision", models.PositiveIntegerField(default=1)),
                ("celebrated_revision", models.PositiveIntegerField(default=0)),
                ("last_observed_progress", models.PositiveBigIntegerField(blank=True, null=True)),
                ("celebration_sequence", models.PositiveBigIntegerField(default=0)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("background_asset", models.ForeignKey(blank=True, limit_choices_to={"kind": "image"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="app.overlayasset")),
                ("connection", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="overlays", to="app.twitchconnection")),
                ("font_asset", models.ForeignKey(blank=True, limit_choices_to={"kind": "font"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="app.overlayasset")),
                ("logo_asset", models.ForeignKey(blank=True, limit_choices_to={"kind": "image"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="app.overlayasset")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="twitch_goal_overlays", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-updated_at", "-created_at")},
        ),
    ]
