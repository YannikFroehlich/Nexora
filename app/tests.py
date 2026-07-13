import json
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.forms import SpotifyOverlayForm, WinChallengeCreateForm
from app.models import SpotifyOverlay, WinChallenge, WinChallengeGame


class HomeViewTests(TestCase):
    def test_header_links_to_overlay_tools_instead_of_repeating_home(self):
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertContains(response, f'href="{reverse("spotify_list")}"')
        self.assertContains(response, f'href="{reverse("winchallenge_list")}"')
        self.assertContains(response, f'href="{reverse("about")}"')
        self.assertContains(response, 'class="header-logo__image"')
        self.assertContains(response, "imgs/icons/nexora_logo.png")
        self.assertEqual(content.count(f'href="{reverse("home")}"'), 1)

    def test_header_marks_current_tool_area_as_active(self):
        response = self.client.get(reverse("spotify_create"))

        self.assertContains(
            response,
            f'href="{reverse("spotify_list")}"\n                        aria-current="page"',
        )

    def test_home_uses_selected_language_for_content_and_document(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertContains(response, "Custom OBS overlays made simple")
        self.assertContains(response, "Now playing")
        self.assertIn('<html lang="en">', content)

    @override_settings(APP_VERSION="9.8.7-test")
    def test_footer_uses_configured_app_version(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Version 9.8.7-test")


class AboutViewTests(TestCase):
    def test_about_page_describes_products_and_links_to_tools(self):
        response = self.client.get(reverse("about"))

        self.assertContains(response, "Tools für Streams mit deiner Handschrift")
        self.assertContains(response, "Zwei Tools, ein einheitlicher Workflow")
        self.assertContains(response, f'href="{reverse("spotify_list")}"')
        self.assertContains(response, f'href="{reverse("winchallenge_list")}"')

    def test_about_page_is_available_in_english(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

        response = self.client.get(reverse("about"))
        content = response.content.decode()

        self.assertContains(response, "Tools for streams that feel like yours")
        self.assertContains(response, "Made to stay out of your way")
        self.assertIn('<html lang="en">', content)


class WinChallengeListTests(TestCase):
    def test_empty_list_shows_one_create_link_and_example_preview(self):
        response = self.client.get(reverse("winchallenge_list"))
        create_url = reverse("winchallenge_create")
        content = response.content.decode()

        self.assertContains(response, "empty-preview-window")
        self.assertEqual(content.count(f'href="{create_url}"'), 1)

    def test_saved_list_shows_one_create_link_and_challenge_card(self):
        challenge = WinChallenge.objects.create(title="Road to Diamond")

        response = self.client.get(reverse("winchallenge_list"))
        create_url = reverse("winchallenge_create")
        content = response.content.decode()

        self.assertContains(response, challenge.display_title)
        self.assertContains(response, "challenge-card__preview-canvas")
        self.assertEqual(content.count(f'href="{create_url}"'), 1)


class WinChallengeModelTests(TestCase):
    def test_total_wins_are_calculated_from_games(self):
        challenge = WinChallenge.objects.create(title="Road to Diamond")
        WinChallengeGame.objects.create(challenge=challenge, name="Rocket League", wins=4, target_wins=6)
        game = WinChallengeGame.objects.create(challenge=challenge, name="Valorant", wins=2, target_wins=4)

        self.assertEqual(challenge.total_wins, 6)
        self.assertEqual(game.progress_percent, 50)


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
        self.challenge = WinChallenge.objects.create(title="Road to Diamond")
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

    def test_manage_page_uses_the_shared_editor_design(self):
        response = self.client.get(reverse("winchallenge_manage", args=[self.challenge.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "winchallenge-editor-page--manage")
        self.assertContains(response, "editor-panel--surface", count=4)
        self.assertContains(response, "preview-panel--surface")
        self.assertContains(response, '<div class="preview-stage">')

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
        self.assertContains(home_response, reverse("spotify_list"))

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
        data = self.valid_data(border_color="#FF8800", border_width=7)
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
        self.overlay = SpotifyOverlay.objects.create(name="Desk Setup")

    @override_settings(SPOTIFY_CLIENT_ID="client-id", SPOTIFY_CLIENT_SECRET="client-secret")
    def test_list_and_manage_pages_show_saved_overlay(self):
        list_response = self.client.get(reverse("spotify_list"))
        manage_response = self.client.get(reverse("spotify_manage", args=[self.overlay.pk]))

        self.assertContains(list_response, "Desk Setup")
        self.assertContains(manage_response, "data-spotify-editor")
        self.assertContains(manage_response, reverse("spotify_connect", args=[self.overlay.pk]))
        self.assertContains(manage_response, reverse("spotify_overlay", args=[self.overlay.public_token]))

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
