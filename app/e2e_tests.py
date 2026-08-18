import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from app.models import (
    SpotifyOverlay,
    TimerOverlay,
    TwitchGoalOverlay,
    WinChallenge,
    WinChallengeGame,
)


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
        self.goal = TwitchGoalOverlay.objects.create(
            owner=self.user,
            name="Browser Twitch Goal",
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
            (
                reverse("twitch_goal_overlay", args=[self.goal.public_token]),
                "[data-twitch-goal-source]",
                "[data-twitch-goal-canvas]",
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

    def test_editor_surfaces_empty_assets_and_responsive_actions_are_consistent(self):
        editor_pages = (
            (
                reverse("spotify_manage", args=[self.spotify.pk]),
                ".spotify-panel",
            ),
            (
                reverse("timer_manage", args=[self.timer.pk]),
                ".timer-panel",
            ),
            (
                reverse("winchallenge_manage", args=[self.challenge.pk]),
                ".editor-panel--surface",
            ),
            (
                reverse("twitch_goal_manage", args=[self.goal.pk]),
                ".goal-panel",
            ),
        )

        for path, panel_selector in editor_pages:
            with self.subTest(path=path):
                page = self.context.new_page()
                page.goto(self.live_server_url + path)

                expect(page.locator(panel_selector).first).to_have_css(
                    "border-radius",
                    "24px",
                )
                branding = page.locator("[data-overlay-branding-controls]")
                expect(branding).to_have_css("border-top-width", "1px")

                asset_selects = page.locator("[data-branding-field]")
                self.assertEqual(asset_selects.count(), 3)
                for index in range(asset_selects.count()):
                    select = asset_selects.nth(index)
                    self.assertTrue(select.is_disabled())
                    self.assertEqual(select.locator("option").count(), 1)

                page.close()

        timer_page = self.context.new_page()
        timer_page.set_viewport_size({"width": 760, "height": 900})
        timer_page.goto(self.live_server_url + reverse("timer_manage", args=[self.timer.pk]))
        back_button = timer_page.locator(".timer-hero > .btn")
        box = back_button.bounding_box()
        self.assertIsNotNone(box)
        self.assertLessEqual(box["height"], 48)
        timer_page.close()

    def test_twitch_goal_editor_and_public_source_scale_without_horizontal_clipping(self):
        page = self.context.new_page()
        editor_url = self.live_server_url + reverse("twitch_goal_manage", args=[self.goal.pk])

        for width in (1440, 760, 390):
            with self.subTest(width=width):
                page.set_viewport_size({"width": width, "height": 960})
                page.goto(editor_url)
                expect(page.locator("[data-twitch-goal-editor]")).to_be_visible()
                expect(page.locator("[data-twitch-goal-canvas]")).to_be_visible()
                has_horizontal_overflow = page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
                )
                self.assertFalse(has_horizontal_overflow)

        page.close()

        for width, height in ((900, 160), (450, 80), (1920, 1080)):
            with self.subTest(source=(width, height)):
                source_context = self.browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                )
                source = source_context.new_page()
                source.goto(
                    self.live_server_url
                    + reverse("twitch_goal_overlay", args=[self.goal.public_token])
                )
                canvas_box = source.locator("[data-twitch-goal-canvas]").bounding_box()
                self.assertIsNotNone(canvas_box)
                self.assertGreaterEqual(canvas_box["x"], -0.5)
                self.assertGreaterEqual(canvas_box["y"], -0.5)
                self.assertLessEqual(canvas_box["x"] + canvas_box["width"], width + 0.5)
                self.assertLessEqual(canvas_box["y"] + canvas_box["height"], height + 0.5)
                source_context.close()

    def test_twitch_goal_celebration_replays_once_and_respects_reduced_motion(self):
        editor = self.context.new_page()
        editor.goto(self.live_server_url + reverse("twitch_goal_manage", args=[self.goal.pk]))
        editor.locator("#id_animation_type").select_option("neon")
        editor.locator("#id_animation_duration").fill("3")
        editor.locator("#id_sound_type").select_option("chime")
        expect(editor.locator("[data-editor-save-status]")).to_have_attribute(
            "data-state",
            "saved",
            timeout=7_000,
        )

        fake_audio_context = """
            window.__goalSoundPlayCount = 0;
            window.AudioContext = class {
                constructor() {
                    window.__goalSoundPlayCount += 1;
                    this.currentTime = 0;
                    this.destination = {};
                }
                createOscillator() {
                    return {
                        type: 'sine', frequency: {value: 0},
                        connect(target) { return target; }, start() {}, stop() {},
                    };
                }
                createGain() {
                    return {
                        gain: {
                            setValueAtTime() {},
                            exponentialRampToValueAtTime() {},
                        },
                        connect(target) { return target; },
                    };
                }
                close() { return Promise.resolve(); }
            };
        """
        public = self.context.new_page()
        public.add_init_script(fake_audio_context)
        public.goto(
            self.live_server_url + reverse("twitch_goal_overlay", args=[self.goal.public_token])
        )

        editor.locator("[data-replay-obs]").click()
        public.wait_for_function(
            "document.querySelector('[data-twitch-goal-canvas]').classList.contains('is-celebrating-neon')",
            timeout=6_000,
        )
        self.assertEqual(public.evaluate("window.__goalSoundPlayCount"), 1)

        public.reload()
        public.wait_for_timeout(2_300)
        self.assertFalse(
            public.locator("[data-twitch-goal-canvas]").evaluate(
                "node => node.classList.contains('is-celebrating-neon')"
            )
        )
        self.assertEqual(public.evaluate("window.__goalSoundPlayCount"), 0)

        expect(editor.locator("[data-replay-obs]")).to_be_enabled(timeout=5_000)
        editor.locator("[data-replay-obs]").click()
        public.wait_for_function("window.__goalSoundPlayCount === 1", timeout=6_000)
        self.assertEqual(public.evaluate("window.__goalSoundPlayCount"), 1)

        reduced_context = self.browser.new_context(
            viewport={"width": 900, "height": 160},
            reduced_motion="reduce",
        )
        reduced = reduced_context.new_page()
        reduced.goto(
            self.live_server_url + reverse("twitch_goal_overlay", args=[self.goal.public_token])
        )
        expect(editor.locator("[data-replay-obs]")).to_be_enabled(timeout=5_000)
        editor.locator("[data-replay-obs]").click()
        reduced.wait_for_function(
            "document.querySelector('[data-twitch-goal-canvas]').classList.contains('is-goal-flash')",
            timeout=6_000,
        )
        self.assertFalse(
            reduced.locator("[data-twitch-goal-canvas]").evaluate(
                "node => node.classList.contains('is-celebrating-neon')"
            )
        )
        reduced_context.close()
