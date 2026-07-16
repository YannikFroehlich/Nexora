import json
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.forms import SpotifyOverlayForm, WinChallengeCreateForm, WinChallengeDesignForm
from app.models import SpotifyOverlay, WinChallenge, WinChallengeGame


User = get_user_model()


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
        self.assertContains(response, 'data-open-label=')
        self.assertContains(response, 'data-close-label=')
        self.assertContains(response, 'class="header-menu" id="header-menu"')

    def test_page_exposes_skip_link_landmarks_and_public_indexing(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'class="skip-link" href="#main-content"')
        self.assertContains(response, '<main id="main-content" tabindex="-1">')
        self.assertContains(response, 'aria-label="Hauptnavigation"')
        self.assertContains(response, 'aria-label="Footer-Navigation"')
        self.assertContains(response, '<meta name="robots" content="index, follow">')
        self.assertContains(response, '<link rel="canonical" href="http://testserver/">')
        self.assertContains(response, "imgs/icons/Nexora_Icon.png")

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
        self.assertContains(response, "Kostenloses Konto zum Speichern und f\u00fcr OBS erforderlich.")

    def test_authenticated_overlay_actions_open_the_selected_editor(self):
        user = User.objects.create_user(username="home-creator")
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, f'href="{reverse("spotify_create")}"')
        self.assertContains(response, f'href="{reverse("winchallenge_create")}"')

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
        self.assertContains(response, 'data-demo-progress')

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
        self.assertIn("Disallow: /spotify/", content)
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
        self.assertContains(response, 'data-error-summary')


