from django.contrib import admin

from app.models import SpotifyOverlay, TimerOverlay, WinChallenge, WinChallengeGame


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


@admin.register(SpotifyOverlay)
class SpotifyOverlayAdmin(admin.ModelAdmin):
    list_display = ("display_name", "owner", "canvas_size", "spotify_connected", "updated_at")
    list_filter = ("background_opacity", "spotify_connected_at", "owner")
    search_fields = ("name", "public_token", "owner__username")
    readonly_fields = (
        "public_token",
        "spotify_connected_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Size")
    def canvas_size(self, obj):
        return f"{obj.canvas_width} × {obj.canvas_height}"

    @admin.display(boolean=True, description="Spotify connected")
    def spotify_connected(self, obj):
        return obj.is_spotify_connected


@admin.register(TimerOverlay)
class TimerOverlayAdmin(admin.ModelAdmin):
    list_display = ("display_name", "owner", "mode", "timer_running", "updated_at")
    list_filter = ("mode", "design_template", "is_running", "owner")
    search_fields = ("name", "label", "public_token", "owner__username")
    readonly_fields = ("public_token", "created_at", "updated_at")

    @admin.display(boolean=True, description="Running")
    def timer_running(self, obj):
        return obj.effective_is_running()
