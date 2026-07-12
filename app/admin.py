from django.contrib import admin

from app.models import WinChallenge, WinChallengeGame


class WinChallengeGameInline(admin.TabularInline):
    model = WinChallengeGame
    extra = 0
    fields = ("name", "wins", "target_wins", "sort_order", "created_at")
    readonly_fields = ("created_at",)


@admin.register(WinChallenge)
class WinChallengeAdmin(admin.ModelAdmin):
    inlines = (WinChallengeGameInline,)
    list_display = ("overlay_title", "total_wins", "games_count", "updated_at")
    list_filter = ("design_template", "shadow_enabled", "show_games_list")
    search_fields = ("title", "public_token")
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
