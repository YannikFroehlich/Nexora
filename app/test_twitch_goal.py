import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection as database_connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app import overlay_transfer, overlay_versions, twitch_api
from app.forms import TwitchGoalOverlayForm
from app.models import (
    TwitchConnection,
    TwitchGoalOverlay,
    goal_elements_for_layout,
)

User = get_user_model()


def form_data(overlay, **overrides):
    data = {field: getattr(overlay, field) for field in overlay_transfer.TWITCH_GOAL_FIELDS}
    data["elements"] = json.dumps(data["elements"])
    data.update({"font_asset": "", "logo_asset": "", "background_asset": ""})
    data.update(overrides)
    return data


class TwitchGoalModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="goal-model-owner")

    def test_total_and_campaign_progress_are_clamped(self):
        overlay = TwitchGoalOverlay(owner=self.user, target_value=100)

        self.assertEqual(overlay.progress_values(150)["progress_percent"], 100)
        self.assertEqual(overlay.progress_values(150)["remaining"], 0)

        overlay.progress_mode = overlay.MODE_CAMPAIGN
        overlay.campaign_baseline = 120
        self.assertEqual(overlay.progress_values(110)["current_value"], 0)
        self.assertEqual(overlay.progress_values(150)["current_value"], 30)

    def test_campaign_baseline_waits_for_first_successful_value(self):
        overlay = TwitchGoalOverlay.objects.create(
            owner=self.user,
            progress_mode=TwitchGoalOverlay.MODE_CAMPAIGN,
            target_value=25,
        )

        twitch_api.reconcile_goal(overlay, None)
        overlay.refresh_from_db()
        self.assertIsNone(overlay.campaign_baseline)

        twitch_api.reconcile_goal(overlay, 400)
        overlay.refresh_from_db()
        self.assertEqual(overlay.campaign_baseline, 400)
        self.assertEqual(overlay.last_observed_progress, 0)
        self.assertEqual(overlay.celebration_sequence, 0)

    def test_goal_crossing_celebrates_once_per_revision(self):
        overlay = TwitchGoalOverlay.objects.create(owner=self.user, target_value=100)

        twitch_api.reconcile_goal(overlay, 80)
        twitch_api.reconcile_goal(overlay, 100)
        twitch_api.reconcile_goal(overlay, 140)
        overlay.refresh_from_db()

        self.assertEqual(overlay.celebration_sequence, 1)
        self.assertEqual(overlay.celebrated_revision, overlay.goal_revision)

    def test_already_reached_goal_is_initialized_without_celebration(self):
        overlay = TwitchGoalOverlay.objects.create(owner=self.user, target_value=100)

        twitch_api.reconcile_goal(overlay, 120)
        overlay.refresh_from_db()

        self.assertEqual(overlay.celebration_sequence, 0)
        self.assertEqual(overlay.celebrated_revision, overlay.goal_revision)
        self.assertIsNotNone(overlay.completed_at)

    def test_form_enforces_preset_dimensions_and_resets_definition_runtime(self):
        overlay = TwitchGoalOverlay.objects.create(
            owner=self.user,
            target_value=100,
            campaign_baseline=40,
            last_observed_progress=20,
            completed_at=timezone.now(),
        )
        form = TwitchGoalOverlayForm(
            data=form_data(
                overlay,
                target_value=250,
                layout_mode=TwitchGoalOverlay.LAYOUT_RADIAL,
                canvas_width=999,
                canvas_height=999,
            ),
            instance=overlay,
            asset_owner=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        changed = form.save()
        self.assertEqual((changed.canvas_width, changed.canvas_height), (420, 420))
        self.assertEqual(changed.goal_revision, 2)
        self.assertIsNone(changed.campaign_baseline)
        self.assertIsNone(changed.last_observed_progress)
        self.assertIsNone(changed.completed_at)

    def test_form_rejects_unknown_elements(self):
        overlay = TwitchGoalOverlay(owner=self.user)
        bad_elements = [{**goal_elements_for_layout()[0], "type": "script"}]
        form = TwitchGoalOverlayForm(
            data=form_data(overlay, elements=json.dumps(bad_elements)),
            instance=overlay,
            asset_owner=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("elements", form.errors)


class TwitchConnectionAndAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="twitch-api-owner")
        self.connection = TwitchConnection.objects.create(
            owner=self.user,
            access_token="access-secret",
            refresh_token="refresh-secret",
            twitch_user_id="1234",
            twitch_login="nexora",
            display_name="Nexora",
            scopes=[twitch_api.FOLLOWER_SCOPE, twitch_api.SUBSCRIPTION_SCOPE],
            validated_at=timezone.now(),
        )

    def test_tokens_are_encrypted_in_storage(self):
        table = TwitchConnection._meta.db_table
        with database_connection.cursor() as cursor:
            cursor.execute(
                f"SELECT access_token, refresh_token FROM {table} WHERE id = %s",
                [self.connection.pk],
            )
            stored_access, stored_refresh = cursor.fetchone()

        self.assertNotEqual(stored_access, "access-secret")
        self.assertNotEqual(stored_refresh, "refresh-secret")
        self.assertTrue(stored_access.startswith("fernet$"))

    @override_settings(TWITCH_METRIC_CACHE_SECONDS=15)
    def test_follower_metric_is_shared_from_the_account_cache(self):
        with patch("app.twitch_api._helix_metric_request", return_value={"total": 842}) as request:
            first = twitch_api.cached_metric_state(
                self.connection, TwitchGoalOverlay.GOAL_FOLLOWERS
            )
            second = twitch_api.cached_metric_state(
                self.connection, TwitchGoalOverlay.GOAL_FOLLOWERS
            )

        self.assertEqual(first["follower_count"], 842)
        self.assertEqual(second["follower_count"], 842)
        request.assert_called_once()

    def test_subscription_response_keeps_total_and_points(self):
        with patch(
            "app.twitch_api._helix_metric_request",
            return_value={"total": 18, "points": 26},
        ):
            state = twitch_api.cached_metric_state(
                self.connection, TwitchGoalOverlay.GOAL_SUBSCRIPTIONS
            )

        self.assertEqual(state["subscription_count"], 18)
        self.assertEqual(state["subscription_points"], 26)

    def test_refresh_lease_returns_last_known_value_during_parallel_fetch(self):
        self.connection.follower_count = 77
        self.connection.follower_cached_at = timezone.now() - timedelta(minutes=1)
        self.connection.refresh_started_at = timezone.now()
        self.connection.save()

        with patch("app.twitch_api._helix_metric_request") as request:
            state = twitch_api.cached_metric_state(
                self.connection, TwitchGoalOverlay.GOAL_FOLLOWERS
            )

        self.assertEqual(state["follower_count"], 77)
        request.assert_not_called()

    def test_temporary_failure_preserves_last_known_value(self):
        self.connection.follower_count = 55
        self.connection.follower_cached_at = timezone.now() - timedelta(minutes=1)
        self.connection.save()

        with patch(
            "app.twitch_api._helix_metric_request",
            side_effect=twitch_api.TwitchAPIError("temporarily unavailable", 500),
        ):
            state = twitch_api.cached_metric_state(
                self.connection, TwitchGoalOverlay.GOAL_FOLLOWERS
            )

        self.assertEqual(state["follower_count"], 55)
        self.assertEqual(state["error"], "temporarily unavailable")
        self.assertFalse(state["needs_reconnect"])

    def test_helix_401_refreshes_once_and_retries(self):
        with (
            patch(
                "app.twitch_api._api_request",
                side_effect=[twitch_api.TwitchAPIError("expired", 401), {"total": 9}],
            ) as request,
            patch("app.twitch_api._refresh_access_token") as refresh,
        ):
            result = twitch_api._helix_metric_request(
                twitch_api.FOLLOWERS_URL,
                self.connection,
                {"broadcaster_id": "1234"},
            )

        self.assertEqual(result["total"], 9)
        self.assertEqual(request.call_count, 2)
        refresh.assert_called_once_with(self.connection)

    @override_settings(TWITCH_CLIENT_ID="expected-client")
    def test_validation_marks_wrong_application_for_reconnect(self):
        with patch(
            "app.twitch_api._validate_request",
            return_value={"client_id": "different-client"},
        ):
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api.validate_connection(self.connection, force=True)

        self.connection.refresh_from_db()
        self.assertTrue(self.connection.needs_reconnect)

    def test_temporary_validation_error_does_not_require_reconnect(self):
        with patch(
            "app.twitch_api._validate_request",
            side_effect=twitch_api.TwitchAPIError("network down", 500),
        ):
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api.validate_connection(self.connection, force=True)

        self.connection.refresh_from_db()
        self.assertFalse(self.connection.needs_reconnect)
        self.assertEqual(self.connection.last_error, "network down")

    def test_hourly_validation_command_checks_stored_connections(self):
        output = StringIO()
        with patch("app.twitch_api.validate_connection") as validate:
            call_command("validate_twitch_tokens", stdout=output)

        validate.assert_called_once()
        self.assertIn("Validated 1 Twitch token", output.getvalue())


@override_settings(
    TWITCH_CLIENT_ID="client-id",
    TWITCH_CLIENT_SECRET="client-secret",
    TWITCH_REDIRECT_URI="http://testserver/goals/twitch/callback/",
)
class TwitchGoalEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="goal-endpoint-owner")
        self.other = User.objects.create_user(username="goal-endpoint-other")
        self.client.force_login(self.user)
        self.connection = TwitchConnection.objects.create(
            owner=self.user,
            access_token="private-access-token",
            refresh_token="private-refresh-token",
            twitch_user_id="444",
            twitch_login="creator",
            display_name="Creator",
            scopes=[twitch_api.FOLLOWER_SCOPE],
            follower_count=88,
            follower_cached_at=timezone.now(),
            validated_at=timezone.now(),
        )
        self.overlay = TwitchGoalOverlay.objects.create(
            owner=self.user,
            connection=self.connection,
            name="Follower Sprint",
            target_value=100,
        )

    def test_connect_uses_csrf_state_and_incremental_scopes(self):
        self.connection.scopes = [twitch_api.FOLLOWER_SCOPE]
        self.connection.save(update_fields=("scopes", "updated_at"))
        self.overlay.goal_type = TwitchGoalOverlay.GOAL_SUBSCRIPTIONS
        self.overlay.save(update_fields=("goal_type", "updated_at"))

        response = self.client.get(reverse("twitch_connect", args=[self.overlay.pk]))
        query = parse_qs(urlparse(response.url).query)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(query["state"][0], self.client.session["twitch_oauth"]["state"])
        self.assertEqual(
            set(query["scope"][0].split()),
            {twitch_api.FOLLOWER_SCOPE, twitch_api.SUBSCRIPTION_SCOPE},
        )

    def test_callback_rejects_invalid_state(self):
        session = self.client.session
        session["twitch_oauth"] = {
            "state": "expected",
            "overlay_id": self.overlay.pk,
            "scopes": [twitch_api.FOLLOWER_SCOPE],
        }
        session.save()

        with patch("app.twitch_api.exchange_authorization_code") as exchange:
            response = self.client.get(
                reverse("twitch_callback"),
                {"state": "wrong", "code": "code"},
            )

        self.assertEqual(response.status_code, 302)
        exchange.assert_not_called()

    def test_public_state_has_etag_and_never_exposes_secrets(self):
        url = reverse("twitch_goal_overlay_state", args=[self.overlay.public_token])
        response = self.client.get(url)
        payload = response.json()
        encoded = json.dumps(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["goal"]["current_value"], 88)
        self.assertNotIn("private-access-token", encoded)
        self.assertNotIn("private-refresh-token", encoded)
        self.assertNotIn("scopes", encoded)
        self.assertNotIn("error", encoded)
        self.assertNotIn("campaign_baseline", encoded)

        cached = self.client.get(url, HTTP_IF_NONE_MATCH=response["ETag"])
        self.assertEqual(cached.status_code, 304)

    def test_public_overlay_is_available_without_login_and_has_no_store(self):
        self.client.logout()
        response = self.client.get(reverse("twitch_goal_overlay", args=[self.overlay.public_token]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(response, "data-twitch-goal-source")

    def test_temporary_error_is_visible_only_in_the_editor(self):
        self.connection.last_error = "Helix temporarily unavailable"
        self.connection.save(update_fields=("last_error", "updated_at"))

        editor = self.client.get(reverse("twitch_goal_manage", args=[self.overlay.pk]))
        public = self.client.get(
            reverse("twitch_goal_overlay_state", args=[self.overlay.public_token])
        )

        self.assertContains(editor, "Helix temporarily unavailable")
        self.assertNotIn("Helix temporarily unavailable", public.content.decode())
        self.assertEqual(public.json()["goal"]["status"], "stale")

    def test_replay_is_post_only_and_owner_protected(self):
        replay_url = reverse("twitch_goal_replay", args=[self.overlay.pk])
        self.assertEqual(self.client.get(replay_url).status_code, 405)

        self.client.force_login(self.other)
        self.assertEqual(self.client.post(replay_url).status_code, 404)

        self.client.force_login(self.user)
        response = self.client.post(replay_url)
        self.overlay.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.overlay.celebration_sequence, 1)

    def test_disconnect_clears_accountwide_tokens_profile_and_caches(self):
        with patch("app.twitch_api._read_json_response", return_value={}):
            response = self.client.post(reverse("twitch_disconnect"))

        self.assertEqual(response.status_code, 302)
        self.connection.refresh_from_db()
        self.overlay.refresh_from_db()
        self.assertEqual(self.connection.access_token, "")
        self.assertEqual(self.connection.refresh_token, "")
        self.assertEqual(self.connection.scopes, [])
        self.assertEqual(self.connection.display_name, "")
        self.assertIsNone(self.connection.follower_count)
        self.assertEqual(self.overlay.connection, self.connection)

    def test_csrf_is_required_for_replay(self):
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.user)
        response = strict_client.post(reverse("twitch_goal_replay", args=[self.overlay.pk]))
        self.assertEqual(response.status_code, 403)

    def test_campaign_reset_is_limited_to_campaign_goals(self):
        url = reverse("twitch_goal_campaign_reset", args=[self.overlay.pk])
        self.assertEqual(self.client.post(url).status_code, 409)

        self.overlay.progress_mode = TwitchGoalOverlay.MODE_CAMPAIGN
        self.overlay.save(update_fields=("progress_mode", "updated_at"))
        response = self.client.post(url)
        self.overlay.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.overlay.campaign_baseline, 88)
        self.assertEqual(self.overlay.last_observed_progress, 0)

    def test_export_and_duplicate_reset_runtime_state(self):
        self.overlay.progress_mode = TwitchGoalOverlay.MODE_CAMPAIGN
        self.overlay.campaign_baseline = 50
        self.overlay.last_observed_progress = 20
        self.overlay.celebration_sequence = 4
        self.overlay.celebrated_revision = 1
        self.overlay.save()

        exported = self.client.get(reverse("twitch_goal_export", args=[self.overlay.pk])).json()
        self.assertNotIn("campaign_baseline", exported["overlay"])
        self.assertNotIn("celebration_sequence", exported["overlay"])
        self.assertNotIn("connection", exported["overlay"])

        self.client.post(reverse("twitch_goal_duplicate", args=[self.overlay.pk]))
        duplicate = TwitchGoalOverlay.objects.exclude(pk=self.overlay.pk).get()
        self.assertIsNone(duplicate.campaign_baseline)
        self.assertIsNone(duplicate.last_observed_progress)
        self.assertEqual(duplicate.celebration_sequence, 0)
        self.assertEqual(duplicate.celebrated_revision, 0)

        imported = overlay_transfer.import_payload(exported, self.other)
        self.assertEqual(imported.owner, self.other)
        self.assertIsNone(imported.campaign_baseline)
        self.assertEqual(imported.celebration_sequence, 0)
        self.assertNotEqual(imported.connection, self.connection)

    def test_version_history_restores_goal_design_without_runtime_data(self):
        original_title = self.overlay.title
        version, created = overlay_versions.record_version(self.overlay)
        self.assertTrue(created)
        self.overlay.title = "Changed title"
        self.overlay.celebration_sequence = 7
        self.overlay.save()

        overlay_versions.restore_version(self.overlay, version)
        self.overlay.refresh_from_db()

        self.assertEqual(self.overlay.title, original_title)
        self.assertEqual(self.overlay.celebration_sequence, 7)
