import hashlib
import hmac
import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app import overlay_transfer, overlay_versions, twitch_api
from app.models import (
    OverlayVersion,
    TwitchAlertEvent,
    TwitchAlertOverlay,
    TwitchConnection,
)

User = get_user_model()


def form_data(overlay, **overrides):
    data = {field: getattr(overlay, field) for field in overlay_transfer.TWITCH_ALERT_FIELDS}
    data = {key: value for key, value in data.items() if value is not False}
    data.update({"font_asset": "", "logo_asset": "", "background_asset": ""})
    data.update(overrides)
    return data


def signed_headers(
    body, message_type="notification", message_id="message-1", sent_at=None, timestamp=None
):
    timestamp = timestamp or (sent_at or timezone.now()).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")
    signature = hmac.new(
        twitch_api.eventsub_secret().encode(),
        message_id.encode() + timestamp.encode() + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "HTTP_TWITCH_EVENTSUB_MESSAGE_ID": message_id,
        "HTTP_TWITCH_EVENTSUB_MESSAGE_TIMESTAMP": timestamp,
        "HTTP_TWITCH_EVENTSUB_MESSAGE_SIGNATURE": f"sha256={signature}",
        "HTTP_TWITCH_EVENTSUB_MESSAGE_TYPE": message_type,
    }


def notification(subscription_type, event, broadcaster_id="1234"):
    condition_key = (
        "to_broadcaster_user_id" if subscription_type == "channel.raid" else "broadcaster_user_id"
    )
    return {
        "subscription": {
            "id": f"sub-{subscription_type}",
            "type": subscription_type,
            "condition": {condition_key: broadcaster_id},
        },
        "event": event,
    }


class TwitchAlertModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alert-model-owner")
        self.overlay = TwitchAlertOverlay.objects.create(owner=self.user, name="Alerts")

    def event(self, event_type, amount=0, **values):
        return TwitchAlertEvent.objects.create(
            owner=self.user,
            message_id=f"{event_type}-{TwitchAlertEvent.objects.count()}",
            event_type=event_type,
            amount=amount,
            **values,
        )

    def test_state_lists_recent_events_filtered_by_type_and_thresholds(self):
        self.overlay.show_follows = False
        self.overlay.minimum_bits = 100
        self.overlay.minimum_raid_viewers = 10
        self.overlay.save()
        self.event("follow", user_name="Hidden")
        self.event("cheer", 50, user_name="SmallCheer")
        self.event("cheer", 100, user_name="BigCheer")
        self.event("raid", 9, user_name="SmallRaid")
        self.event("raid", 10, user_name="BigRaid")
        self.event(
            "subscription", 1, user_name="Old", created_at=timezone.now() - timedelta(hours=1)
        )
        other = User.objects.create_user(username="alert-model-other")
        TwitchAlertEvent.objects.create(
            owner=other, message_id="foreign", event_type="subscription", user_name="Foreign"
        )

        names = [event["name"] for event in self.overlay.state_payload()["events"]]

        self.assertEqual(names, ["BigCheer", "BigRaid"])

    def test_hidden_events_cannot_push_shown_alerts_out_of_the_limit(self):
        self.overlay.show_follows = False
        self.overlay.save()
        self.event("cheer", 500, user_name="Cheerer")
        for _index in range(25):
            self.event("follow", user_name="FollowBot")

        names = [event["name"] for event in self.overlay.state_payload()["events"]]

        self.assertEqual(names, ["Cheerer"])

    def test_texts_fall_back_to_defaults_and_anonymous_names_are_labeled(self):
        self.overlay.raid_text = "  {name} brings {amount} friends  "
        texts = self.overlay.alert_texts()
        event = self.event("gift", 5, user_name="")

        self.assertEqual(texts["raid"], "{name} brings {amount} friends")
        self.assertIn("{name}", texts["follow"])
        self.assertEqual(len(texts), 5)
        self.assertEqual(event.payload()["name"], "Anonym")


class TwitchAlertEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alert-owner")
        self.client.force_login(self.user)
        self.overlay = TwitchAlertOverlay.objects.create(owner=self.user, name="Stream Alerts")

    def test_create_assigns_owner_and_records_version(self):
        response = self.client.post(
            reverse("twitch_alert_create"),
            form_data(TwitchAlertOverlay(), name="New Alerts"),
        )

        created = TwitchAlertOverlay.objects.get(name="New Alerts")
        self.assertRedirects(response, reverse("twitch_alert_manage", args=[created.pk]))
        self.assertEqual(created.owner, self.user)
        self.assertTrue(overlay_versions.versions_for(created).exists())

    def test_editor_pages_render(self):
        for url in (
            reverse("twitch_alert_create"),
            reverse("twitch_alert_manage", args=[self.overlay.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "data-alert-editor")
                self.assertContains(response, 'data-alert-test="raid"')

    @override_settings(TWITCH_CLIENT_ID="client-id", TWITCH_CLIENT_SECRET="client-secret")
    def test_manage_shows_connection_state(self):
        response = self.client.get(reverse("twitch_alert_manage", args=[self.overlay.pk]))
        self.assertNotContains(response, reverse("twitch_alert_activate", args=[self.overlay.pk]))

        TwitchConnection.objects.create(
            owner=self.user,
            access_token="token",
            twitch_login="streamer",
            scopes=[twitch_api.FOLLOWER_SCOPE],
            eventsub_subscriptions={"channel.raid": "id", "channel.follow": "id-2"},
        )
        response = self.client.get(reverse("twitch_alert_manage", args=[self.overlay.pk]))

        self.assertContains(response, reverse("twitch_alert_activate", args=[self.overlay.pk]))
        self.assertContains(response, reverse("twitch_alert_connect", args=[self.overlay.pk]))
        self.assertContains(response, "2 Twitch-Ereignistypen sind aktiv.")

    def test_autosave_validates_and_saves(self):
        url = reverse("twitch_alert_autosave", args=[self.overlay.pk])
        invalid = self.client.post(url, form_data(self.overlay, alert_duration_seconds=99))
        valid = self.client.post(url, form_data(self.overlay, cheer_text="{name}: {amount}!"))

        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(invalid.json()["ok"])
        self.assertIn("alert_duration_seconds", invalid.json()["errors"])
        self.assertTrue(valid.json()["ok"])
        self.overlay.refresh_from_db()
        self.assertEqual(self.overlay.cheer_text, "{name}: {amount}!")

    def test_test_alert_creates_event_for_obs(self):
        url = reverse("twitch_alert_test", args=[self.overlay.pk])
        response = self.client.post(url, {"event_type": "cheer"})
        rejected = self.client.post(url, {"event_type": "hack"})

        self.assertEqual(response.json()["event"]["amount"], 500)
        self.assertEqual(rejected.status_code, 400)
        event = TwitchAlertEvent.objects.get()
        self.assertTrue(event.is_test)
        self.assertEqual(event.owner, self.user)

    def test_public_state_supports_conditional_requests_and_new_events(self):
        url = reverse("twitch_alert_overlay_state", args=[self.overlay.public_token])
        self.client.logout()
        first = self.client.get(url)
        cached = self.client.get(url, HTTP_IF_NONE_MATCH=first["ETag"])
        TwitchAlertEvent.objects.create(
            owner=self.user, message_id="new", event_type="follow", user_name="Viewer"
        )
        changed = self.client.get(url, HTTP_IF_NONE_MATCH=first["ETag"])

        self.assertEqual(first.status_code, 200)
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["events"][0]["name"], "Viewer")

    def test_export_import_duplicate_and_restore_round_trip(self):
        self.overlay.raid_text = "Raid by {name}"
        self.overlay.save()
        exported = self.client.get(reverse("twitch_alert_export", args=[self.overlay.pk]))
        payload = json.loads(exported.content)
        imported = overlay_transfer.import_payload(payload, self.user)
        duplicate = overlay_transfer.duplicate_overlay(self.overlay, self.user, "Copy")

        self.assertEqual(payload["type"], overlay_transfer.TWITCH_ALERT_TYPE)
        self.assertEqual(imported.raid_text, "Raid by {name}")
        self.assertEqual(duplicate.name, "Stream Alerts (Copy)")

        version, _created = overlay_versions.record_version(
            self.overlay, OverlayVersion.REASON_MANUAL
        )
        self.overlay.raid_text = "Changed"
        self.overlay.save()
        overlay_versions.restore_version(self.overlay, version)
        self.overlay.refresh_from_db()
        self.assertEqual(self.overlay.raid_text, "Raid by {name}")

    def test_dashboard_lists_alert_overlays(self):
        response = self.client.get(reverse("overlay_dashboard"))

        self.assertContains(response, 'id="twitch-alert-overlays"')
        self.assertContains(response, reverse("twitch_alert_manage", args=[self.overlay.pk]))

    def test_dashboard_import_lands_on_alert_section(self):
        payload = json.dumps(overlay_transfer.twitch_alert_export_payload(self.overlay)).encode()
        upload = BytesIO(payload)
        upload.name = "alerts.json"

        response = self.client.post(reverse("overlay_import"), {"overlay_file": upload})

        self.assertRedirects(response, f"{reverse('overlay_dashboard')}#twitch-alert-overlays")
        self.assertEqual(TwitchAlertOverlay.objects.count(), 2)


class TwitchAlertAccessControlTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="alert-access-owner")
        self.other = User.objects.create_user(username="alert-access-other")
        self.overlay = TwitchAlertOverlay.objects.create(owner=self.owner, name="Private Alerts")

    def test_public_page_and_state_work_without_login(self):
        page = self.client.get(reverse("twitch_alert_overlay", args=[self.overlay.public_token]))
        state = self.client.get(
            reverse("twitch_alert_overlay_state", args=[self.overlay.public_token])
        )

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-alert-source")
        self.assertIn("no-store", page["Cache-Control"])
        self.assertEqual(state.json()["name"], "Private Alerts")

    def test_anonymous_users_are_redirected_to_login(self):
        for name in ("twitch_alert_list", "twitch_alert_create"):
            url = reverse(name)
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")
        for name in ("twitch_alert_manage", "twitch_alert_connect", "twitch_alert_export"):
            url = reverse(name, args=[self.overlay.pk])
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_foreign_overlay_routes_return_404_without_changes(self):
        self.client.force_login(self.other)
        requests = (
            ("get", "twitch_alert_manage"),
            ("post", "twitch_alert_manage"),
            ("post", "twitch_alert_autosave"),
            ("post", "twitch_alert_delete"),
            ("post", "twitch_alert_duplicate"),
            ("get", "twitch_alert_export"),
            ("post", "twitch_alert_renew_obs_link"),
            ("get", "twitch_alert_connect"),
            ("post", "twitch_alert_activate"),
            ("post", "twitch_alert_test"),
        )
        public_token = self.overlay.public_token

        for method, name in requests:
            with self.subTest(route=name, method=method):
                url = reverse(name, args=[self.overlay.pk])
                response = getattr(self.client, method)(url, form_data(self.overlay, name="X"))
                self.assertEqual(response.status_code, 404)

        self.overlay.refresh_from_db()
        self.assertEqual(self.overlay.name, "Private Alerts")
        self.assertEqual(self.overlay.public_token, public_token)
        self.assertFalse(TwitchAlertEvent.objects.exists())


class TwitchEventSubWebhookTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="eventsub-owner")
        self.connection = TwitchConnection.objects.create(
            owner=self.owner,
            access_token="token",
            twitch_user_id="1234",
            eventsub_subscriptions={"channel.raid": "sub-channel.raid"},
        )
        self.url = reverse("twitch_eventsub_callback")

    def post(self, payload, **header_options):
        body = json.dumps(payload).encode()
        return self.client.post(
            self.url,
            body,
            content_type="application/json",
            **signed_headers(body, **header_options),
        )

    def test_verification_returns_the_challenge(self):
        response = self.post(
            {"challenge": "pogchamp-kappa"}, message_type="webhook_callback_verification"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"pogchamp-kappa")

    def test_invalid_or_stale_signatures_are_rejected(self):
        body = json.dumps(notification("channel.follow", {"user_name": "Viewer"})).encode()
        headers = signed_headers(body)
        headers["HTTP_TWITCH_EVENTSUB_MESSAGE_SIGNATURE"] = "sha256=" + "0" * 64
        forged = self.client.post(self.url, body, content_type="application/json", **headers)
        stale = self.post(
            notification("channel.follow", {"user_name": "Viewer"}),
            sent_at=timezone.now() - timedelta(minutes=11),
        )
        unsigned = self.client.post(self.url, body, content_type="application/json")

        self.assertEqual(forged.status_code, 403)
        self.assertEqual(stale.status_code, 403)
        self.assertEqual(unsigned.status_code, 403)
        self.assertFalse(TwitchAlertEvent.objects.exists())

    def test_timestamps_without_offset_or_impossible_dates_are_rejected(self):
        body = json.dumps(notification("channel.follow", {"user_name": "Viewer"})).encode()
        timestamps = (
            timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "2026-13-40T10:00:00Z",
        )
        for timestamp in timestamps:
            with self.subTest(timestamp=timestamp):
                response = self.client.post(
                    self.url,
                    body,
                    content_type="application/json",
                    **signed_headers(body, timestamp=timestamp),
                )

                self.assertEqual(response.status_code, 403)
        self.assertFalse(TwitchAlertEvent.objects.exists())

    def test_notifications_become_alert_events_once(self):
        payloads = (
            ("follow", notification("channel.follow", {"user_name": "Follower"})),
            ("sub", notification("channel.subscribe", {"user_name": "Sub", "is_gift": False})),
            ("gifted", notification("channel.subscribe", {"user_name": "Gifted", "is_gift": True})),
            (
                "resub",
                notification(
                    "channel.subscription.message",
                    {"user_name": "Resub", "cumulative_months": 7, "message": {"text": "Hi"}},
                ),
            ),
            (
                "gift",
                notification(
                    "channel.subscription.gift",
                    {"user_name": "Secret", "total": 5, "is_anonymous": True},
                ),
            ),
            (
                "cheer",
                notification(
                    "channel.cheer", {"user_name": "Cheerer", "bits": 300, "message": "GG"}
                ),
            ),
            (
                "raid",
                notification(
                    "channel.raid", {"from_broadcaster_user_name": "Raider", "viewers": 25}
                ),
            ),
            ("other", notification("channel.follow", {"user_name": "Nobody"}, broadcaster_id="9")),
        )
        for message_id, payload in payloads:
            self.assertEqual(self.post(payload, message_id=message_id).status_code, 204)
        self.post(payloads[0][1], message_id="follow")

        events = {
            event.user_name: (event.event_type, event.amount, event.message)
            for event in TwitchAlertEvent.objects.filter(owner=self.owner)
        }
        self.assertEqual(
            events,
            {
                "Follower": ("follow", 0, ""),
                "Sub": ("subscription", 1, ""),
                "Resub": ("subscription", 7, "Hi"),
                "": ("gift", 5, ""),
                "Cheerer": ("cheer", 300, "GG"),
                "Raider": ("raid", 25, ""),
            },
        )

    def test_old_events_are_pruned_and_revocations_are_forgotten(self):
        twitch_api.cache.delete(twitch_api.ALERT_PRUNE_CACHE_KEY)
        TwitchAlertEvent.objects.create(
            owner=self.owner,
            message_id="ancient",
            event_type="follow",
            created_at=timezone.now() - timedelta(days=2),
        )
        self.post(notification("channel.follow", {"user_name": "Fresh"}), message_id="fresh")
        revoked = self.post(
            {"subscription": {"id": "sub-channel.raid", "status": "authorization_revoked"}},
            message_type="revocation",
            message_id="revoke",
        )

        self.assertEqual(revoked.status_code, 204)
        self.assertEqual(
            list(TwitchAlertEvent.objects.values_list("message_id", flat=True)),
            [f"fresh:{self.owner.pk}"],
        )
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.eventsub_subscriptions, {})

    def test_pruning_runs_at_most_once_per_interval(self):
        twitch_api.cache.delete(twitch_api.ALERT_PRUNE_CACHE_KEY)
        self.post(notification("channel.follow", {"user_name": "First"}), message_id="first")
        TwitchAlertEvent.objects.create(
            owner=self.owner,
            message_id="ancient",
            event_type="follow",
            created_at=timezone.now() - timedelta(days=2),
        )

        self.post(notification("channel.follow", {"user_name": "Second"}), message_id="second")

        self.assertTrue(TwitchAlertEvent.objects.filter(message_id="ancient").exists())

    def test_get_and_malformed_bodies_are_rejected(self):
        body = b"not json"
        malformed = self.client.post(
            self.url, body, content_type="application/json", **signed_headers(body)
        )

        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(malformed.status_code, 400)


