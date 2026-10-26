import json
from datetime import timedelta
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch
from urllib import error as urlerror
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.db import connection as database_connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app import overlay_transfer, overlay_versions, twitch_api
from app.forms import TwitchGoalOverlayForm
from app.models import (
    OverlayVersion,
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

    def test_recent_validation_is_reused_without_request(self):
        with patch("app.twitch_api._validate_request") as validate_request:
            data = twitch_api.validate_connection(self.connection)

        validate_request.assert_not_called()
        self.assertEqual(data["user_id"], "1234")
        self.assertEqual(data["login"], "nexora")

    def test_validation_without_access_token_is_rejected(self):
        self.connection.access_token = ""

        with self.assertRaises(twitch_api.TwitchAPIError) as raised:
            twitch_api.validate_connection(self.connection, force=True)

        self.assertEqual(raised.exception.status_code, 401)

    @override_settings(TWITCH_CLIENT_ID="client-id", TWITCH_CLIENT_SECRET="client-secret")
    def test_expired_token_is_refreshed_and_revalidated(self):
        with (
            patch(
                "app.twitch_api._validate_request",
                side_effect=[
                    twitch_api.TwitchAPIError("invalid access token", 401),
                    {
                        "client_id": "client-id",
                        "user_id": "1234",
                        "login": "nexora",
                        "scopes": [twitch_api.FOLLOWER_SCOPE],
                    },
                ],
            ) as validate_request,
            patch(
                "app.twitch_api._token_request",
                return_value={"access_token": "new-access", "refresh_token": "rotated"},
            ) as token_request,
        ):
            twitch_api.validate_connection(self.connection, force=True)

        self.connection.refresh_from_db()
        token_request.assert_called_once_with(
            {"grant_type": "refresh_token", "refresh_token": "refresh-secret"}
        )
        validate_request.assert_called_with("new-access")
        self.assertEqual(self.connection.access_token, "new-access")
        self.assertEqual(self.connection.refresh_token, "rotated")
        self.assertEqual(self.connection.scopes, [twitch_api.FOLLOWER_SCOPE])
        self.assertIsNotNone(self.connection.validated_at)
        self.assertFalse(self.connection.needs_reconnect)

    def test_failed_refresh_marks_connection_for_reconnect(self):
        with (
            patch(
                "app.twitch_api._validate_request",
                side_effect=twitch_api.TwitchAPIError("invalid access token", 401),
            ),
            patch(
                "app.twitch_api._token_request",
                side_effect=twitch_api.TwitchAPIError("Invalid refresh token", 400),
            ),
        ):
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api.validate_connection(self.connection, force=True)

        self.connection.refresh_from_db()
        self.assertTrue(self.connection.needs_reconnect)
        self.assertEqual(self.connection.last_error, "Invalid refresh token")
        self.assertEqual(self.connection.access_token, "access-secret")

    def test_401_without_refresh_token_marks_reconnect_without_refresh(self):
        self.connection.refresh_token = ""
        self.connection.save()

        with (
            patch(
                "app.twitch_api._validate_request",
                side_effect=twitch_api.TwitchAPIError("invalid access token", 401),
            ),
            patch("app.twitch_api._token_request") as token_request,
        ):
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api.validate_connection(self.connection, force=True)

        token_request.assert_not_called()
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.needs_reconnect)

    def test_helix_401_without_refresh_token_is_raised(self):
        self.connection.refresh_token = ""

        with (
            patch(
                "app.twitch_api._api_request",
                side_effect=twitch_api.TwitchAPIError("expired", 401),
            ),
            patch("app.twitch_api._refresh_access_token") as refresh,
        ):
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api._helix_metric_request(twitch_api.FOLLOWERS_URL, self.connection, {})

        refresh.assert_not_called()

    def test_token_response_without_access_token_is_rejected(self):
        with self.assertRaises(twitch_api.TwitchAPIError):
            twitch_api._store_token_response(self.connection, {"refresh_token": "rotated"})

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.access_token, "access-secret")
        self.assertEqual(self.connection.refresh_token, "refresh-secret")

    def test_token_response_keeps_refresh_token_and_resets_validation(self):
        self.connection.needs_reconnect = True
        self.connection.last_error = "expired"
        self.connection.save()

        twitch_api._store_token_response(
            self.connection,
            {"access_token": "new-access", "expires_in": "soon"},
        )
        self.connection.refresh_from_db()

        remaining = self.connection.token_expires_at - timezone.now()
        self.assertEqual(self.connection.access_token, "new-access")
        self.assertEqual(self.connection.refresh_token, "refresh-secret")
        self.assertGreater(remaining, timedelta(minutes=59))
        self.assertIsNone(self.connection.validated_at)
        self.assertFalse(self.connection.needs_reconnect)
        self.assertEqual(self.connection.last_error, "")

    def test_auth_failure_during_metric_fetch_requires_reconnect(self):
        self.connection.follower_count = 40
        self.connection.save()

        with patch(
            "app.twitch_api._helix_metric_request",
            side_effect=twitch_api.TwitchAPIError("Missing scope", 403),
        ):
            state = twitch_api.cached_metric_state(
                self.connection, TwitchGoalOverlay.GOAL_FOLLOWERS
            )

        self.assertEqual(state["follower_count"], 40)
        self.assertTrue(state["needs_reconnect"])
        self.connection.refresh_from_db()
        self.assertIsNone(self.connection.refresh_started_at)
        self.assertIsNotNone(self.connection.follower_cached_at)

    def test_malformed_metric_response_preserves_last_known_value(self):
        self.connection.subscription_count = 12
        self.connection.save()

        with patch(
            "app.twitch_api._helix_metric_request",
            return_value={"total": "many", "points": 3},
        ):
            state = twitch_api.cached_metric_state(
                self.connection, TwitchGoalOverlay.GOAL_SUBSCRIPTIONS
            )

        self.assertEqual(state["subscription_count"], 12)
        self.assertTrue(state["error"])
        self.assertFalse(state["needs_reconnect"])

    @override_settings(TWITCH_CLIENT_ID="client-id", TWITCH_CLIENT_SECRET="client-secret")
    def test_code_exchange_rejects_missing_scopes(self):
        with (
            patch("app.twitch_api._token_request", return_value={"access_token": "new-access"}),
            patch(
                "app.twitch_api._validate_request",
                return_value={
                    "client_id": "client-id",
                    "user_id": "1234",
                    "login": "nexora",
                    "scopes": [twitch_api.FOLLOWER_SCOPE],
                },
            ),
            patch("app.twitch_api._load_channel_profile") as load_profile,
        ):
            with self.assertRaises(twitch_api.TwitchAPIError) as raised:
                twitch_api.exchange_authorization_code(
                    MagicMock(),
                    self.user,
                    "code",
                    [twitch_api.SUBSCRIPTION_SCOPE],
                )

        self.assertEqual(raised.exception.status_code, 403)
        load_profile.assert_not_called()

    def test_disconnect_clears_tokens_even_when_revoke_fails(self):
        with patch(
            "app.twitch_api._read_json_response",
            side_effect=twitch_api.TwitchAPIError("revoke failed", 500),
        ):
            twitch_api.disconnect(self.user)

        self.connection.refresh_from_db()
        self.assertFalse(self.connection.is_connected)
        self.assertEqual(self.connection.scopes, [])

    def test_read_json_response_maps_http_error_message_and_status(self):
        error = urlerror.HTTPError(
            "https://example.com",
            401,
            "error",
            {},
            BytesIO(json.dumps({"status": 401, "message": "invalid access token"}).encode()),
        )

        with patch("app.twitch_api.urlrequest.urlopen", side_effect=error):
            with self.assertRaises(twitch_api.TwitchAPIError) as raised:
                twitch_api._read_json_response(object())

        self.assertEqual(str(raised.exception), "invalid access token")
        self.assertEqual(raised.exception.status_code, 401)

    def test_read_json_response_hides_unparseable_error_body(self):
        error = urlerror.HTTPError("https://example.com", 502, "error", {}, BytesIO(b"<html>"))

        with patch("app.twitch_api.urlrequest.urlopen", side_effect=error):
            with self.assertRaises(twitch_api.TwitchAPIError) as raised:
                twitch_api._read_json_response(object())

        self.assertNotIn("<html>", str(raised.exception))
        self.assertEqual(raised.exception.status_code, 502)

    def test_read_json_response_handles_network_failure(self):
        for failure in (urlerror.URLError("offline"), TimeoutError()):
            with self.subTest(failure=failure):
                with patch("app.twitch_api.urlrequest.urlopen", side_effect=failure):
                    with self.assertRaises(twitch_api.TwitchAPIError) as raised:
                        twitch_api._read_json_response(object())

                self.assertIsNone(raised.exception.status_code)

    def test_read_json_response_handles_empty_and_invalid_bodies(self):
        def response_with(body):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = body
            return response

        with patch("app.twitch_api.urlrequest.urlopen", return_value=response_with(b"")):
            self.assertEqual(twitch_api._read_json_response(object(), allow_empty=True), {})
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api._read_json_response(object())

        with patch("app.twitch_api.urlrequest.urlopen", return_value=response_with(b"not json")):
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api._read_json_response(object())

    @override_settings(TWITCH_CLIENT_ID="", TWITCH_CLIENT_SECRET="")
    def test_token_request_requires_configured_credentials(self):
        with patch("app.twitch_api.urlrequest.urlopen") as urlopen:
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api._token_request({"grant_type": "refresh_token"})

        urlopen.assert_not_called()

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

    def start_oauth_session(self, overlay_id=None, state="expected"):
        session = self.client.session
        session["twitch_oauth"] = {
            "state": state,
            "overlay_id": overlay_id or self.overlay.pk,
            "scopes": [twitch_api.FOLLOWER_SCOPE],
        }
        session.save()

    def test_anonymous_users_are_redirected_to_login(self):
        self.client.logout()
        protected_urls = (
            reverse("twitch_goal_list"),
            reverse("twitch_goal_create"),
            reverse("twitch_goal_manage", args=[self.overlay.pk]),
            reverse("twitch_goal_autosave", args=[self.overlay.pk]),
            reverse("twitch_goal_delete", args=[self.overlay.pk]),
            reverse("twitch_goal_duplicate", args=[self.overlay.pk]),
            reverse("twitch_goal_export", args=[self.overlay.pk]),
            reverse("twitch_goal_renew_obs_link", args=[self.overlay.pk]),
            reverse("twitch_connect", args=[self.overlay.pk]),
            reverse("twitch_callback"),
            reverse("twitch_disconnect"),
            reverse("twitch_goal_campaign_reset", args=[self.overlay.pk]),
            reverse("twitch_goal_replay", args=[self.overlay.pk]),
        )

        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_foreign_overlay_management_routes_return_404_without_changes(self):
        self.client.force_login(self.other)
        public_token = self.overlay.public_token
        requests = (
            ("get", "twitch_goal_manage"),
            ("post", "twitch_goal_manage"),
            ("post", "twitch_goal_autosave"),
            ("post", "twitch_goal_delete"),
            ("post", "twitch_goal_duplicate"),
            ("get", "twitch_goal_export"),
            ("post", "twitch_goal_renew_obs_link"),
            ("get", "twitch_connect"),
            ("post", "twitch_goal_campaign_reset"),
        )

        for method, name in requests:
            with self.subTest(route=name, method=method):
                url = reverse(name, args=[self.overlay.pk])
                response = getattr(self.client, method)(url, form_data(self.overlay, name="X"))
                self.assertEqual(response.status_code, 404)

        self.overlay.refresh_from_db()
        self.assertEqual(self.overlay.name, "Follower Sprint")
        self.assertEqual(self.overlay.public_token, public_token)
        self.assertEqual(TwitchGoalOverlay.objects.count(), 1)
        self.assertNotIn("twitch_oauth", self.client.session)

    def test_callback_cannot_attach_a_connection_to_a_foreign_overlay(self):
        foreign = TwitchGoalOverlay.objects.create(owner=self.other, name="Foreign")
        self.start_oauth_session(overlay_id=foreign.pk)

        with patch("app.twitch_api.exchange_authorization_code") as exchange:
            response = self.client.get(
                reverse("twitch_callback"),
                {"state": "expected", "code": "code"},
            )

        self.assertEqual(response.status_code, 404)
        exchange.assert_not_called()
        foreign.refresh_from_db()
        self.assertIsNone(foreign.connection_id)

    def test_callback_state_is_single_use(self):
        self.start_oauth_session()
        url = reverse("twitch_callback")

        with patch(
            "app.twitch_api.exchange_authorization_code",
            return_value=self.connection,
        ) as exchange:
            first = self.client.get(url, {"state": "expected", "code": "code"})
            replay = self.client.get(url, {"state": "expected", "code": "code"})

        self.assertRedirects(first, reverse("twitch_goal_manage", args=[self.overlay.pk]))
        self.assertRedirects(
            replay,
            f"{reverse('overlay_dashboard')}#twitch-goal-overlays",
            fetch_redirect_response=False,
        )
        exchange.assert_called_once()

    def test_callback_without_session_or_state_is_rejected(self):
        with patch("app.twitch_api.exchange_authorization_code") as exchange:
            no_session = self.client.get(reverse("twitch_callback"), {"code": "code"})
            self.start_oauth_session()
            no_state = self.client.get(reverse("twitch_callback"), {"code": "code"})

        for response in (no_session, no_state):
            self.assertRedirects(
                response,
                f"{reverse('overlay_dashboard')}#twitch-goal-overlays",
                fetch_redirect_response=False,
            )
        exchange.assert_not_called()

    def test_callback_handles_denied_access_and_missing_code(self):
        manage_url = reverse("twitch_goal_manage", args=[self.overlay.pk])

        for params in (
            {"state": "expected", "error": "access_denied"},
            {"state": "expected"},
        ):
            with self.subTest(params=params):
                self.start_oauth_session()
                with patch("app.twitch_api.exchange_authorization_code") as exchange:
                    response = self.client.get(reverse("twitch_callback"), params)

                self.assertRedirects(response, manage_url, fetch_redirect_response=False)
                exchange.assert_not_called()

    def test_callback_reports_exchange_failure_without_upstream_details(self):
        self.overlay.connection = None
        self.overlay.save(update_fields=("connection", "updated_at"))
        self.start_oauth_session()

        with patch(
            "app.twitch_api.exchange_authorization_code",
            side_effect=twitch_api.TwitchAPIError("upstream secret detail", 400),
        ):
            response = self.client.get(
                reverse("twitch_callback"),
                {"state": "expected", "code": "code"},
            )

        error_messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.overlay.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("twitch_goal_manage", args=[self.overlay.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(error_messages), 1)
        self.assertNotIn("upstream secret detail", error_messages[0])
        self.assertIsNone(self.overlay.connection_id)

    def test_callback_links_the_connection_on_success(self):
        self.overlay.connection = None
        self.overlay.save(update_fields=("connection", "updated_at"))
        self.start_oauth_session()

        with patch(
            "app.twitch_api.exchange_authorization_code",
            return_value=self.connection,
        ) as exchange:
            self.client.get(reverse("twitch_callback"), {"state": "expected", "code": "code"})

        self.overlay.refresh_from_db()
        self.assertEqual(self.overlay.connection, self.connection)
        self.assertEqual(exchange.call_args.args[2:], ("code", [twitch_api.FOLLOWER_SCOPE]))

    @override_settings(TWITCH_CLIENT_ID="", TWITCH_CLIENT_SECRET="")
    def test_connect_without_credentials_redirects_back_to_editor(self):
        response = self.client.get(reverse("twitch_connect", args=[self.overlay.pk]))

        self.assertRedirects(
            response,
            reverse("twitch_goal_manage", args=[self.overlay.pk]),
            fetch_redirect_response=False,
        )
        self.assertNotIn("twitch_oauth", self.client.session)

    def test_disconnect_ignores_external_next_url(self):
        with patch("app.twitch_api._read_json_response", return_value={}):
            response = self.client.post(
                reverse("twitch_disconnect"),
                {"next": "https://evil.example/phish"},
            )

        self.assertRedirects(response, reverse("overlay_dashboard"))

    def test_disconnect_and_mutations_require_post(self):
        for url in (
            reverse("twitch_disconnect"),
            reverse("twitch_goal_autosave", args=[self.overlay.pk]),
            reverse("twitch_goal_delete", args=[self.overlay.pk]),
            reverse("twitch_goal_campaign_reset", args=[self.overlay.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

        self.connection.refresh_from_db()
        self.assertTrue(self.connection.is_connected)
        self.assertTrue(TwitchGoalOverlay.objects.filter(pk=self.overlay.pk).exists())

    def test_create_attaches_the_owner_connection_and_records_a_version(self):
        candidate = TwitchGoalOverlay(owner=self.user)
        response = self.client.post(
            reverse("twitch_goal_create"),
            form_data(candidate, name="New Goal"),
        )

        created = TwitchGoalOverlay.objects.get(name="New Goal")
        self.assertRedirects(response, reverse("twitch_goal_manage", args=[created.pk]))
        self.assertEqual(created.owner, self.user)
        self.assertEqual(created.connection, self.connection)
        self.assertEqual(overlay_versions.versions_for(created).count(), 1)

    def test_create_with_invalid_data_rerenders_without_saving(self):
        candidate = TwitchGoalOverlay(owner=self.user)
        response = self.client.post(
            reverse("twitch_goal_create"),
            form_data(candidate, name="Broken", target_value=0),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(TwitchGoalOverlay.objects.filter(name="Broken").exists())

    def test_manage_post_saves_valid_and_rejects_invalid_data(self):
        url = reverse("twitch_goal_manage", args=[self.overlay.pk])

        invalid = self.client.post(
            url, form_data(self.overlay, target_value=0, background_color="nope")
        )
        self.overlay.refresh_from_db()
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(self.overlay.target_value, 100)
        self.assertNotEqual(self.overlay.background_color, "nope")

        valid = self.client.post(url, form_data(self.overlay, name="Renamed"))
        self.overlay.refresh_from_db()
        self.assertRedirects(valid, url)
        self.assertEqual(self.overlay.name, "Renamed")

    def test_autosave_returns_400_for_invalid_data_and_records_valid_saves(self):
        url = reverse("twitch_goal_autosave", args=[self.overlay.pk])

        invalid = self.client.post(url, form_data(self.overlay, elements="not json"))
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(invalid.json()["ok"])
        self.assertIn("elements", invalid.json()["errors"])
        self.assertEqual(overlay_versions.versions_for(self.overlay).count(), 0)

        valid = self.client.post(url, form_data(self.overlay, name="Autosaved"))
        self.overlay.refresh_from_db()
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(valid.json()["ok"])
        self.assertEqual(self.overlay.name, "Autosaved")
        self.assertEqual(overlay_versions.versions_for(self.overlay).count(), 1)

    def test_delete_removes_overlay_and_its_versions(self):
        overlay_versions.record_version(self.overlay)

        response = self.client.post(reverse("twitch_goal_delete", args=[self.overlay.pk]))

        self.assertRedirects(response, f"{reverse('overlay_dashboard')}#twitch-goal-overlays")
        self.assertFalse(TwitchGoalOverlay.objects.filter(pk=self.overlay.pk).exists())
        self.assertFalse(
            OverlayVersion.objects.filter(
                overlay_type=overlay_transfer.TWITCH_GOAL_TYPE,
                overlay_id=self.overlay.pk,
            ).exists()
        )
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.is_connected)

    def test_renew_obs_link_invalidates_the_old_public_url(self):
        old_url = reverse("twitch_goal_overlay_state", args=[self.overlay.public_token])

        self.client.post(reverse("twitch_goal_renew_obs_link", args=[self.overlay.pk]))
        self.overlay.refresh_from_db()

        self.assertEqual(self.client.get(old_url).status_code, 404)
        new_url = reverse("twitch_goal_overlay_state", args=[self.overlay.public_token])
        self.assertEqual(self.client.get(new_url).status_code, 200)

    def test_campaign_reset_requires_connection_and_metric_value(self):
        url = reverse("twitch_goal_campaign_reset", args=[self.overlay.pk])
        self.overlay.progress_mode = TwitchGoalOverlay.MODE_CAMPAIGN
        self.overlay.connection = None
        self.overlay.save(update_fields=("progress_mode", "connection", "updated_at"))

        not_connected = self.client.post(url)
        self.assertEqual(not_connected.status_code, 409)

        self.overlay.connection = self.connection
        self.overlay.save(update_fields=("connection", "updated_at"))
        self.connection.follower_count = None
        self.connection.save(update_fields=("follower_count", "updated_at"))
        no_value = self.client.post(url)

        self.overlay.refresh_from_db()
        self.assertEqual(no_value.status_code, 409)
        self.assertIsNone(self.overlay.campaign_baseline)
        self.assertEqual(self.overlay.goal_revision, 1)

    def test_public_routes_return_404_for_unknown_tokens(self):
        self.client.logout()
        unknown = "00000000-0000-0000-0000-000000000000"

        for name in ("twitch_goal_overlay", "twitch_goal_overlay_state"):
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name, args=[unknown])).status_code, 404)
