import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection as database_connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from app import overlay_versions
from app.forms import (
    ScoreOverlayForm,
    SpotifyOverlayForm,
    TimerOverlayForm,
    WinChallengeCreateForm,
    WinChallengeDesignForm,
)
from app.models import (
    OverlayAsset,
    OverlayVersion,
    ScoreOverlay,
    ScoreParticipant,
    SpotifyConnection,
    SpotifyOverlay,
    TimerOverlay,
    WinChallenge,
    WinChallengeGame,
)

User = get_user_model()


def uploaded_png(name="logo.png", color=(20, 184, 166, 255)):
    buffer = BytesIO()
    Image.new("RGBA", (4, 4), color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class HomeViewTests(TestCase):
    def test_header_and_footer_expose_primary_destinations(self):
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertContains(response, f'href="{reverse("overlay_dashboard")}"')
        self.assertNotContains(response, f'href="{reverse("spotify_list")}"')
        self.assertNotContains(response, f'href="{reverse("winchallenge_list")}"')
        self.assertContains(response, f'href="{reverse("demo")}"')
        self.assertContains(response, f'href="{reverse("about")}"')
        self.assertContains(response, 'class="header-logo__image"')
        self.assertContains(response, "imgs/icons/nexora_logo.webp")
        self.assertEqual(content.count(f'href="{reverse("home")}"'), 2)

    def test_header_exposes_accessible_mobile_navigation(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'id="mobile-menu-toggle"')
        self.assertContains(response, 'aria-controls="header-menu"')
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, "data-open-label=")
        self.assertContains(response, "data-close-label=")
        self.assertContains(response, 'class="header-menu" id="header-menu"')

    def test_page_exposes_skip_link_landmarks_and_public_indexing(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'class="skip-link" href="#main-content"')
        self.assertContains(response, '<main id="main-content" tabindex="-1">')
        self.assertContains(response, 'aria-label="Hauptnavigation"')
        self.assertContains(response, 'aria-label="Footer-Navigation"')
        self.assertContains(response, '<meta name="robots" content="index, follow">')
        self.assertContains(response, '<link rel="canonical" href="http://testserver/">')
        self.assertContains(response, "imgs/icons/nexora_icon.png")

    def test_anonymous_header_surfaces_signup_without_losing_destination(self):
        response = self.client.get(reverse("demo"))

        self.assertContains(
            response,
            f'href="{reverse("signup")}?next={reverse("demo")}"',
        )

    def test_header_marks_current_tool_area_as_active(self):
        user = User.objects.create_user(username="header-user")
        self.client.force_login(user)

        response = self.client.get(reverse("spotify_create"))

        self.assertRegex(
            response.content.decode(),
            rf'href="{reverse("overlay_dashboard")}"\s+aria-current="page"',
        )
        self.assertNotContains(response, "header-create-button")

    def test_home_uses_selected_language_for_content_and_document(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertContains(response, "Custom OBS overlays made simple")
        self.assertContains(response, "Now playing")
        self.assertIn('<html lang="en">', content)

    def test_anonymous_overlay_actions_explain_and_preserve_signup_destination(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, f'href="{reverse("demo")}"')
        self.assertContains(
            response,
            f'href="{reverse("signup")}?next={reverse("spotify_create")}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("signup")}?next={reverse("winchallenge_create")}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("signup")}?next={reverse("timer_create")}"',
        )
        self.assertContains(
            response, "Kostenloses Konto zum Speichern und f\u00fcr OBS erforderlich."
        )

    def test_authenticated_overlay_actions_open_the_selected_editor(self):
        user = User.objects.create_user(username="home-creator")
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, f'href="{reverse("spotify_create")}"')
        self.assertContains(response, f'href="{reverse("winchallenge_create")}"')
        self.assertContains(response, f'href="{reverse("timer_create")}"')

    @override_settings(APP_VERSION="9.8.7-test")
    def test_footer_uses_configured_app_version(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Version 9.8.7-test")


class DemoViewTests(TestCase):
    def test_demo_is_public_and_contains_both_interactive_previews(self):
        response = self.client.get(reverse("demo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-demo-card="spotify"')
        self.assertContains(response, 'data-demo-card="winchallenge"')
        self.assertContains(response, 'data-demo-style="neon"', count=2)
        self.assertContains(response, "data-demo-progress")

    def test_demo_signup_actions_return_to_selected_editor(self):
        response = self.client.get(reverse("demo"))

        self.assertContains(
            response,
            f'href="{reverse("signup")}?next={reverse("spotify_create")}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("signup")}?next={reverse("winchallenge_create")}"',
        )

    def test_demo_is_available_in_english(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

        response = self.client.get(reverse("demo"))

        self.assertContains(response, "Build a sample overlay in seconds")
        self.assertContains(response, "Every change updates the preview immediately.")

    def test_demo_has_breadcrumb_and_unique_meta_description(self):
        response = self.client.get(reverse("demo"))

        self.assertContains(response, 'class="breadcrumbs"')
        self.assertContains(response, 'aria-current="page">Interaktive Demo')
        self.assertContains(response, "interaktive Spotify- und Win-Challenge-Overlay-Demo")


class DiscoverabilityTests(TestCase):
    def test_robots_file_keeps_private_workspaces_out_of_search(self):
        response = self.client.get(reverse("robots_txt"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("Disallow: /accounts/", content)
        self.assertIn("Disallow: /overlays/", content)
        self.assertIn("Disallow: /scores/", content)
        self.assertIn("Disallow: /spotify/", content)
        self.assertIn("Disallow: /timers/", content)
        self.assertIn("Disallow: /winchallenges/", content)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", content)

    def test_sitemap_contains_only_public_marketing_pages(self):
        response = self.client.get(reverse("sitemap"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        self.assertIn("<loc>http://testserver/</loc>", content)
        self.assertIn("<loc>http://testserver/demo/</loc>", content)
        self.assertIn("<loc>http://testserver/about/</loc>", content)
        self.assertNotIn("/accounts/", content)
        self.assertNotIn("/spotify/", content)

    def test_private_workspace_uses_noindex_and_breadcrumbs(self):
        user = User.objects.create_user(username="private-owner")
        self.client.force_login(user)

        response = self.client.get(reverse("overlay_dashboard"))

        self.assertContains(response, '<meta name="robots" content="noindex, nofollow">')
        self.assertContains(response, 'class="breadcrumbs"')
        self.assertNotContains(response, '<link rel="canonical"')


class AuthenticationAccessibilityTests(TestCase):
    def test_invalid_login_exposes_linked_error_summary(self):
        response = self.client.post(reverse("login"), {"username": "", "password": ""})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="auth-error-summary" role="alert"')
        self.assertContains(response, 'href="#id_username"')
        self.assertContains(response, 'id="id_username_error"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_username_error"')
        self.assertContains(response, "data-error-summary")


class AboutViewTests(TestCase):
    def test_about_page_describes_products_and_links_to_tools(self):
        response = self.client.get(reverse("about"))

        self.assertContains(response, "Tools für Streams mit deiner Handschrift")
        self.assertContains(response, "Drei Tools, ein einheitlicher Workflow")
        dashboard_url = reverse("overlay_dashboard")
        self.assertContains(response, f'href="{dashboard_url}#spotify-overlays"')
        self.assertContains(response, f'href="{dashboard_url}#winchallenge-overlays"')
        self.assertContains(response, f'href="{dashboard_url}#timer-overlays"')

    def test_about_page_is_available_in_english(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

        response = self.client.get(reverse("about"))
        content = response.content.decode()

        self.assertContains(response, "Tools for streams that feel like yours")
        self.assertContains(response, "Made to stay out of your way")
        self.assertIn('<html lang="en">', content)


class OverlayDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="list-owner")
        self.client.force_login(self.user)

    def test_empty_dashboard_shows_all_overlay_categories(self):
        response = self.client.get(reverse("overlay_dashboard"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="spotify-overlays"')
        self.assertContains(response, 'id="winchallenge-overlays"')
        self.assertContains(response, 'id="score-overlays"')
        self.assertContains(response, 'id="timer-overlays"')
        self.assertContains(response, 'class="dashboard-empty"', count=4)
        self.assertEqual(content.count(f'href="{reverse("spotify_create")}"'), 1)
        self.assertEqual(content.count(f'href="{reverse("winchallenge_create")}"'), 1)
        self.assertEqual(content.count(f'href="{reverse("score_create")}"'), 1)
        self.assertEqual(content.count(f'href="{reverse("timer_create")}"'), 1)

    def test_dashboard_shows_saved_overlays_from_all_tools(self):
        spotify_overlay = SpotifyOverlay.objects.create(owner=self.user, name="Stream Music")
        challenge = WinChallenge.objects.create(owner=self.user, title="Road to Diamond")
        score_overlay = ScoreOverlay.objects.create(owner=self.user, name="Match Score")
        timer = TimerOverlay.objects.create(owner=self.user, name="Starting Soon")

        response = self.client.get(reverse("overlay_dashboard"))

        self.assertContains(response, spotify_overlay.display_name)
        self.assertContains(response, challenge.display_title)
        self.assertContains(response, score_overlay.display_name)
        self.assertContains(response, timer.display_name)
        self.assertContains(response, "spotify-dashboard-preview")
        self.assertContains(response, "challenge-dashboard-preview")
        self.assertContains(response, "score-dashboard-preview")
        self.assertContains(response, "timer-dashboard-preview")
        self.assertContains(response, reverse("spotify_duplicate", args=[spotify_overlay.pk]))
        self.assertContains(response, reverse("spotify_export", args=[spotify_overlay.pk]))
        self.assertContains(response, reverse("spotify_renew_obs_link", args=[spotify_overlay.pk]))
        self.assertContains(response, reverse("winchallenge_duplicate", args=[challenge.pk]))
        self.assertContains(response, reverse("winchallenge_export", args=[challenge.pk]))
        self.assertContains(response, reverse("winchallenge_renew_obs_link", args=[challenge.pk]))
        self.assertContains(response, reverse("score_duplicate", args=[score_overlay.pk]))
        self.assertContains(response, reverse("score_export", args=[score_overlay.pk]))
        self.assertContains(response, reverse("score_renew_obs_link", args=[score_overlay.pk]))
        self.assertContains(response, reverse("timer_duplicate", args=[timer.pk]))
        self.assertContains(response, reverse("timer_export", args=[timer.pk]))
        self.assertContains(response, reverse("timer_renew_obs_link", args=[timer.pk]))
        self.assertContains(response, "OBS-Link erneuern", count=4)
        self.assertContains(response, reverse("overlay_import"))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertEqual(response.context["overlay_count"], 4)

    def test_legacy_overview_urls_redirect_to_dashboard_sections(self):
        self.assertRedirects(
            self.client.get(reverse("spotify_list")),
            f"{reverse('overlay_dashboard')}#spotify-overlays",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(reverse("winchallenge_list")),
            f"{reverse('overlay_dashboard')}#winchallenge-overlays",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(reverse("timer_list")),
            f"{reverse('overlay_dashboard')}#timer-overlays",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(reverse("score_list")),
            f"{reverse('overlay_dashboard')}#score-overlays",
            fetch_redirect_response=False,
        )


class OverlayAssetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="asset-owner")
        self.client.force_login(self.user)
        self.media_settings = override_settings(
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.InMemoryStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            }
        )
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)

    def test_branding_asset_selects_render_a_disabled_empty_choice(self):
        editor_forms = (
            WinChallengeCreateForm(asset_owner=self.user),
            SpotifyOverlayForm(asset_owner=self.user),
            ScoreOverlayForm(asset_owner=self.user),
            TimerOverlayForm(asset_owner=self.user),
        )

        for form in editor_forms:
            with self.subTest(form=form.__class__.__name__):
                for field_name in ("font_asset", "logo_asset", "background_asset"):
                    field = form.fields[field_name]
                    choices = list(field.widget.choices)

                    self.assertEqual(len(choices), 1)
                    self.assertEqual(choices[0][0], "")
                    self.assertTrue(str(choices[0][1]))
                    self.assertTrue(field.widget.attrs["disabled"])
                    self.assertEqual(field.widget.attrs["aria-disabled"], "true")

    def test_branding_asset_select_is_enabled_when_matching_assets_exist(self):
        image = OverlayAsset.objects.create(
            owner=self.user,
            name="Available logo",
            kind=OverlayAsset.KIND_IMAGE,
            file="overlay-assets/available/logo.png",
        )
        form = SpotifyOverlayForm(asset_owner=self.user)

        for field_name in ("logo_asset", "background_asset"):
            field = form.fields[field_name]
            choice_values = [str(value) for value, _label in field.widget.choices]

            self.assertNotIn("disabled", field.widget.attrs)
            self.assertEqual(choice_values, ["", str(image.pk)])

    def test_valid_image_and_font_uploads_are_private_to_the_owner(self):
        image_response = self.client.post(
            reverse("overlay_asset_upload"),
            {
                "asset-name": "Channel logo",
                "asset-kind": OverlayAsset.KIND_IMAGE,
                "asset-file": uploaded_png(),
                "next": reverse("spotify_create"),
            },
        )
        font_response = self.client.post(
            reverse("overlay_asset_upload"),
            {
                "asset-name": "Stream font",
                "asset-kind": OverlayAsset.KIND_FONT,
                "asset-file": SimpleUploadedFile(
                    "stream.woff2",
                    b"wOF2" + (b"\0" * 64),
                    content_type="font/woff2",
                ),
                "next": reverse("timer_create"),
            },
        )

        self.assertRedirects(image_response, reverse("spotify_create"))
        self.assertRedirects(font_response, reverse("timer_create"))
        self.assertEqual(
            set(OverlayAsset.objects.values_list("owner", "kind")),
            {
                (self.user.pk, OverlayAsset.KIND_IMAGE),
                (self.user.pk, OverlayAsset.KIND_FONT),
            },
        )

    def test_invalid_or_mismatched_upload_is_rejected(self):
        response = self.client.post(
            reverse("overlay_asset_upload"),
            {
                "asset-name": "Unsafe logo",
                "asset-kind": OverlayAsset.KIND_IMAGE,
                "asset-file": SimpleUploadedFile(
                    "unsafe.svg",
                    b"<svg><script>alert(1)</script></svg>",
                    content_type="image/svg+xml",
                ),
            },
        )

        self.assertRedirects(response, reverse("overlay_dashboard"))
        self.assertFalse(OverlayAsset.objects.exists())

    def test_asset_file_uses_token_url_and_safe_response_headers(self):
        self.client.post(
            reverse("overlay_asset_upload"),
            {
                "asset-name": "OBS logo",
                "asset-kind": OverlayAsset.KIND_IMAGE,
                "asset-file": uploaded_png(),
            },
        )
        asset = OverlayAsset.objects.get()
        self.client.logout()

        response = self.client.get(asset.public_url)
        content = b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(content.startswith(b"\x89PNG"))

    def test_asset_from_another_account_cannot_be_selected(self):
        other_user = User.objects.create_user(username="other-asset-owner")
        foreign_asset = OverlayAsset.objects.create(
            owner=other_user,
            name="Foreign logo",
            kind=OverlayAsset.KIND_IMAGE,
            file="overlay-assets/foreign/logo.png",
        )
        overlay = SpotifyOverlay.objects.create(owner=self.user, name="Owned overlay")
        response = self.client.post(
            reverse("spotify_autosave", args=[overlay.pk]),
            {
                "name": overlay.name,
                "canvas_width": overlay.canvas_width,
                "canvas_height": overlay.canvas_height,
                "background_color": overlay.background_color,
                "background_opacity": overlay.background_opacity,
                "border_color": overlay.border_color,
                "border_width": overlay.border_width,
                "corner_radius": overlay.corner_radius,
                "elements": json.dumps(overlay.elements),
                "logo_asset": foreign_asset.pk,
            },
        )

        overlay.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(overlay.logo_asset)

    def test_uploaded_branding_is_available_in_editor_and_public_state(self):
        self.client.post(
            reverse("overlay_asset_upload"),
            {
                "asset-name": "Public logo",
                "asset-kind": OverlayAsset.KIND_IMAGE,
                "asset-file": uploaded_png(),
            },
        )
        self.client.post(
            reverse("overlay_asset_upload"),
            {
                "asset-name": "Public font",
                "asset-kind": OverlayAsset.KIND_FONT,
                "asset-file": SimpleUploadedFile(
                    "public.woff",
                    b"wOFF" + (b"\0" * 64),
                    content_type="font/woff",
                ),
            },
        )
        logo = OverlayAsset.objects.get(kind=OverlayAsset.KIND_IMAGE)
        font = OverlayAsset.objects.get(kind=OverlayAsset.KIND_FONT)
        overlay = SpotifyOverlay.objects.create(
            owner=self.user,
            name="Branded",
            font_family=SpotifyOverlay.FONT_GEORGIA,
            logo_asset=logo,
            background_asset=logo,
            font_asset=font,
        )

        editor_response = self.client.get(reverse("spotify_manage", args=[overlay.pk]))
        public_response = self.client.get(reverse("spotify_overlay", args=[overlay.public_token]))
        state_response = self.client.get(
            reverse("spotify_overlay_state", args=[overlay.public_token])
        )

        self.assertContains(editor_response, "Public logo")
        self.assertContains(editor_response, "Georgia")
        self.assertContains(editor_response, logo.public_url)
        self.assertContains(editor_response, font.public_url)
        self.assertContains(public_response, logo.public_url)
        self.assertContains(public_response, font.public_url)
        self.assertEqual(state_response.json()["logo_url"], logo.public_url)
        self.assertEqual(
            state_response.json()["background_image_url"],
            logo.public_url,
        )
        self.assertEqual(state_response.json()["font_url"], font.public_url)
        self.assertEqual(
            state_response.json()["font_family"],
            SpotifyOverlay.FONT_GEORGIA,
        )


class OverlayVersionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="version-owner")
        self.client.force_login(self.user)
        self.spotify = SpotifyOverlay.objects.create(owner=self.user, name="Original")

    def spotify_form_data(self, **updates):
        data = {
            field_name: (
                getattr(self.spotify, field_name)
                if getattr(self.spotify, field_name) is not None
                else ""
            )
            for field_name in SpotifyOverlayForm.Meta.fields
        }
        data["elements"] = json.dumps(self.spotify.elements)
        data.update(updates)
        return data

    def test_editor_creates_baseline_and_autosave_keeps_distinct_versions(self):
        manage_response = self.client.get(reverse("spotify_manage", args=[self.spotify.pk]))
        changed_response = self.client.post(
            reverse("spotify_autosave", args=[self.spotify.pk]),
            self.spotify_form_data(name="Changed"),
        )
        duplicate_response = self.client.post(
            reverse("spotify_autosave", args=[self.spotify.pk]),
            self.spotify_form_data(name="Changed"),
        )

        self.assertContains(manage_response, "overlay-version-history")
        self.assertEqual(changed_response.status_code, 200)
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertEqual(overlay_versions.versions_for(self.spotify).count(), 2)

    def test_restore_recovers_overlay_and_branding_state(self):
        logo = OverlayAsset.objects.create(
            owner=self.user,
            name="Logo",
            kind=OverlayAsset.KIND_IMAGE,
            file="overlay-assets/version-owner/logo.png",
        )
        baseline, _ = overlay_versions.record_version(
            self.spotify,
            OverlayVersion.REASON_CREATED,
        )
        self.spotify.name = "Changed"
        self.spotify.font_family = SpotifyOverlay.FONT_GEORGIA
        self.spotify.logo_asset = logo
        self.spotify.save()
        overlay_versions.record_version(self.spotify)

        response = self.client.post(
            reverse(
                "overlay_version_restore",
                args=["spotify", self.spotify.pk, baseline.pk],
            )
        )

        self.spotify.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("spotify_manage", args=[self.spotify.pk]),
        )
        self.assertEqual(self.spotify.name, "Original")
        self.assertEqual(self.spotify.font_family, SpotifyOverlay.FONT_SYSTEM)
        self.assertIsNone(self.spotify.logo_asset)
        self.assertEqual(overlay_versions.versions_for(self.spotify).count(), 3)

    def test_winchallenge_restore_replaces_games(self):
        challenge = WinChallenge.objects.create(owner=self.user, title="First")
        game = WinChallengeGame.objects.create(
            challenge=challenge,
            name="Rocket League",
            wins=0,
            target_wins=3,
        )
        baseline, _ = overlay_versions.record_version(
            challenge,
            OverlayVersion.REASON_CREATED,
        )
        challenge.title = "Changed"
        challenge.save()
        game.wins = 2
        game.save()

        overlay_versions.restore_version(challenge, baseline)
        challenge.refresh_from_db()

        self.assertEqual(challenge.title, "First")
        self.assertEqual(challenge.games.get().wins, 0)

    def test_timer_restore_recovers_duration_and_design(self):
        timer = TimerOverlay.objects.create(
            owner=self.user,
            name="Break",
            duration_seconds=120,
            accent_color="#14b8a6",
        )
        baseline, _ = overlay_versions.record_version(
            timer,
            OverlayVersion.REASON_CREATED,
        )
        timer.duration_seconds = 600
        timer.accent_color = "#ff5500"
        timer.save()

        overlay_versions.restore_version(timer, baseline)
        timer.refresh_from_db()

        self.assertEqual(timer.duration_seconds, 120)
        self.assertEqual(timer.accent_color, "#14b8a6")

    def test_restore_endpoint_rejects_a_version_from_another_account(self):
        other_user = User.objects.create_user(username="other-version-owner")
        other_overlay = SpotifyOverlay.objects.create(owner=other_user, name="Private")
        foreign_version, _ = overlay_versions.record_version(other_overlay)

        response = self.client.post(
            reverse(
                "overlay_version_restore",
                args=["spotify", self.spotify.pk, foreign_version.pk],
            )
        )

        self.assertEqual(response.status_code, 404)
        self.spotify.refresh_from_db()
        self.assertEqual(self.spotify.name, "Original")

    def test_only_the_30_most_recent_distinct_versions_are_retained(self):
        for index in range(35):
            self.spotify.name = f"Version {index}"
            self.spotify.save(update_fields=["name", "updated_at"])
            overlay_versions.record_version(self.spotify)

        versions = overlay_versions.versions_for(self.spotify)
        self.assertEqual(versions.count(), 30)
        self.assertEqual(versions.first().snapshot["payload"]["overlay"]["name"], "Version 34")


class OverlayTransferTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="transfer-owner")
        self.other_user = User.objects.create_user(username="transfer-other")
        self.client.force_login(self.user)
        self.spotify = SpotifyOverlay.objects.create(
            owner=self.user,
            name="Green Room",
            canvas_width=880,
            border_color="#abcdef",
        )
        self.challenge = WinChallenge.objects.create(
            owner=self.user,
            title="Ranked Run",
            design_template=WinChallenge.TEMPLATE_NEON,
            accent_color="#ff8800",
        )
        WinChallengeGame.objects.create(
            challenge=self.challenge,
            name="Rocket League",
            wins=4,
            target_wins=7,
            sort_order=0,
        )

    def test_spotify_duplicate_shares_connection_but_not_public_url(self):
        connection = SpotifyConnection.objects.create(
            owner=self.user,
            access_token="private-access-token",
            refresh_token="private-refresh-token",
        )
        self.spotify.connection = connection
        self.spotify.save(update_fields=["connection"])

        response = self.client.post(reverse("spotify_duplicate", args=[self.spotify.pk]))

        duplicate = SpotifyOverlay.objects.exclude(pk=self.spotify.pk).get(owner=self.user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(duplicate.canvas_width, self.spotify.canvas_width)
        self.assertEqual(duplicate.border_color, self.spotify.border_color)
        self.assertEqual(duplicate.elements, self.spotify.elements)
        self.assertNotEqual(duplicate.public_token, self.spotify.public_token)
        self.assertEqual(duplicate.connection, connection)
        self.assertNotEqual(duplicate.name, self.spotify.name)

    def test_winchallenge_duplicate_copies_design_and_games(self):
        response = self.client.post(reverse("winchallenge_duplicate", args=[self.challenge.pk]))

        duplicate = WinChallenge.objects.exclude(pk=self.challenge.pk).get(owner=self.user)
        duplicate_game = duplicate.games.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(duplicate.design_template, self.challenge.design_template)
        self.assertEqual(duplicate.accent_color, self.challenge.accent_color)
        self.assertNotEqual(duplicate.public_token, self.challenge.public_token)
        self.assertEqual(duplicate_game.name, "Rocket League")
        self.assertEqual(duplicate_game.wins, 4)
        self.assertEqual(duplicate_game.target_wins, 7)

    def test_spotify_export_is_json_and_omits_private_fields(self):
        connection = SpotifyConnection.objects.create(
            owner=self.user,
            access_token="private-access-token",
        )
        self.spotify.connection = connection
        self.spotify.save(update_fields=["connection"])

        response = self.client.get(reverse("spotify_export", args=[self.spotify.pk]))
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(payload["format"], "nexora-overlay")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["type"], "spotify")
        self.assertEqual(payload["overlay"]["name"], "Green Room")
        self.assertNotIn("owner", payload["overlay"])
        self.assertNotIn("public_token", payload["overlay"])
        self.assertNotIn("spotify_access_token", response.content.decode())

    def test_winchallenge_export_contains_ordered_games(self):
        response = self.client.get(reverse("winchallenge_export", args=[self.challenge.pk]))
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["type"], "winchallenge")
        self.assertEqual(payload["overlay"]["title"], "Ranked Run")
        self.assertEqual(
            payload["games"],
            [{"name": "Rocket League", "wins": 4, "target_wins": 7}],
        )

    def test_spotify_export_can_be_imported_as_new_owned_overlay(self):
        export_response = self.client.get(reverse("spotify_export", args=[self.spotify.pk]))
        upload = SimpleUploadedFile(
            "green-room.json",
            export_response.content,
            content_type="application/json",
        )

        response = self.client.post(
            reverse("overlay_import"),
            {"overlay_file": upload},
        )

        imported = SpotifyOverlay.objects.exclude(pk=self.spotify.pk).get(owner=self.user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(imported.name, self.spotify.name)
        self.assertEqual(imported.canvas_width, self.spotify.canvas_width)
        self.assertEqual(imported.elements, self.spotify.elements)
        self.assertNotEqual(imported.public_token, self.spotify.public_token)

    def test_older_export_without_preset_font_remains_importable(self):
        payload = json.loads(
            self.client.get(reverse("spotify_export", args=[self.spotify.pk])).content
        )
        payload["overlay"].pop("font_family")
        upload = SimpleUploadedFile(
            "older-export.json",
            json.dumps(payload).encode(),
            content_type="application/json",
        )

        response = self.client.post(reverse("overlay_import"), {"overlay_file": upload})

        imported = SpotifyOverlay.objects.exclude(pk=self.spotify.pk).get(owner=self.user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(imported.font_family, SpotifyOverlay.FONT_SYSTEM)

    def test_winchallenge_export_can_be_imported_with_games(self):
        export_response = self.client.get(reverse("winchallenge_export", args=[self.challenge.pk]))
        upload = SimpleUploadedFile(
            "ranked-run.json",
            export_response.content,
            content_type="application/json",
        )

        response = self.client.post(
            reverse("overlay_import"),
            {"overlay_file": upload},
        )

        imported = WinChallenge.objects.exclude(pk=self.challenge.pk).get(owner=self.user)
        imported_game = imported.games.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(imported.title, self.challenge.title)
        self.assertEqual(imported.design_template, self.challenge.design_template)
        self.assertEqual(imported_game.name, "Rocket League")
        self.assertEqual(imported_game.wins, 4)

    def test_invalid_or_extended_import_file_is_rejected_without_creating_data(self):
        malformed_upload = SimpleUploadedFile(
            "broken.json",
            b"{not-json",
            content_type="application/json",
        )

        malformed_response = self.client.post(
            reverse("overlay_import"),
            {"overlay_file": malformed_upload},
        )
        self.assertEqual(malformed_response.status_code, 400)
        self.assertContains(
            malformed_response,
            'aria-invalid="true"',
            status_code=400,
        )

        export_payload = json.loads(
            self.client.get(reverse("spotify_export", args=[self.spotify.pk])).content
        )
        export_payload["overlay"]["owner"] = self.other_user.pk
        extended_upload = SimpleUploadedFile(
            "extended.json",
            json.dumps(export_payload).encode(),
            content_type="application/json",
        )
        extended_response = self.client.post(
            reverse("overlay_import"),
            {"overlay_file": extended_upload},
        )

        self.assertEqual(extended_response.status_code, 400)
        self.assertEqual(SpotifyOverlay.objects.filter(owner=self.user).count(), 1)

    def test_transfer_endpoints_reject_foreign_overlays(self):
        foreign_spotify = SpotifyOverlay.objects.create(
            owner=self.other_user,
            name="Private Spotify",
        )
        foreign_challenge = WinChallenge.objects.create(
            owner=self.other_user,
            title="Private Challenge",
        )

        self.assertEqual(
            self.client.post(reverse("spotify_duplicate", args=[foreign_spotify.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("spotify_export", args=[foreign_spotify.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("winchallenge_duplicate", args=[foreign_challenge.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("winchallenge_export", args=[foreign_challenge.pk])
            ).status_code,
            404,
        )


class WinChallengeModelTests(TestCase):
    def test_total_wins_are_calculated_from_games(self):
        challenge = WinChallenge.objects.create(title="Road to Diamond")
        WinChallengeGame.objects.create(
            challenge=challenge, name="Rocket League", wins=4, target_wins=6
        )
        game = WinChallengeGame.objects.create(
            challenge=challenge, name="Valorant", wins=2, target_wins=4
        )

        self.assertEqual(challenge.total_wins, 6)
        self.assertEqual(game.progress_percent, 50)
        self.assertFalse(game.is_complete)

        game.wins = game.target_wins

        self.assertTrue(game.is_complete)


class WinChallengeCreateFormTests(TestCase):
    def test_title_is_optional_and_uses_default_display_title(self):
        challenge = WinChallenge()
        form = WinChallengeCreateForm(
            data={
                "title": "",
                "design_template": WinChallenge.TEMPLATE_GLASS,
                "background_color": challenge.background_color,
                "background_opacity": challenge.background_opacity,
                "text_color": challenge.text_color,
                "accent_color": challenge.accent_color,
                "border_color": challenge.border_color,
                "border_width": challenge.border_width,
                "corner_radius": challenge.corner_radius,
                "padding": challenge.padding,
                "overlay_width": challenge.overlay_width,
                "overlay_height": challenge.overlay_height,
                "label_text_size": challenge.label_text_size,
                "title_text_size": challenge.title_text_size,
                "total_text_size": challenge.total_text_size,
                "game_text_size": challenge.game_text_size,
                "game_score_text_size": challenge.game_score_text_size,
                "pager_text_size": challenge.pager_text_size,
                "page_interval_seconds": challenge.page_interval_seconds,
                "item_spacing": challenge.item_spacing,
                "shadow_enabled": "on",
                "show_games_list": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

        saved_challenge = form.save()
        self.assertEqual(saved_challenge.title, "")
        self.assertEqual(saved_challenge.display_title, "Winchallenge")


class WinChallengeEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="challenge-owner")
        self.client.force_login(self.user)
        self.challenge = WinChallenge.objects.create(owner=self.user, title="Road to Diamond")
        self.game = WinChallengeGame.objects.create(
            challenge=self.challenge,
            name="Rocket League",
            target_wins=3,
        )

    def test_create_page_renders_unsaved_preview(self):
        response = self.client.get(reverse("winchallenge_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-winchallenge-preview")
        self.assertContains(response, "winchallenge-editor-page--create")
        self.assertContains(response, "panel-heading__number", count=2)
        self.assertContains(response, 'placeholder="Winchallenge"')
        self.assertContains(response, "Optional: Standard Winchallenge")
        self.assertContains(response, "data-number-increase-label")
        self.assertContains(response, "data-number-decrease-label")
        self.assertContains(response, "data-editor-state")
        self.assertContains(response, 'data-editor-create="true"')
        self.assertContains(response, "data-editor-state-form")
        self.assertContains(response, "data-editor-undo")
        self.assertContains(response, "data-editor-redo")
        self.assertNotContains(response, "data-autosave-url")

    def test_create_assigns_the_signed_in_user(self):
        candidate = WinChallenge()
        data = {
            field_name: (
                getattr(candidate, field_name) if getattr(candidate, field_name) is not None else ""
            )
            for field_name in WinChallengeCreateForm.Meta.fields
        }
        data.update(
            {
                "title": "Private Challenge",
                "shadow_enabled": "on",
                "show_games_list": "on",
            }
        )

        response = self.client.post(reverse("winchallenge_create"), data)

        created = WinChallenge.objects.get(title="Private Challenge")
        self.assertRedirects(response, reverse("winchallenge_manage", args=[created.pk]))
        self.assertEqual(created.owner, self.user)

    def test_manage_page_uses_the_shared_editor_design(self):
        response = self.client.get(reverse("winchallenge_manage", args=[self.challenge.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "winchallenge-editor-page--manage")
        self.assertContains(response, "editor-panel--surface", count=4)
        self.assertContains(response, "preview-panel--surface")
        self.assertContains(response, '<div class="preview-stage">')
        self.assertContains(response, "data-number-increase-label")
        self.assertContains(response, "data-number-decrease-label")
        self.assertContains(response, "data-editor-state")
        self.assertContains(response, 'data-editor-create="false"')
        self.assertContains(response, "data-editor-state-form", count=2)
        self.assertContains(
            response,
            f'data-autosave-url="{reverse("winchallenge_autosave", args=[self.challenge.pk])}"',
            count=2,
        )

    def test_settings_autosave_updates_title(self):
        response = self.client.post(
            reverse("winchallenge_autosave", args=[self.challenge.pk]),
            {"form_type": "challenge", "title": "Autosaved Challenge"},
        )

        self.challenge.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIn("updated_at", response.json())
        self.assertEqual(self.challenge.title, "Autosaved Challenge")

    def test_design_autosave_updates_design_without_changing_title(self):
        data = {
            field_name: (
                getattr(self.challenge, field_name)
                if getattr(self.challenge, field_name) is not None
                else ""
            )
            for field_name in WinChallengeDesignForm.Meta.fields
        }
        data.update({"form_type": "design", "accent_color": "#ff5500"})

        response = self.client.post(
            reverse("winchallenge_autosave", args=[self.challenge.pk]),
            data,
        )

        self.challenge.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.challenge.accent_color, "#ff5500")
        self.assertEqual(self.challenge.title, "Road to Diamond")

    def test_autosave_rejects_unknown_form(self):
        response = self.client.post(
            reverse("winchallenge_autosave", args=[self.challenge.pk]),
            {"form_type": "games"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_spotify_create_page_renders_visual_editor(self):
        home_response = self.client.get(reverse("home"))
        response = self.client.get(reverse("spotify_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-spotify-editor")
        self.assertContains(response, 'data-add-element="title"')
        self.assertContains(response, 'data-add-element="progress"')
        self.assertContains(response, "data-grid-toggle")
        self.assertContains(response, "data-grid-size")
        self.assertContains(response, 'value="Spotify-Overlay"')
        self.assertContains(home_response, reverse("overlay_dashboard"))

    def test_public_state_exposes_overlay_data_only(self):
        self.challenge.text_size = 20
        self.challenge.item_spacing = 14
        self.challenge.overlay_width = 640
        self.challenge.overlay_height = 360
        self.challenge.label_text_size = 11
        self.challenge.title_text_size = 24
        self.challenge.total_text_size = 16
        self.challenge.game_text_size = 18
        self.challenge.game_score_text_size = 13
        self.challenge.pager_text_size = 12
        self.challenge.page_interval_seconds = 7
        self.challenge.save()

        response = self.client.get(
            reverse("winchallenge_overlay_state", args=[self.challenge.public_token])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "Road to Diamond")
        self.assertEqual(payload["games"][0]["name"], "Rocket League")
        self.assertEqual(payload["games"][0]["target_wins"], 3)
        self.assertFalse(payload["games"][0]["is_complete"])
        self.assertEqual(payload["design"]["overlay_width"], 640)
        self.assertEqual(payload["design"]["overlay_height"], 360)
        self.assertEqual(payload["design"]["text_size"], 20)
        self.assertEqual(payload["design"]["label_text_size"], 11)
        self.assertEqual(payload["design"]["title_text_size"], 24)
        self.assertEqual(payload["design"]["total_text_size"], 16)
        self.assertEqual(payload["design"]["game_text_size"], 18)
        self.assertEqual(payload["design"]["game_score_text_size"], 13)
        self.assertEqual(payload["design"]["pager_text_size"], 12)
        self.assertEqual(payload["design"]["page_interval_seconds"], 7)
        self.assertEqual(payload["design"]["item_spacing"], 14)
        self.assertNotIn("target_wins", payload)
        self.assertNotIn("owner", payload)

    def test_game_win_updates_do_not_go_below_zero(self):
        url = reverse("winchallenge_game_wins", args=[self.challenge.pk, self.game.pk])

        decrement_response = self.client.post(url, {"delta": -1})
        self.game.refresh_from_db()

        self.assertEqual(decrement_response.status_code, 200)
        self.assertEqual(self.game.wins, 0)

        increment_response = self.client.post(url, {"delta": 1})
        self.game.refresh_from_db()

        self.assertEqual(increment_response.status_code, 200)
        self.assertEqual(self.game.wins, 1)

    def test_game_win_updates_do_not_exceed_maximum(self):
        self.game.wins = WinChallengeGame.MAX_WINS - 1
        self.game.save(update_fields=["wins"])
        url = reverse("winchallenge_game_wins", args=[self.challenge.pk, self.game.pk])

        increment_response = self.client.post(url, {"delta": 1})
        capped_response = self.client.post(url, {"delta": 1})
        self.game.refresh_from_db()

        self.assertEqual(increment_response.status_code, 200)
        self.assertEqual(capped_response.status_code, 200)
        self.assertEqual(self.game.wins, WinChallengeGame.MAX_WINS)
        self.assertEqual(
            capped_response.json()["games"][0]["wins"],
            WinChallengeGame.MAX_WINS,
        )

    def test_reaching_target_marks_game_as_complete(self):
        self.game.wins = self.game.target_wins - 1
        self.game.save(update_fields=["wins"])
        url = reverse("winchallenge_game_wins", args=[self.challenge.pk, self.game.pk])

        response = self.client.post(url, {"delta": 1})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["games"][0]["is_complete"])

        manage_response = self.client.get(reverse("winchallenge_manage", args=[self.challenge.pk]))
        self.assertContains(manage_response, 'class="game-row is-complete"')
        self.assertContains(manage_response, 'data-game-complete="true"', count=2)

    def test_game_add_accepts_current_and_target_wins(self):
        url = reverse("winchallenge_game_add", args=[self.challenge.pk])

        response = self.client.post(
            url,
            {"name": "Valorant", "wins": 2, "target_wins": 5},
        )

        self.assertEqual(response.status_code, 200)
        game = WinChallengeGame.objects.get(name="Valorant")
        self.assertEqual(game.wins, 2)
        self.assertEqual(game.target_wins, 5)

    def test_game_add_defaults_missing_current_wins_to_zero(self):
        url = reverse("winchallenge_game_add", args=[self.challenge.pk])

        response = self.client.post(url, {"name": "Trackmania", "target_wins": 4})

        self.assertEqual(response.status_code, 200)
        game = WinChallengeGame.objects.get(name="Trackmania")
        self.assertEqual(game.wins, 0)
        self.assertEqual(game.target_wins, 4)

    def test_game_limit_is_twenty(self):
        WinChallengeGame.objects.bulk_create(
            [
                WinChallengeGame(
                    challenge=self.challenge,
                    name=f"Game {index}",
                    target_wins=1,
                )
                for index in range(19)
            ]
        )
        url = reverse("winchallenge_game_add", args=[self.challenge.pk])

        response = self.client.post(url, {"name": "Too much", "wins": 0, "target_wins": 1})

        self.assertEqual(response.status_code, 400)


class SpotifyOverlayModelTests(TestCase):
    def test_default_overlay_has_starter_elements_and_display_name(self):
        overlay = SpotifyOverlay.objects.create()

        self.assertEqual(overlay.display_name, "Spotify-Overlay")
        self.assertEqual(overlay.canvas_width, 720)
        self.assertEqual(overlay.canvas_height, 220)
        self.assertEqual(overlay.browser_source_width, 800)
        self.assertEqual(overlay.browser_source_height, 316)
        self.assertEqual(overlay.border_color, "#1ed760")
        self.assertEqual(overlay.border_width, 0)
        self.assertEqual(
            {element["type"] for element in overlay.elements},
            {"artwork", "title", "artist", "progress", "elapsed", "duration"},
        )

    def test_spotify_tokens_are_encrypted_in_the_database(self):
        owner = User.objects.create_user(username="encrypted-token-owner")
        connection = SpotifyConnection.objects.create(
            owner=owner,
            access_token="secret-access-token",
            refresh_token="secret-refresh-token",
        )

        with database_connection.cursor() as cursor:
            cursor.execute(
                "SELECT access_token, refresh_token FROM app_spotifyconnection WHERE id = %s",
                [connection.pk],
            )
            stored_access_token, stored_refresh_token = cursor.fetchone()

        self.assertTrue(stored_access_token.startswith("fernet$"))
        self.assertTrue(stored_refresh_token.startswith("fernet$"))
        self.assertNotIn("secret-access-token", stored_access_token)
        self.assertNotIn("secret-refresh-token", stored_refresh_token)

        connection.refresh_from_db()
        self.assertEqual(connection.access_token, "secret-access-token")
        self.assertEqual(connection.refresh_token, "secret-refresh-token")


class SpotifyOverlayFormTests(TestCase):
    def valid_data(self, **overrides):
        overlay = SpotifyOverlay()
        data = {
            "name": "My Spotify",
            "canvas_width": overlay.canvas_width,
            "canvas_height": overlay.canvas_height,
            "background_color": overlay.background_color,
            "background_opacity": overlay.background_opacity,
            "border_color": overlay.border_color,
            "border_width": overlay.border_width,
            "corner_radius": overlay.corner_radius,
            "elements": json.dumps(overlay.elements),
        }
        data.update(overrides)
        return data

    def test_layout_and_element_styles_are_saved(self):
        data = self.valid_data(
            background_color="#336699",
            background_opacity=42,
            border_color="#FF8800",
            border_width=7,
        )
        elements = json.loads(data["elements"])
        elements[1]["font_size"] = 42
        elements[1]["color"] = "#ABCDEF"
        elements[1]["x"] = 310
        data["elements"] = json.dumps(elements)
        form = SpotifyOverlayForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        overlay = form.save()
        title = next(element for element in overlay.elements if element["type"] == "title")
        self.assertEqual(title["font_size"], 42)
        self.assertEqual(title["color"], "#abcdef")
        self.assertEqual(title["x"], 310)
        self.assertEqual(overlay.background_color, "#336699")
        self.assertEqual(overlay.background_opacity, 42)
        self.assertEqual(overlay.border_color, "#FF8800")
        self.assertEqual(overlay.border_width, 7)

    def test_unknown_elements_are_rejected(self):
        data = self.valid_data()
        elements = json.loads(data["elements"])
        elements[0]["type"] = "unsafe-html"
        data["elements"] = json.dumps(elements)
        form = SpotifyOverlayForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("elements", form.errors)


class SpotifyOverlayEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="spotify-owner")
        self.client.force_login(self.user)
        self.overlay = SpotifyOverlay.objects.create(owner=self.user, name="Desk Setup")

    def spotify_form_data(self, **updates):
        data = {
            field_name: (
                getattr(self.overlay, field_name)
                if getattr(self.overlay, field_name) is not None
                else ""
            )
            for field_name in SpotifyOverlayForm.Meta.fields
        }
        data["elements"] = json.dumps(self.overlay.elements)
        data.update(updates)
        return data

    @override_settings(SPOTIFY_CLIENT_ID="client-id", SPOTIFY_CLIENT_SECRET="client-secret")
    def test_list_and_manage_pages_show_saved_overlay(self):
        list_response = self.client.get(reverse("overlay_dashboard"))
        manage_response = self.client.get(reverse("spotify_manage", args=[self.overlay.pk]))

        self.assertContains(list_response, "Desk Setup")
        self.assertContains(manage_response, "data-spotify-editor")
        self.assertContains(manage_response, "spotify-background-settings")
        self.assertContains(manage_response, "data-background-opacity-range")
        self.assertContains(manage_response, "data-background-opacity-value")
        self.assertContains(manage_response, "data-editor-state")
        self.assertContains(manage_response, "data-editor-state-form")
        self.assertContains(manage_response, "data-editor-undo")
        self.assertContains(manage_response, "data-editor-redo")
        self.assertContains(
            manage_response,
            f'data-autosave-url="{reverse("spotify_autosave", args=[self.overlay.pk])}"',
        )
        self.assertContains(manage_response, reverse("spotify_connect", args=[self.overlay.pk]))
        self.assertContains(
            manage_response, reverse("spotify_overlay", args=[self.overlay.public_token])
        )

    def test_create_editor_uses_local_drafts_without_server_autosave(self):
        response = self.client.get(reverse("spotify_create"))

        self.assertContains(response, "data-editor-state")
        self.assertContains(response, 'data-editor-create="true"')
        self.assertContains(response, "data-editor-state-form")
        self.assertNotContains(response, "data-autosave-url")

    def test_autosave_updates_spotify_overlay(self):
        response = self.client.post(
            reverse("spotify_autosave", args=[self.overlay.pk]),
            self.spotify_form_data(name="Autosaved Spotify", canvas_width=840),
        )

        self.overlay.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIn("updated_at", response.json())
        self.assertEqual(self.overlay.name, "Autosaved Spotify")
        self.assertEqual(self.overlay.canvas_width, 840)

    def test_autosave_rejects_invalid_spotify_overlay(self):
        response = self.client.post(
            reverse("spotify_autosave", args=[self.overlay.pk]),
            self.spotify_form_data(canvas_width=100),
        )

        self.overlay.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("canvas_width", response.json()["errors"])
        self.assertEqual(self.overlay.canvas_width, 720)

    def test_create_saves_overlay_and_redirects_to_manage(self):
        candidate = SpotifyOverlay()
        response = self.client.post(
            reverse("spotify_create"),
            {
                "name": "Stream Music",
                "canvas_width": 800,
                "canvas_height": 260,
                "background_color": candidate.background_color,
                "background_opacity": candidate.background_opacity,
                "border_color": "#ff8800",
                "border_width": 6,
                "corner_radius": candidate.corner_radius,
                "elements": json.dumps(candidate.elements),
            },
        )

        created = SpotifyOverlay.objects.get(name="Stream Music")
        self.assertRedirects(response, reverse("spotify_manage", args=[created.pk]))
        self.assertEqual(created.canvas_width, 800)
        self.assertEqual(created.border_color, "#ff8800")
        self.assertEqual(created.border_width, 6)
        self.assertEqual(created.owner, self.user)
        self.assertEqual(created.connection.owner, self.user)

    def test_public_state_does_not_expose_spotify_tokens(self):
        connection = SpotifyConnection.objects.create(
            owner=self.user,
            access_token="secret-access-token",
            refresh_token="secret-refresh-token",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        self.overlay.connection = connection
        self.overlay.save(update_fields=["connection"])

        with patch(
            "app.spotify_api._api_request",
            return_value={
                "is_playing": True,
                "progress_ms": 1000,
                "item": {
                    "type": "track",
                    "name": "Night Drive",
                    "duration_ms": 200000,
                    "artists": [{"name": "Nova"}],
                    "album": {
                        "name": "Lights",
                        "images": [{"url": "https://example.com/cover.jpg"}],
                    },
                },
            },
        ):
            response = self.client.get(
                reverse("spotify_overlay_state", args=[self.overlay.public_token])
            )

        payload = response.json()
        self.assertEqual(payload["playback"]["title"], "Night Drive")
        self.assertEqual(payload["playback"]["artist"], "Nova")
        self.assertEqual(payload["elements"], self.overlay.elements)
        self.assertEqual(payload["browser_source_width"], 800)
        self.assertEqual(payload["browser_source_height"], 316)
        self.assertEqual(payload["background_color"], self.overlay.background_color)
        self.assertEqual(payload["background_opacity"], self.overlay.background_opacity)
        self.assertEqual(payload["border_color"], self.overlay.border_color)
        self.assertEqual(payload["border_width"], self.overlay.border_width)
        self.assertNotIn("spotify_access_token", payload)
        self.assertNotIn("spotify_refresh_token", payload)

    def test_shared_connection_reuses_cached_playback_across_overlays(self):
        connection = SpotifyConnection.objects.create(
            owner=self.user,
            access_token="secret-access-token",
            refresh_token="secret-refresh-token",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        self.overlay.connection = connection
        self.overlay.save(update_fields=["connection"])
        second_overlay = SpotifyOverlay.objects.create(
            owner=self.user,
            connection=connection,
            name="Second layout",
        )
        playback_response = {
            "is_playing": True,
            "progress_ms": 1000,
            "item": {
                "type": "track",
                "name": "Night Drive",
                "duration_ms": 200000,
                "artists": [{"name": "Nova"}],
                "album": {"name": "Lights", "images": []},
            },
        }

        with patch("app.spotify_api._api_request", return_value=playback_response) as api_request:
            first_response = self.client.get(
                reverse("spotify_overlay_state", args=[self.overlay.public_token])
            )
            second_response = self.client.get(
                reverse("spotify_overlay_state", args=[second_overlay.public_token])
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["playback"]["title"], "Night Drive")
        api_request.assert_called_once()

    def test_disconnect_clears_the_shared_connection_for_all_overlays(self):
        connection = SpotifyConnection.objects.create(
            owner=self.user,
            access_token="secret-access-token",
            refresh_token="secret-refresh-token",
        )
        self.overlay.connection = connection
        self.overlay.save(update_fields=["connection"])
        second_overlay = SpotifyOverlay.objects.create(
            owner=self.user,
            connection=connection,
            name="Second layout",
        )

        response = self.client.post(reverse("spotify_disconnect", args=[self.overlay.pk]))
        connection.refresh_from_db()
        self.overlay.refresh_from_db()
        second_overlay.refresh_from_db()

        self.assertRedirects(response, reverse("spotify_manage", args=[self.overlay.pk]))
        self.assertFalse(connection.is_connected)
        self.assertFalse(self.overlay.is_spotify_connected)
        self.assertFalse(second_overlay.is_spotify_connected)

    @override_settings(
        SPOTIFY_CLIENT_ID="client-id",
        SPOTIFY_CLIENT_SECRET="client-secret",
        SPOTIFY_REDIRECT_URI="http://testserver/spotify/callback/",
    )
    def test_connect_starts_authorization_code_flow_with_state(self):
        response = self.client.get(reverse("spotify_connect", args=[self.overlay.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://accounts.spotify.com/authorize?"))
        self.assertIn("user-read-currently-playing", response.url)
        self.assertEqual(self.client.session["spotify_oauth"]["overlay_id"], self.overlay.pk)

    @override_settings(
        SPOTIFY_CLIENT_ID="client-id",
        SPOTIFY_CLIENT_SECRET="client-secret",
        SPOTIFY_REDIRECT_URI="http://testserver/spotify/callback/",
    )
    @patch("app.views.spotify_api.exchange_authorization_code")
    def test_callback_connects_the_overlay_after_state_validation(self, exchange):
        session = self.client.session
        session["spotify_oauth"] = {"state": "secure-state", "overlay_id": self.overlay.pk}
        session.save()

        response = self.client.get(
            reverse("spotify_callback"),
            {"state": "secure-state", "code": "authorization-code"},
        )

        self.assertRedirects(response, reverse("spotify_manage", args=[self.overlay.pk]))
        exchange.assert_called_once()


class TimerOverlayModelAndFormTests(TestCase):
    def test_countdown_uses_persisted_elapsed_time(self):
        started_at = timezone.now() - timedelta(seconds=12)
        timer = TimerOverlay(
            duration_seconds=60,
            accumulated_seconds=8,
            is_running=True,
            started_at=started_at,
        )

        self.assertEqual(timer.elapsed_seconds(), 20)
        self.assertEqual(timer.display_seconds(), 40)
        self.assertEqual(timer.formatted_time(), "00:40")

    def test_stopwatch_counts_up(self):
        timer = TimerOverlay(
            mode=TimerOverlay.MODE_STOPWATCH,
            accumulated_seconds=65,
        )

        self.assertEqual(timer.display_seconds(), 65)
        self.assertEqual(timer.formatted_time(), "01:05")

    def test_form_combines_duration_fields(self):
        timer = TimerOverlay()
        data = {
            "name": "Break Timer",
            "label": "Back in",
            "mode": TimerOverlay.MODE_COUNTDOWN,
            "duration_hours": 1,
            "duration_minutes": 2,
            "duration_seconds_part": 3,
            "design_template": timer.design_template,
            "background_color": timer.background_color,
            "background_opacity": timer.background_opacity,
            "text_color": timer.text_color,
            "accent_color": timer.accent_color,
            "border_color": timer.border_color,
            "border_width": timer.border_width,
            "corner_radius": timer.corner_radius,
            "overlay_width": timer.overlay_width,
            "overlay_height": timer.overlay_height,
            "label_text_size": timer.label_text_size,
            "timer_text_size": timer.timer_text_size,
            "show_progress": True,
            "shadow_enabled": True,
        }
        form = TimerOverlayForm(data=data, instance=timer)

        self.assertTrue(form.is_valid(), form.errors)
        saved_timer = form.save()
        self.assertEqual(saved_timer.duration_seconds, 3723)

    def test_form_rejects_zero_duration(self):
        timer = TimerOverlay()
        data = {
            "name": "Timer",
            "label": "",
            "mode": TimerOverlay.MODE_COUNTDOWN,
            "duration_hours": 0,
            "duration_minutes": 0,
            "duration_seconds_part": 0,
            "design_template": timer.design_template,
            "background_color": timer.background_color,
            "background_opacity": timer.background_opacity,
            "text_color": timer.text_color,
            "accent_color": timer.accent_color,
            "border_color": timer.border_color,
            "border_width": timer.border_width,
            "corner_radius": timer.corner_radius,
            "overlay_width": timer.overlay_width,
            "overlay_height": timer.overlay_height,
            "label_text_size": timer.label_text_size,
            "timer_text_size": timer.timer_text_size,
        }
        form = TimerOverlayForm(data=data, instance=timer)

        self.assertFalse(form.is_valid())
        self.assertIn("duration_seconds_part", form.errors)


class TimerOverlayEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="timer-owner")
        self.client.force_login(self.user)
        self.timer = TimerOverlay.objects.create(
            owner=self.user,
            name="Starting Soon",
            label="Live in",
            duration_seconds=300,
        )

    def timer_form_data(self, **updates):
        hours, remainder = divmod(self.timer.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        data = {
            "name": self.timer.name,
            "label": self.timer.label,
            "mode": self.timer.mode,
            "duration_hours": hours,
            "duration_minutes": minutes,
            "duration_seconds_part": seconds,
            "design_template": self.timer.design_template,
            "background_color": self.timer.background_color,
            "background_opacity": self.timer.background_opacity,
            "text_color": self.timer.text_color,
            "accent_color": self.timer.accent_color,
            "border_color": self.timer.border_color,
            "border_width": self.timer.border_width,
            "corner_radius": self.timer.corner_radius,
            "overlay_width": self.timer.overlay_width,
            "overlay_height": self.timer.overlay_height,
            "label_text_size": self.timer.label_text_size,
            "timer_text_size": self.timer.timer_text_size,
            "show_progress": self.timer.show_progress,
            "shadow_enabled": self.timer.shadow_enabled,
        }
        data.update(updates)
        return data

    def test_manage_page_contains_editor_controls_and_obs_url(self):
        response = self.client.get(reverse("timer_manage", args=[self.timer.pk]))

        self.assertContains(response, "data-timer-editor")
        self.assertContains(response, "data-timer-controls")
        self.assertContains(response, 'data-timer-action="start"')
        self.assertContains(response, reverse("timer_overlay", args=[self.timer.public_token]))
        self.assertContains(response, "data-editor-state")
        self.assertContains(response, reverse("timer_autosave", args=[self.timer.pk]))

    def test_autosave_updates_timer_design_and_duration(self):
        response = self.client.post(
            reverse("timer_autosave", args=[self.timer.pk]),
            self.timer_form_data(
                duration_minutes=10,
                accent_color="#ff8800",
                timer_text_size=92,
            ),
        )

        self.timer.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.timer.duration_seconds, 600)
        self.assertEqual(self.timer.accent_color, "#ff8800")
        self.assertEqual(self.timer.timer_text_size, 92)

    def test_start_pause_and_reset_persist_timer_state(self):
        start_time = timezone.now()
        with (
            patch("app.views.timezone.now", return_value=start_time),
            patch("app.models.timezone.now", return_value=start_time),
        ):
            start_response = self.client.post(
                reverse("timer_control", args=[self.timer.pk]),
                {"action": "start"},
            )

        self.timer.refresh_from_db()
        self.assertEqual(start_response.status_code, 200)
        self.assertTrue(self.timer.is_running)
        self.assertEqual(self.timer.started_at, start_time)

        pause_time = start_time + timedelta(seconds=9)
        with (
            patch("app.views.timezone.now", return_value=pause_time),
            patch("app.models.timezone.now", return_value=pause_time),
        ):
            pause_response = self.client.post(
                reverse("timer_control", args=[self.timer.pk]),
                {"action": "pause"},
            )

        self.timer.refresh_from_db()
        self.assertEqual(pause_response.status_code, 200)
        self.assertFalse(self.timer.is_running)
        self.assertEqual(self.timer.accumulated_seconds, 9)

        reset_response = self.client.post(
            reverse("timer_control", args=[self.timer.pk]),
            {"action": "reset"},
        )
        self.timer.refresh_from_db()
        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(self.timer.accumulated_seconds, 0)
        self.assertIsNone(self.timer.started_at)

    def test_public_state_does_not_expose_owner_or_public_token(self):
        self.client.logout()
        response = self.client.get(reverse("timer_overlay_state", args=[self.timer.public_token]))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], TimerOverlay.MODE_COUNTDOWN)
        self.assertEqual(payload["display_seconds"], 300)
        self.assertIn("design", payload)
        self.assertNotIn("owner", payload)
        self.assertNotIn("public_token", payload)

    def test_duplicate_and_transfer_reset_runtime_state(self):
        self.timer.accumulated_seconds = 42
        self.timer.started_at = timezone.now()
        self.timer.is_running = True
        self.timer.save()

        duplicate_response = self.client.post(reverse("timer_duplicate", args=[self.timer.pk]))
        duplicate = TimerOverlay.objects.exclude(pk=self.timer.pk).get()

        self.assertRedirects(
            duplicate_response,
            f"{reverse('overlay_dashboard')}#timer-overlays",
            fetch_redirect_response=False,
        )
        self.assertEqual(duplicate.duration_seconds, self.timer.duration_seconds)
        self.assertEqual(duplicate.accumulated_seconds, 0)
        self.assertFalse(duplicate.is_running)
        self.assertNotEqual(duplicate.public_token, self.timer.public_token)

        export_response = self.client.get(reverse("timer_export", args=[self.timer.pk]))
        payload = json.loads(export_response.content)
        self.assertEqual(payload["type"], "timer")
        self.assertNotIn("started_at", payload["overlay"])
        self.assertNotIn("is_running", payload["overlay"])

        upload = SimpleUploadedFile(
            "timer.json",
            json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        import_response = self.client.post(reverse("overlay_import"), {"overlay_file": upload})
        imported = TimerOverlay.objects.filter(name=self.timer.name).exclude(pk=self.timer.pk).get()
        self.assertRedirects(
            import_response,
            f"{reverse('overlay_dashboard')}#timer-overlays",
            fetch_redirect_response=False,
        )
        self.assertEqual(imported.duration_seconds, self.timer.duration_seconds)
        self.assertFalse(imported.is_running)
        self.assertEqual(imported.accumulated_seconds, 0)

    def test_create_assigns_signed_in_owner(self):
        self.timer.delete()
        candidate = TimerOverlay()
        data = self.timer_form_data(name="Break", duration_minutes=2)
        response = self.client.post(reverse("timer_create"), data)

        created = TimerOverlay.objects.get(name="Break")
        self.assertRedirects(response, reverse("timer_manage", args=[created.pk]))
        self.assertEqual(created.owner, self.user)
        self.assertEqual(created.duration_seconds, 120)
        self.assertEqual(created.accent_color, candidate.accent_color)


class ScoreOverlayEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="score-owner")
        self.client.force_login(self.user)
        self.overlay = ScoreOverlay.objects.create(owner=self.user, name="Finals")
        self.player_one = ScoreParticipant.objects.create(
            overlay=self.overlay,
            name="Alice",
            accent_color="#38bdf8",
            sort_order=0,
        )
        self.player_two = ScoreParticipant.objects.create(
            overlay=self.overlay,
            name="Bob",
            accent_color="#fb7185",
            sort_order=1,
        )
        self.overlay.elements = [
            {
                "id": f"participant-{self.player_one.public_id}-name",
                "type": "participant_name",
                "participant_id": str(self.player_one.public_id),
                "x": 20,
                "y": 20,
                "width": 180,
                "height": 32,
                "font_size": 20,
                "color": "#ffffff",
                "background_color": "#111827",
                "border_radius": 8,
                "text_align": "left",
            },
            {
                "id": f"participant-{self.player_one.public_id}-score",
                "type": "participant_score",
                "participant_id": str(self.player_one.public_id),
                "x": 220,
                "y": 20,
                "width": 90,
                "height": 50,
                "font_size": 38,
                "color": "#ffffff",
                "background_color": "#38bdf8",
                "border_radius": 12,
                "text_align": "center",
            },
        ]
        self.overlay.save()

    def score_form_data(self, **updates):
        data = {
            "name": self.overlay.name,
            "canvas_width": self.overlay.canvas_width,
            "canvas_height": self.overlay.canvas_height,
            "background_color": self.overlay.background_color,
            "background_opacity": self.overlay.background_opacity,
            "border_color": self.overlay.border_color,
            "border_width": self.overlay.border_width,
            "corner_radius": self.overlay.corner_radius,
            "elements": json.dumps(self.overlay.elements),
            "font_family": self.overlay.font_family,
        }
        if self.overlay.allow_negative_scores:
            data["allow_negative_scores"] = "on"
        data.update(updates)
        return data

    def test_create_starts_with_two_zero_score_participants(self):
        candidate = ScoreOverlay()
        response = self.client.post(
            reverse("score_create"),
            {
                "name": "Grand Final",
                "player_one_name": "Team Blue",
                "player_two_name": "Team Red",
                "canvas_width": candidate.canvas_width,
                "canvas_height": candidate.canvas_height,
                "background_color": candidate.background_color,
                "background_opacity": candidate.background_opacity,
                "border_color": candidate.border_color,
                "border_width": candidate.border_width,
                "corner_radius": candidate.corner_radius,
                "elements": json.dumps(candidate.elements),
                "font_family": candidate.font_family,
            },
        )

        created = ScoreOverlay.objects.get(name="Grand Final")
        participants = list(created.ordered_participants)
        self.assertRedirects(response, reverse("score_manage", args=[created.pk]))
        self.assertEqual(created.owner, self.user)
        self.assertEqual([participant.name for participant in participants], ["Team Blue", "Team Red"])
        self.assertEqual([participant.score for participant in participants], [0, 0])
        self.assertEqual(len(created.elements), 6)

    def test_manage_page_contains_canvas_controls_and_obs_url(self):
        response = self.client.get(reverse("score_manage", args=[self.overlay.pk]))

        self.assertContains(response, "data-score-editor")
        self.assertContains(response, "data-layout-template=\"duel\"")
        self.assertContains(response, reverse("score_overlay", args=[self.overlay.public_token]))
        self.assertContains(response, "data-editor-state")
        self.assertContains(response, reverse("score_autosave", args=[self.overlay.pk]))

    def test_autosave_updates_canvas_design_and_elements(self):
        response = self.client.post(
            reverse("score_autosave", args=[self.overlay.pk]),
            self.score_form_data(
                canvas_width=1120,
                border_color="#22c55e",
                elements=json.dumps(
                    [
                        {
                            **self.overlay.elements[0],
                            "x": 44,
                            "font_size": 24,
                            "text_align": "center",
                        }
                    ]
                ),
            ),
        )

        self.overlay.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.overlay.canvas_width, 1120)
        self.assertEqual(self.overlay.border_color, "#22c55e")
        self.assertEqual(self.overlay.elements[0]["x"], 44)
        self.assertEqual(self.overlay.elements[0]["text_align"], "center")

    def test_score_buttons_respect_negative_score_setting(self):
        decrease_response = self.client.post(
            reverse(
                "score_participant_score",
                args=[self.overlay.pk, self.player_one.public_id],
            ),
            {"delta": -1},
        )
        self.player_one.refresh_from_db()
        self.assertEqual(decrease_response.status_code, 200)
        self.assertEqual(self.player_one.score, 0)

        increase_response = self.client.post(
            reverse(
                "score_participant_score",
                args=[self.overlay.pk, self.player_one.public_id],
            ),
            {"delta": 1},
        )
        self.player_one.refresh_from_db()
        self.assertEqual(increase_response.status_code, 200)
        self.assertEqual(self.player_one.score, 1)

        self.overlay.allow_negative_scores = True
        self.overlay.save(update_fields=["allow_negative_scores", "updated_at"])
        self.player_one.score = 0
        self.player_one.save(update_fields=["score"])
        self.client.post(
            reverse(
                "score_participant_score",
                args=[self.overlay.pk, self.player_one.public_id],
            ),
            {"delta": -1},
        )
        self.player_one.refresh_from_db()
        self.assertEqual(self.player_one.score, -1)

    def test_participant_add_delete_and_reset_return_public_state(self):
        add_response = self.client.post(
            reverse("score_participant_add", args=[self.overlay.pk]),
            {
                "name": "Carol",
                "accent_color": "#22c55e",
                "image_asset": "",
            },
        )
        created = ScoreParticipant.objects.get(name="Carol")
        self.assertEqual(add_response.status_code, 200)
        self.assertIn(str(created.public_id), json.dumps(add_response.json()["elements"]))

        reset_response = self.client.post(reverse("score_reset_all", args=[self.overlay.pk]))
        self.assertEqual(reset_response.status_code, 200)
        self.assertTrue(
            all(participant["score"] == 0 for participant in reset_response.json()["participants"])
        )

        delete_response = self.client.post(
            reverse("score_participant_delete", args=[self.overlay.pk, created.public_id])
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(ScoreParticipant.objects.filter(pk=created.pk).exists())

    def test_public_state_does_not_expose_owner_or_public_token(self):
        self.client.logout()
        response = self.client.get(reverse("score_overlay_state", args=[self.overlay.public_token]))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["name"], "Finals")
        self.assertIn("participants", payload)
        self.assertEqual(payload["participants"][0]["name"], "Alice")
        self.assertNotIn("owner", payload)
        self.assertNotIn("public_token", payload)

    def test_duplicate_and_transfer_preserve_scores_with_new_participant_ids(self):
        self.player_one.score = 3
        self.player_one.save(update_fields=["score"])

        duplicate_response = self.client.post(reverse("score_duplicate", args=[self.overlay.pk]))
        duplicate = ScoreOverlay.objects.exclude(pk=self.overlay.pk).get()

        self.assertRedirects(
            duplicate_response,
            f"{reverse('overlay_dashboard')}#score-overlays",
            fetch_redirect_response=False,
        )
        self.assertEqual(duplicate.participants.count(), 2)
        self.assertEqual(duplicate.participants.get(name="Alice").score, 3)
        self.assertNotEqual(
            set(duplicate.participants.values_list("public_id", flat=True)),
            set(self.overlay.participants.values_list("public_id", flat=True)),
        )

        export_response = self.client.get(reverse("score_export", args=[self.overlay.pk]))
        payload = json.loads(export_response.content)
        self.assertEqual(payload["type"], "score")
        self.assertEqual(payload["participants"][0]["score"], 3)

        upload = SimpleUploadedFile(
            "score.json",
            json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        import_response = self.client.post(reverse("overlay_import"), {"overlay_file": upload})
        self.assertRedirects(
            import_response,
            f"{reverse('overlay_dashboard')}#score-overlays",
            fetch_redirect_response=False,
        )
        self.assertEqual(ScoreOverlay.objects.filter(name=self.overlay.name).count(), 2)


class PublicStateConditionalRequestTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="conditional-state-owner")
        self.timer = TimerOverlay.objects.create(owner=owner)
        self.state_urls = (
            reverse(
                "spotify_overlay_state",
                args=[SpotifyOverlay.objects.create(owner=owner).public_token],
            ),
            reverse(
                "timer_overlay_state",
                args=[self.timer.public_token],
            ),
            reverse(
                "score_overlay_state",
                args=[ScoreOverlay.objects.create(owner=owner).public_token],
            ),
            reverse(
                "winchallenge_overlay_state",
                args=[WinChallenge.objects.create(owner=owner).public_token],
            ),
        )

    def test_unchanged_public_states_return_not_modified(self):
        for state_url in self.state_urls:
            with self.subTest(state_url=state_url):
                first_response = self.client.get(state_url)
                conditional_response = self.client.get(
                    state_url,
                    HTTP_IF_NONE_MATCH=first_response["ETag"],
                )

                self.assertEqual(first_response.status_code, 200)
                self.assertEqual(conditional_response.status_code, 304)
                self.assertEqual(conditional_response.content, b"")

    def test_changed_state_invalidates_the_previous_etag(self):
        state_url = reverse("timer_overlay_state", args=[self.timer.public_token])
        first_response = self.client.get(state_url)
        self.timer.label = "Updated label"
        self.timer.save(update_fields=["label", "updated_at"])

        changed_response = self.client.get(
            state_url,
            HTTP_IF_NONE_MATCH=first_response["ETag"],
        )

        self.assertEqual(changed_response.status_code, 200)
        self.assertNotEqual(changed_response["ETag"], first_response["ETag"])
        self.assertEqual(changed_response.json()["label"], "Updated label")


class PublicOBSLinkRotationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="rotation-owner")
        self.other_user = User.objects.create_user(username="rotation-other")
        self.client.force_login(self.owner)
        self.overlays = (
            (
                SpotifyOverlay.objects.create(owner=self.owner, name="Spotify"),
                "spotify_renew_obs_link",
                "spotify_overlay",
                "spotify_overlay_state",
            ),
            (
                TimerOverlay.objects.create(owner=self.owner, name="Timer"),
                "timer_renew_obs_link",
                "timer_overlay",
                "timer_overlay_state",
            ),
            (
                ScoreOverlay.objects.create(owner=self.owner, name="Score"),
                "score_renew_obs_link",
                "score_overlay",
                "score_overlay_state",
            ),
            (
                WinChallenge.objects.create(owner=self.owner, title="Challenge"),
                "winchallenge_renew_obs_link",
                "winchallenge_overlay",
                "winchallenge_overlay_state",
            ),
        )

    def test_owner_can_renew_and_revoke_each_public_obs_link(self):
        for overlay, renew_url_name, public_url_name, state_url_name in self.overlays:
            with self.subTest(overlay=overlay):
                previous_token = overlay.public_token

                response = self.client.post(
                    reverse(renew_url_name, args=[overlay.pk]),
                )
                overlay.refresh_from_db()

                self.assertRedirects(response, reverse("overlay_dashboard"))
                self.assertNotEqual(overlay.public_token, previous_token)
                self.assertEqual(
                    self.client.get(reverse(public_url_name, args=[previous_token])).status_code,
                    404,
                )
                self.assertEqual(
                    self.client.get(reverse(state_url_name, args=[previous_token])).status_code,
                    404,
                )
                self.assertEqual(
                    self.client.get(
                        reverse(public_url_name, args=[overlay.public_token])
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    self.client.get(
                        reverse(state_url_name, args=[overlay.public_token])
                    ).status_code,
                    200,
                )

    def test_renewing_a_public_obs_link_requires_post(self):
        for overlay, renew_url_name, _public_url_name, _state_url_name in self.overlays:
            with self.subTest(overlay=overlay):
                previous_token = overlay.public_token

                response = self.client.get(reverse(renew_url_name, args=[overlay.pk]))
                overlay.refresh_from_db()

                self.assertEqual(response.status_code, 405)
                self.assertEqual(overlay.public_token, previous_token)

    def test_users_cannot_renew_foreign_public_obs_links(self):
        foreign_overlays = (
            (
                SpotifyOverlay.objects.create(owner=self.other_user, name="Foreign Spotify"),
                "spotify_renew_obs_link",
            ),
            (
                TimerOverlay.objects.create(owner=self.other_user, name="Foreign Timer"),
                "timer_renew_obs_link",
            ),
            (
                ScoreOverlay.objects.create(owner=self.other_user, name="Foreign Score"),
                "score_renew_obs_link",
            ),
            (
                WinChallenge.objects.create(owner=self.other_user, title="Foreign Challenge"),
                "winchallenge_renew_obs_link",
            ),
        )

        for overlay, renew_url_name in foreign_overlays:
            with self.subTest(overlay=overlay):
                previous_token = overlay.public_token

                response = self.client.post(reverse(renew_url_name, args=[overlay.pk]))
                overlay.refresh_from_db()

                self.assertEqual(response.status_code, 404)
                self.assertEqual(overlay.public_token, previous_token)


class AccessControlTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner")
        self.other_user = User.objects.create_user(username="other")
        self.owner_challenge = WinChallenge.objects.create(
            owner=self.owner, title="Owner Challenge"
        )
        self.foreign_challenge = WinChallenge.objects.create(
            owner=self.other_user, title="Foreign Challenge"
        )
        self.foreign_game = WinChallengeGame.objects.create(
            challenge=self.foreign_challenge,
            name="Private Game",
        )
        self.owner_spotify = SpotifyOverlay.objects.create(owner=self.owner, name="Owner Spotify")
        self.foreign_spotify = SpotifyOverlay.objects.create(
            owner=self.other_user, name="Foreign Spotify"
        )
        self.owner_score = ScoreOverlay.objects.create(owner=self.owner, name="Owner Score")
        self.foreign_score = ScoreOverlay.objects.create(
            owner=self.other_user, name="Foreign Score"
        )
        self.owner_timer = TimerOverlay.objects.create(owner=self.owner, name="Owner Timer")
        self.foreign_timer = TimerOverlay.objects.create(
            owner=self.other_user, name="Foreign Timer"
        )

    def test_management_pages_redirect_anonymous_users_to_login(self):
        protected_urls = (
            reverse("overlay_dashboard"),
            reverse("overlay_import"),
            reverse("spotify_list"),
            reverse("spotify_create"),
            reverse("spotify_autosave", args=[self.owner_spotify.pk]),
            reverse("spotify_duplicate", args=[self.owner_spotify.pk]),
            reverse("spotify_export", args=[self.owner_spotify.pk]),
            reverse("spotify_renew_obs_link", args=[self.owner_spotify.pk]),
            reverse("score_list"),
            reverse("score_create"),
            reverse("score_autosave", args=[self.owner_score.pk]),
            reverse("score_duplicate", args=[self.owner_score.pk]),
            reverse("score_export", args=[self.owner_score.pk]),
            reverse("score_renew_obs_link", args=[self.owner_score.pk]),
            reverse("timer_list"),
            reverse("timer_create"),
            reverse("timer_autosave", args=[self.owner_timer.pk]),
            reverse("timer_control", args=[self.owner_timer.pk]),
            reverse("timer_duplicate", args=[self.owner_timer.pk]),
            reverse("timer_export", args=[self.owner_timer.pk]),
            reverse("timer_renew_obs_link", args=[self.owner_timer.pk]),
            reverse("winchallenge_list"),
            reverse("winchallenge_create"),
            reverse("winchallenge_autosave", args=[self.owner_challenge.pk]),
            reverse("winchallenge_duplicate", args=[self.owner_challenge.pk]),
            reverse("winchallenge_export", args=[self.owner_challenge.pk]),
            reverse("winchallenge_renew_obs_link", args=[self.owner_challenge.pk]),
        )

        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_users_only_see_and_manage_their_own_overlays(self):
        self.client.force_login(self.owner)

        dashboard = self.client.get(reverse("overlay_dashboard"))

        self.assertContains(dashboard, self.owner_spotify.name)
        self.assertNotContains(dashboard, self.foreign_spotify.name)
        self.assertContains(dashboard, self.owner_score.name)
        self.assertNotContains(dashboard, self.foreign_score.name)
        self.assertContains(dashboard, self.owner_challenge.title)
        self.assertNotContains(dashboard, self.foreign_challenge.title)
        self.assertContains(dashboard, self.owner_timer.name)
        self.assertNotContains(dashboard, self.foreign_timer.name)
        self.assertEqual(
            self.client.get(reverse("spotify_manage", args=[self.foreign_spotify.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("score_manage", args=[self.foreign_score.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("winchallenge_manage", args=[self.foreign_challenge.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("timer_manage", args=[self.foreign_timer.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("spotify_autosave", args=[self.foreign_spotify.pk]),
                {},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("score_autosave", args=[self.foreign_score.pk]),
                {},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("winchallenge_autosave", args=[self.foreign_challenge.pk]),
                {"form_type": "challenge", "title": "No access"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("timer_control", args=[self.foreign_timer.pk]),
                {"action": "start"},
            ).status_code,
            404,
        )

    def test_foreign_game_updates_are_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "winchallenge_game_wins",
                args=[self.foreign_challenge.pk, self.foreign_game.pk],
            ),
            {"delta": 1},
        )

        self.assertEqual(response.status_code, 404)
        self.foreign_game.refresh_from_db()
        self.assertEqual(self.foreign_game.wins, 0)

    def test_logout_ends_access_to_management_pages(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        protected_response = self.client.get(reverse("overlay_dashboard"))
        self.assertRedirects(
            protected_response,
            f"{reverse('login')}?next={reverse('overlay_dashboard')}",
        )

    def test_public_obs_views_remain_available_without_login(self):
        spotify_response = self.client.get(
            reverse("spotify_overlay", args=[self.owner_spotify.public_token])
        )
        score_response = self.client.get(
            reverse("score_overlay", args=[self.owner_score.public_token])
        )
        challenge_response = self.client.get(
            reverse("winchallenge_overlay", args=[self.owner_challenge.public_token])
        )
        timer_response = self.client.get(
            reverse("timer_overlay", args=[self.owner_timer.public_token])
        )

        self.assertEqual(spotify_response.status_code, 200)
        self.assertEqual(score_response.status_code, 200)
        self.assertEqual(challenge_response.status_code, 200)
        self.assertEqual(timer_response.status_code, 200)
        self.assertContains(spotify_response, "js/polling.js")
        self.assertContains(score_response, "js/polling.js")
        self.assertContains(challenge_response, "js/polling.js")
        self.assertContains(timer_response, "js/polling.js")


class SignUpTests(TestCase):
    def test_password_error_is_connected_to_its_input(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "accessible-user",
                "password1": "Strong-Password-2026!",
                "password2": "Different-Password-2026!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_password2_error"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(
            response,
            'aria-describedby="id_password2_helptext id_password2_error"',
        )

    def test_first_account_claims_existing_unowned_overlays(self):
        challenge = WinChallenge.objects.create(title="Existing Challenge")
        spotify = SpotifyOverlay.objects.create(name="Existing Spotify")
        score = ScoreOverlay.objects.create(name="Existing Score")
        timer = TimerOverlay.objects.create(name="Existing Timer")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "first-owner",
                "password1": "Strong-Password-2026!",
                "password2": "Strong-Password-2026!",
            },
        )

        user = User.objects.get(username="first-owner")
        challenge.refresh_from_db()
        spotify.refresh_from_db()
        score.refresh_from_db()
        timer.refresh_from_db()
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(challenge.owner, user)
        self.assertEqual(spotify.owner, user)
        self.assertEqual(score.owner, user)
        self.assertEqual(timer.owner, user)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_rejects_an_external_next_url(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "safe-owner",
                "password1": "Strong-Password-2026!",
                "password2": "Strong-Password-2026!",
                "next": "https://example.com/phishing",
            },
        )

        self.assertRedirects(response, reverse("home"))
