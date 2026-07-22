import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from app.models import SpotifyOverlay, TimerOverlay, WinChallenge, WinChallengeGame


class OverlayEditorBrowserTests(StaticLiveServerTestCase):
    """Browser-level checks for editor state and OBS browser-source pages."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="browser-user",
            password="browser-test-password",
        )
        self.spotify = SpotifyOverlay.objects.create(
            owner=self.user,
            name="Browser Spotify",
        )
        self.timer = TimerOverlay.objects.create(
            owner=self.user,
            name="Browser Timer",
        )
        self.challenge = WinChallenge.objects.create(
            owner=self.user,
            title="Browser Challenge",
        )
        WinChallengeGame.objects.create(
            challenge=self.challenge,
            name="Browser Game",
            wins=2,
            target_wins=5,
        )

        self.client.force_login(self.user)
        session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]

        # Start Playwright only after synchronous Django setup has finished. Its
        # sync API owns an asyncio loop, which Django correctly rejects for ORM work.
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
        )
        self.context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": self.live_server_url,
                }
            ]
        )

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self.playwright.stop()

    def test_spotify_drag_autosave_undo_and_redo(self):
        page = self.context.new_page()
        page.goto(self.live_server_url + reverse("spotify_manage", args=[self.spotify.pk]))
        expect(page.locator("[data-spotify-editor]")).to_be_visible()

        elements_input = page.locator("[data-elements-input]")
        before_drag = json.loads(elements_input.input_value())
        before_title = next(element for element in before_drag if element["id"] == "title")

        title = page.locator('[data-element-id="title"]')
        title.scroll_into_view_if_needed()
        box = title.bounding_box()
        self.assertIsNotNone(box)
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(
            box["x"] + box["width"] / 2 + 70,
            box["y"] + box["height"] / 2 + 35,
            steps=8,
        )
        page.mouse.up()

        page.wait_for_function(
            """
            ([elementId, oldX, oldY]) => {
                const input = document.querySelector('[data-elements-input]');
                const element = JSON.parse(input.value).find((item) => item.id === elementId);
                return element.x !== oldX || element.y !== oldY;
            }
            """,
            arg=["title", before_title["x"], before_title["y"]],
        )
        expect(page.locator("[data-editor-save-status]")).to_have_attribute(
            "data-state",
            "saved",
            timeout=7_000,
        )
        saved_elements = elements_input.input_value()

        page.reload()
        persisted_elements = page.locator("[data-elements-input]").input_value()
        self.assertEqual(json.loads(persisted_elements), json.loads(saved_elements))

        name_input = page.locator("#id_name")
        original_name = name_input.input_value()
        changed_name = "Browser Spotify Autosaved"
        name_input.fill(changed_name)
        expect(page.locator("[data-editor-undo]")).to_be_enabled(timeout=2_000)

        page.locator("[data-editor-undo]").click()
        expect(name_input).to_have_value(original_name)
        expect(page.locator("[data-editor-redo]")).to_be_enabled()

        page.locator("[data-editor-redo]").click()
        expect(name_input).to_have_value(changed_name)
        expect(page.locator("[data-editor-save-status]")).to_have_attribute(
            "data-state",
            "saved",
            timeout=7_000,
        )

        page.reload()
        expect(page.locator("#id_name")).to_have_value(changed_name)

    def test_public_overlays_render_as_transparent_obs_browser_sources(self):
        obs_context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        sources = (
            (
                reverse("spotify_overlay", args=[self.spotify.public_token]),
                "[data-spotify-overlay-source]",
                "[data-spotify-canvas]",
            ),
            (
                reverse("timer_overlay", args=[self.timer.public_token]),
                "[data-timer-source]",
                "[data-timer-overlay]",
            ),
            (
                reverse("winchallenge_overlay", args=[self.challenge.public_token]),
                "[data-overlay-source]",
                "[data-winchallenge-overlay]",
            ),
        )

        for path, source_selector, overlay_selector in sources:
            with self.subTest(path=path):
                page = obs_context.new_page()
                page_errors = []
                page.on(
                    "pageerror",
                    lambda error, errors=page_errors: errors.append(error),
                )

                response = page.goto(self.live_server_url + path)
                self.assertIsNotNone(response)
                self.assertEqual(response.status, 200)
                expect(page.locator(source_selector)).to_be_attached()
                expect(page.locator(overlay_selector)).to_be_visible()
                expect(page.locator('meta[name="robots"]')).to_have_attribute(
                    "content",
                    "noindex",
                )
                background = page.evaluate("window.getComputedStyle(document.body).backgroundColor")
                self.assertEqual(background, "rgba(0, 0, 0, 0)")
                page.wait_for_timeout(250)
                self.assertEqual(page_errors, [])
                page.close()

        obs_context.close()

    def test_preset_font_updates_preview_and_public_overlay(self):
        page = self.context.new_page()
        page.goto(self.live_server_url + reverse("spotify_manage", args=[self.spotify.pk]))

        font_select = page.locator("#id_font_family")
        font_select.select_option(SpotifyOverlay.FONT_GEORGIA)
        expect(page.locator("[data-spotify-canvas]")).to_have_css(
            "font-family",
            "Georgia, serif",
        )
        expect(page.locator("[data-editor-save-status]")).to_have_attribute(
            "data-state",
            "saved",
            timeout=7_000,
        )

        page.reload()
        expect(page.locator("#id_font_family")).to_have_value(SpotifyOverlay.FONT_GEORGIA)

        public_page = self.context.new_page()
        public_page.goto(
            self.live_server_url + reverse("spotify_overlay", args=[self.spotify.public_token])
        )
        expect(public_page.locator("[data-spotify-canvas]")).to_have_css(
            "font-family",
            "Georgia, serif",
        )