@override_settings(
    TWITCH_CLIENT_ID="client-id",
    TWITCH_CLIENT_SECRET="client-secret",
    TWITCH_REDIRECT_URI="https://nexora.example/goals/twitch/callback/",
)
class TwitchAlertSubscriptionTests(TestCase):
    CALLBACK = "https://nexora.example/twitch/eventsub/"

    def setUp(self):
        self.owner = User.objects.create_user(username="sync-owner")
        self.client.force_login(self.owner)
        self.connection = TwitchConnection.objects.create(
            owner=self.owner,
            access_token="token",
            twitch_user_id="1234",
            twitch_login="streamer",
            scopes=[twitch_api.FOLLOWER_SCOPE],
            validated_at=timezone.now(),
        )
        self.overlay = TwitchAlertOverlay.objects.create(owner=self.owner)

    def test_callback_url_uses_the_public_redirect_origin(self):
        self.assertEqual(twitch_api.eventsub_callback_url(None), self.CALLBACK)

    def test_sync_recreates_only_subscriptions_the_scopes_allow(self):
        existing = {
            "data": [
                {
                    "id": "raid-id",
                    "type": "channel.raid",
                    "status": "enabled",
                    "transport": {"callback": self.CALLBACK},
                },
                {
                    "id": "broken-id",
                    "type": "channel.follow",
                    "status": "notification_failures_exceeded",
                    "transport": {"callback": self.CALLBACK},
                },
                {
                    "id": "unscoped-id",
                    "type": "channel.cheer",
                    "status": "enabled",
                    "transport": {"callback": self.CALLBACK},
                },
                {
                    "id": "elsewhere",
                    "type": "channel.cheer",
                    "status": "enabled",
                    "transport": {"callback": "https://other.example/hook/"},
                },
            ]
        }
        calls = []

        def fake_request(method, url, params=None, body=None, allow_empty=False):
            calls.append((method, params, body))
            if method == "GET":
                return existing
            if method == "POST":
                return {"data": [{"id": f"new-{body['type']}"}]}
            return {}

        with patch("app.twitch_api._app_api_request", side_effect=fake_request):
            active = twitch_api.sync_alert_subscriptions(self.connection, self.CALLBACK)

        self.assertEqual(sorted(active), ["channel.follow", "channel.raid"])
        deleted = [params["id"] for method, params, _body in calls if method == "DELETE"]
        # Existing ones are recreated, since their secret may be outdated; foreign callbacks stay.
        self.assertEqual(sorted(deleted), ["broken-id", "raid-id", "unscoped-id"])
        created = {body["type"]: body for method, _params, body in calls if method == "POST"}
        self.assertEqual(sorted(created), ["channel.follow", "channel.raid"])
        self.assertEqual(
            created["channel.follow"]["condition"],
            {"broadcaster_user_id": "1234", "moderator_user_id": "1234"},
        )
        self.assertEqual(
            created["channel.raid"]["transport"]["secret"], twitch_api.eventsub_secret()
        )
        self.connection.refresh_from_db()
        self.assertEqual(
            self.connection.eventsub_subscriptions,
            {"channel.follow": "new-channel.follow", "channel.raid": "new-channel.raid"},
        )

    def test_accounts_on_the_same_channel_share_subscriptions(self):
        other = TwitchConnection.objects.create(
            owner=User.objects.create_user(username="sync-co-owner"),
            access_token="token",
            twitch_user_id="1234",
            eventsub_subscriptions={"channel.raid": "stale-id"},
        )

        def fake_request(method, url, params=None, body=None, allow_empty=False):
            if method == "POST":
                return {"data": [{"id": f"new-{body['type']}"}]}
            return {"data": []}

        with patch("app.twitch_api._app_api_request", side_effect=fake_request):
            twitch_api.sync_alert_subscriptions(self.connection, self.CALLBACK)
        other.refresh_from_db()
        self.assertEqual(
            other.eventsub_subscriptions,
            {"channel.follow": "new-channel.follow", "channel.raid": "new-channel.raid"},
        )

        with (
            patch("app.twitch_api._app_api_request") as request,
            patch("app.twitch_api._read_json_response", return_value={}),
        ):
            twitch_api.disconnect(self.owner)
        request.assert_not_called()
        other.refresh_from_db()
        self.assertEqual(len(other.eventsub_subscriptions), 2)

    def test_sync_refuses_non_https_callbacks_and_records_api_errors(self):
        with self.assertRaises(twitch_api.TwitchAPIError):
            twitch_api.sync_alert_subscriptions(
                self.connection, "http://localhost/twitch/eventsub/"
            )

        with patch(
            "app.twitch_api._app_api_request",
            side_effect=twitch_api.TwitchAPIError("Twitch says no", 400),
        ):
            with self.assertRaises(twitch_api.TwitchAPIError):
                twitch_api.sync_alert_subscriptions(self.connection, self.CALLBACK)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.eventsub_error, "Twitch says no")

    def test_activate_view_reports_success_and_failure(self):
        url = reverse("twitch_alert_activate", args=[self.overlay.pk])
        with patch(
            "app.twitch_api.sync_alert_subscriptions", return_value=["channel.raid"]
        ) as sync:
            ok = self.client.post(url, follow=True)
        with patch(
            "app.twitch_api.sync_alert_subscriptions",
            side_effect=twitch_api.TwitchAPIError("no"),
        ):
            failed = self.client.post(url, follow=True)

        sync.assert_called_once_with(self.connection, self.CALLBACK)
        self.assertContains(ok, "Twitch-Alerts sind aktiv.")
        self.assertContains(failed, "Twitch-Alerts konnten nicht aktiviert werden.")

    def test_activate_requires_a_connection(self):
        self.connection.delete()
        response = self.client.post(
            reverse("twitch_alert_activate", args=[self.overlay.pk]), follow=True
        )

        self.assertContains(response, "Verbinde zuerst Twitch.")

    def test_connect_requests_alert_scopes_and_callback_activates_alerts(self):
        response = self.client.get(reverse("twitch_alert_connect", args=[self.overlay.pk]))
        oauth = self.client.session["twitch_oauth"]

        self.assertEqual(oauth["alert_id"], self.overlay.pk)
        self.assertTrue(set(twitch_api.ALERT_SCOPES).issubset(oauth["scopes"]))
        self.assertIn("bits%3Aread", response["Location"])

        with (
            patch(
                "app.twitch_api.exchange_authorization_code", return_value=self.connection
            ) as exchange,
            patch("app.twitch_api.sync_alert_subscriptions", return_value=[]) as sync,
        ):
            callback = self.client.get(
                reverse("twitch_callback"), {"state": oauth["state"], "code": "code"}
            )

        self.assertRedirects(callback, reverse("twitch_alert_manage", args=[self.overlay.pk]))
        exchange.assert_called_once()
        sync.assert_called_once()

    @override_settings(TWITCH_REDIRECT_URI="http://localhost:8000/goals/twitch/callback/")
    def test_callback_without_public_https_connects_without_activation_error(self):
        self.client.get(reverse("twitch_alert_connect", args=[self.overlay.pk]))
        oauth = self.client.session["twitch_oauth"]

        with (
            patch("app.twitch_api.exchange_authorization_code", return_value=self.connection),
            patch("app.twitch_api.sync_alert_subscriptions") as sync,
        ):
            callback = self.client.get(
                reverse("twitch_callback"),
                {"state": oauth["state"], "code": "code"},
                follow=True,
            )

        sync.assert_not_called()
        self.assertNotContains(callback, "Twitch-Alerts konnten nicht aktiviert werden.")

    def test_failed_alert_verification_returns_to_the_alert_section(self):
        session = self.client.session
        session["twitch_oauth"] = {"state": "expected", "alert_id": self.overlay.pk}
        session.save()

        response = self.client.get(reverse("twitch_callback"), {"state": "wrong", "code": "c"})

        self.assertRedirects(
            response,
            f"{reverse('overlay_dashboard')}#twitch-alert-overlays",
            fetch_redirect_response=False,
        )

    def test_disconnect_deletes_alert_subscriptions(self):
        self.connection.eventsub_subscriptions = {"channel.raid": "raid-id"}
        self.connection.save()

        with (
            patch("app.twitch_api._app_api_request") as request,
            patch("app.twitch_api._read_json_response", return_value={}),
        ):
            twitch_api.disconnect(self.owner)

        request.assert_called_once_with(
            "DELETE", twitch_api.EVENTSUB_URL, {"id": "raid-id"}, allow_empty=True
        )
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.eventsub_subscriptions, {})

    def test_app_token_is_cached_and_refreshed_after_401(self):
        tokens = iter(({"access_token": "app-1"}, {"access_token": "app-2"}))
        sent = []

        def fake_read(request, allow_empty=False):
            if "oauth2/token" in request.full_url:
                return next(tokens)
            sent.append(request.headers["Authorization"])
            if len(sent) == 1:
                raise twitch_api.TwitchAPIError("expired", 401)
            return {"data": []}

        twitch_api.cache.delete(twitch_api.APP_TOKEN_CACHE_KEY)
        with patch("app.twitch_api._read_json_response", side_effect=fake_read):
            result = twitch_api._app_api_request("GET", twitch_api.EVENTSUB_URL, {"user_id": "1"})
            twitch_api._app_api_request("GET", twitch_api.EVENTSUB_URL)

        self.assertEqual(result, {"data": []})
        self.assertEqual(sent, ["Bearer app-1", "Bearer app-2", "Bearer app-2"])
        twitch_api.cache.delete(twitch_api.APP_TOKEN_CACHE_KEY)