class AboutViewTests(TestCase):
    def test_about_page_describes_products_and_links_to_tools(self):
        response = self.client.get(reverse("about"))

        self.assertContains(response, "Tools für Streams mit deiner Handschrift")
        self.assertContains(response, "Zwei Tools, ein einheitlicher Workflow")
        dashboard_url = reverse("overlay_dashboard")
        self.assertContains(response, f'href="{dashboard_url}#spotify-overlays"')
        self.assertContains(response, f'href="{dashboard_url}#winchallenge-overlays"')

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

    def test_empty_dashboard_shows_both_overlay_categories(self):
        response = self.client.get(reverse("overlay_dashboard"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="spotify-overlays"')
        self.assertContains(response, 'id="winchallenge-overlays"')
        self.assertContains(response, 'class="dashboard-empty"', count=2)
        self.assertEqual(content.count(f'href="{reverse("spotify_create")}"'), 1)
        self.assertEqual(content.count(f'href="{reverse("winchallenge_create")}"'), 1)

    def test_dashboard_shows_saved_overlays_from_both_tools(self):
        spotify_overlay = SpotifyOverlay.objects.create(owner=self.user, name="Stream Music")
        challenge = WinChallenge.objects.create(owner=self.user, title="Road to Diamond")

        response = self.client.get(reverse("overlay_dashboard"))

        self.assertContains(response, spotify_overlay.display_name)
        self.assertContains(response, challenge.display_title)
        self.assertContains(response, "spotify-dashboard-preview")
        self.assertContains(response, "challenge-dashboard-preview")
        self.assertContains(response, reverse("spotify_duplicate", args=[spotify_overlay.pk]))
        self.assertContains(response, reverse("spotify_export", args=[spotify_overlay.pk]))
        self.assertContains(response, reverse("winchallenge_duplicate", args=[challenge.pk]))
        self.assertContains(response, reverse("winchallenge_export", args=[challenge.pk]))
        self.assertContains(response, reverse("overlay_import"))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertEqual(response.context["overlay_count"], 2)

    def test_legacy_overview_urls_redirect_to_dashboard_sections(self):
        self.assertRedirects(
            self.client.get(reverse("spotify_list")),
            f'{reverse("overlay_dashboard")}#spotify-overlays',
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(reverse("winchallenge_list")),
            f'{reverse("overlay_dashboard")}#winchallenge-overlays',
            fetch_redirect_response=False,
        )


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

    def test_spotify_duplicate_copies_design_but_not_connection_or_public_url(self):
        self.spotify.spotify_access_token = "private-access-token"
        self.spotify.spotify_refresh_token = "private-refresh-token"
        self.spotify.save()

        response = self.client.post(
            reverse("spotify_duplicate", args=[self.spotify.pk])
        )

        duplicate = SpotifyOverlay.objects.exclude(pk=self.spotify.pk).get(owner=self.user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(duplicate.canvas_width, self.spotify.canvas_width)
        self.assertEqual(duplicate.border_color, self.spotify.border_color)
        self.assertEqual(duplicate.elements, self.spotify.elements)
        self.assertNotEqual(duplicate.public_token, self.spotify.public_token)
        self.assertFalse(duplicate.spotify_access_token)
        self.assertFalse(duplicate.spotify_refresh_token)
        self.assertNotEqual(duplicate.name, self.spotify.name)

    def test_winchallenge_duplicate_copies_design_and_games(self):
        response = self.client.post(
            reverse("winchallenge_duplicate", args=[self.challenge.pk])
        )

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
        self.spotify.spotify_access_token = "private-access-token"
        self.spotify.save()

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
        response = self.client.get(
            reverse("winchallenge_export", args=[self.challenge.pk])
        )
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["type"], "winchallenge")
        self.assertEqual(payload["overlay"]["title"], "Ranked Run")
        self.assertEqual(
            payload["games"],
            [{"name": "Rocket League", "wins": 4, "target_wins": 7}],
        )

    def test_spotify_export_can_be_imported_as_new_owned_overlay(self):
        export_response = self.client.get(
            reverse("spotify_export", args=[self.spotify.pk])
        )
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

    def test_winchallenge_export_can_be_imported_with_games(self):
        export_response = self.client.get(
            reverse("winchallenge_export", args=[self.challenge.pk])
        )
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
            self.client.post(
                reverse("spotify_duplicate", args=[foreign_spotify.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("spotify_export", args=[foreign_spotify.pk])
            ).status_code,
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
        WinChallengeGame.objects.create(challenge=challenge, name="Rocket League", wins=4, target_wins=6)
        game = WinChallengeGame.objects.create(challenge=challenge, name="Valorant", wins=2, target_wins=4)

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
            field_name: getattr(candidate, field_name)
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
            field_name: getattr(self.challenge, field_name)
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
            field_name: getattr(self.overlay, field_name)
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
        self.assertContains(manage_response, reverse("spotify_overlay", args=[self.overlay.public_token]))

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

    def test_public_state_does_not_expose_spotify_tokens(self):
        self.overlay.spotify_access_token = "secret-access-token"
        self.overlay.spotify_refresh_token = "secret-refresh-token"
        self.overlay.spotify_token_expires_at = timezone.now() + timedelta(hours=1)
        self.overlay.save()

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
                    "album": {"name": "Lights", "images": [{"url": "https://example.com/cover.jpg"}]},
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


class AccessControlTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner")
        self.other_user = User.objects.create_user(username="other")
        self.owner_challenge = WinChallenge.objects.create(owner=self.owner, title="Owner Challenge")
        self.foreign_challenge = WinChallenge.objects.create(owner=self.other_user, title="Foreign Challenge")
        self.foreign_game = WinChallengeGame.objects.create(
            challenge=self.foreign_challenge,
            name="Private Game",
        )
        self.owner_spotify = SpotifyOverlay.objects.create(owner=self.owner, name="Owner Spotify")
        self.foreign_spotify = SpotifyOverlay.objects.create(owner=self.other_user, name="Foreign Spotify")

    def test_management_pages_redirect_anonymous_users_to_login(self):
        protected_urls = (
            reverse("overlay_dashboard"),
            reverse("overlay_import"),
            reverse("spotify_list"),
            reverse("spotify_create"),
            reverse("spotify_autosave", args=[self.owner_spotify.pk]),
            reverse("spotify_duplicate", args=[self.owner_spotify.pk]),
            reverse("spotify_export", args=[self.owner_spotify.pk]),
            reverse("winchallenge_list"),
            reverse("winchallenge_create"),
            reverse("winchallenge_autosave", args=[self.owner_challenge.pk]),
            reverse("winchallenge_duplicate", args=[self.owner_challenge.pk]),
            reverse("winchallenge_export", args=[self.owner_challenge.pk]),
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
        self.assertContains(dashboard, self.owner_challenge.title)
        self.assertNotContains(dashboard, self.foreign_challenge.title)
        self.assertEqual(
            self.client.get(reverse("spotify_manage", args=[self.foreign_spotify.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("winchallenge_manage", args=[self.foreign_challenge.pk])).status_code,
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
                reverse("winchallenge_autosave", args=[self.foreign_challenge.pk]),
                {"form_type": "challenge", "title": "No access"},
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
        challenge_response = self.client.get(
            reverse("winchallenge_overlay", args=[self.owner_challenge.public_token])
        )

        self.assertEqual(spotify_response.status_code, 200)
        self.assertEqual(challenge_response.status_code, 200)


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
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(challenge.owner, user)
        self.assertEqual(spotify.owner, user)
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
