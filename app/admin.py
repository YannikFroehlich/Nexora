from django.contrib import admin

from app.models import (
    OverlayAsset,
    OverlayVersion,
    ScoreOverlay,
    ScoreParticipant,
    SpotifyConnection,
    SpotifyOverlay,
    TimerOverlay,
    TwitchConnection,
    TwitchGoalOverlay,
    WinChallenge,
    WinChallengeGame,
)


@admin.register(OverlayAsset)
class OverlayAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "owner", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("name", "owner__username", "public_token")
    readonly_fields = ("public_token", "created_at")


@admin.register(OverlayVersion)
class OverlayVersionAdmin(admin.ModelAdmin):
    list_display = ("overlay_type", "overlay_id", "owner", "reason", "created_at")
    list_filter = ("overlay_type", "reason", "created_at")
    search_fields = ("owner__username", "overlay_id", "fingerprint")
    readonly_fields = (
        "owner",
        "overlay_type",
        "overlay_id",
        "snapshot",
        "fingerprint",
        "reason",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class WinChallengeGameInline(admin.TabularInline):
    model = WinChallengeGame
    extra = 0
    fields = ("name", "wins", "target_wins", "sort_order", "created_at")
    readonly_fields = ("created_at",)


@admin.register(WinChallenge)
class WinChallengeAdmin(admin.ModelAdmin):
    inlines = (WinChallengeGameInline,)
    list_display = ("overlay_title", "owner", "total_wins", "games_count", "updated_at")
    list_filter = ("design_template", "shadow_enabled", "show_games_list", "owner")
    search_fields = ("title", "public_token", "owner__username")
    readonly_fields = ("public_token", "created_at", "updated_at")

    @admin.display(description="Overlay title")
    def overlay_title(self, obj):
        return obj.display_title


@admin.register(WinChallengeGame)
class WinChallengeGameAdmin(admin.ModelAdmin):
    list_display = ("name", "challenge", "wins", "target_wins", "sort_order", "created_at")
    list_filter = ("challenge",)
    search_fields = ("name", "challenge__title")
    readonly_fields = ("created_at",)


class ScoreParticipantInline(admin.TabularInline):
    model = ScoreParticipant
    extra = 0
    fields = ("name", "score", "accent_color", "image_asset", "sort_order", "created_at")
    readonly_fields = ("created_at",)


@admin.register(ScoreOverlay)
class ScoreOverlayAdmin(admin.ModelAdmin):
    inlines = (ScoreParticipantInline,)
    list_display = (
        "display_name",
        "owner",
        "layout_mode",
        "canvas_size",
        "participant_count",
        "updated_at",
    )
    list_filter = ("layout_mode", "allow_negative_scores", "background_opacity", "owner")
    search_fields = ("name", "public_token", "owner__username")
    readonly_fields = ("public_token", "created_at", "updated_at")

    @admin.display(description="Size")
    def canvas_size(self, obj):
        return f"{obj.canvas_width} x {obj.canvas_height}"


@admin.register(ScoreParticipant)
class ScoreParticipantAdmin(admin.ModelAdmin):
    list_display = ("name", "overlay", "score", "sort_order", "created_at")
    list_filter = ("overlay",)
    search_fields = ("name", "overlay__name")
    readonly_fields = ("public_id", "created_at")


@admin.register(SpotifyOverlay)
class SpotifyOverlayAdmin(admin.ModelAdmin):
    list_display = ("display_name", "owner", "canvas_size", "spotify_connected", "updated_at")
    list_select_related = ("connection",)
    list_filter = ("background_opacity", "connection__connected_at", "owner")
    search_fields = ("name", "public_token", "owner__username")
    readonly_fields = (
        "public_token",
        "connection",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Size")
    def canvas_size(self, obj):
        return f"{obj.canvas_width} × {obj.canvas_height}"

    @admin.display(boolean=True, description="Spotify connected")
    def spotify_connected(self, obj):
        return obj.is_spotify_connected


@admin.register(SpotifyConnection)
class SpotifyConnectionAdmin(admin.ModelAdmin):
    list_display = ("owner", "spotify_connected", "connected_at", "playback_cached_at")
    list_filter = ("connected_at",)
    search_fields = ("owner__username",)
    exclude = ("access_token", "refresh_token", "playback_cache")
    readonly_fields = (
        "owner",
        "token_expires_at",
        "connected_at",
        "playback_cached_at",
        "playback_refresh_started_at",
        "created_at",
        "updated_at",
    )

    @admin.display(boolean=True, description="Spotify connected")
    def spotify_connected(self, obj):
        return obj.is_connected

    def has_add_permission(self, request):
        return False


@admin.register(TwitchGoalOverlay)
class TwitchGoalOverlayAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "owner",
        "goal_type",
        "progress_mode",
        "target_value",
        "twitch_connected",
        "updated_at",
    )
    list_select_related = ("connection",)
    list_filter = ("goal_type", "progress_mode", "layout_mode", "animation_type", "owner")
    search_fields = ("name", "title", "public_token", "owner__username")
    readonly_fields = (
        "public_token",
        "connection",
        "campaign_baseline",
        "goal_revision",
        "celebrated_revision",
        "last_observed_progress",
        "celebration_sequence",
        "completed_at",
        "created_at",
        "updated_at",
    )

    @admin.display(boolean=True, description="Twitch connected")
    def twitch_connected(self, obj):
        return bool(obj.connection_id and obj.connection.is_connected)


@admin.register(TwitchConnection)
class TwitchConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "owner",
        "display_name",
        "twitch_connected",
        "validated_at",
        "follower_cached_at",
        "subscription_cached_at",
    )
    search_fields = ("owner__username", "twitch_login", "display_name", "twitch_user_id")
    exclude = ("access_token", "refresh_token")
    readonly_fields = (
        "owner",
        "token_expires_at",
        "scopes",
        "twitch_user_id",
        "twitch_login",
        "display_name",
        "profile_image_url",
        "connected_at",
        "validated_at",
        "follower_count",
        "follower_cached_at",
        "subscription_count",
        "subscription_points",
        "subscription_cached_at",
        "last_error",
        "needs_reconnect",
        "created_at",
        "updated_at",
    )

    @admin.display(boolean=True, description="Twitch connected")
    def twitch_connected(self, obj):
        return obj.is_connected

    def has_add_permission(self, request):
        return False


@admin.register(TimerOverlay)
class TimerOverlayAdmin(admin.ModelAdmin):
    list_display = ("display_name", "owner", "mode", "timer_running", "updated_at")
    list_filter = ("mode", "design_template", "is_running", "owner")
    search_fields = ("name", "label", "public_token", "owner__username")
    readonly_fields = ("public_token", "created_at", "updated_at")

    @admin.display(boolean=True, description="Running")
    def timer_running(self, obj):
        return obj.effective_is_running()
