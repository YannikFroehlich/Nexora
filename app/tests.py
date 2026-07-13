from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from app.forms import WinChallengeCreateForm
from app.models import WinChallenge, WinChallengeGame


class HomeViewTests(TestCase):
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

    def test_spotify_create_page_is_placeholder(self):
        home_response = self.client.get(reverse("home"))
        response = self.client.get(reverse("spotify_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coming soon")
        self.assertContains(home_response, reverse("spotify_create"))

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
