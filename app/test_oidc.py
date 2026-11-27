import base64
import json
import time
from unittest.mock import MagicMock, patch
from urllib import error as urlerror
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import OIDCIdentity
from app.views.oidc import ID_TOKEN_SESSION_KEY, LOGIN_SESSION_KEY

ISSUER = "https://auth.example.test/realms/yfserver"
OIDC_SETTINGS = {
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": "nexora",
    "OIDC_CLIENT_SECRET": "client-secret",
    "OIDC_REQUIRED_GROUP": "",
}


def fake_id_token(**overrides):
    claims = {
        "iss": ISSUER,
        "aud": "nexora",
        "exp": time.time() + 300,
        "nonce": "the-nonce",
        "sub": "kc-user-1",
        "email": "streamer@example.com",
        "email_verified": True,
        "preferred_username": "streamer@example.com",
    }
    claims.update(overrides)
    claims = {key: value for key, value in claims.items() if value is not None}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


def token_response(id_token):
    response = MagicMock()
    response.read.return_value = json.dumps({"id_token": id_token}).encode()
    response.__enter__.return_value = response
    return response


@override_settings(**OIDC_SETTINGS)
class OIDCLoginTests(TestCase):
    def start_login(self, next_url="/overlays/"):
        response = self.client.get(reverse("oidc_login"), {"next": next_url})
        session = self.client.session
        login_session = session[LOGIN_SESSION_KEY]
        login_session["nonce"] = "the-nonce"
        session[LOGIN_SESSION_KEY] = login_session
        session.save()
        return response, login_session

    def finish_login(self, id_token=None, state=None):
        _, login_session = self.start_login()
        with patch("app.oidc.urlrequest.urlopen") as urlopen:
            urlopen.return_value = token_response(id_token or fake_id_token())
            response = self.client.get(
                reverse("oidc_callback"),
                {"state": state or login_session["state"], "code": "auth-code"},
            )
        return response, urlopen

    def assert_rejected(self, response):
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(list(get_messages(response.wsgi_request)))

    def test_login_page_offers_central_sign_in(self):
        response = self.client.get(reverse("login"), {"next": "/overlays/"})
        self.assertContains(response, reverse("oidc_login") + "?next=/overlays/")

    @override_settings(OIDC_CLIENT_SECRET="")
    def test_central_sign_in_is_hidden_and_unreachable_when_not_configured(self):
        self.assertNotContains(self.client.get(reverse("login")), reverse("oidc_login"))
        self.assertEqual(self.client.get(reverse("oidc_login")).status_code, 404)
        self.assertEqual(self.client.get(reverse("oidc_callback")).status_code, 404)

    def test_login_redirects_to_keycloak_with_state_nonce_and_pkce(self):
        response, login_session = self.start_login()
        location = urlsplit(response["Location"])
        query = parse_qs(location.query)
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}",
            f"{ISSUER}/protocol/openid-connect/auth",
        )
        self.assertEqual(query["state"], [login_session["state"]])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], ["http://testserver/accounts/oidc/callback/"])
        self.assertEqual(login_session["next"], "/overlays/")

    def test_login_ignores_foreign_next_url(self):
        _, login_session = self.start_login(next_url="https://evil.example/")
        self.assertEqual(login_session["next"], reverse("home"))

    def test_callback_creates_and_signs_in_new_user(self):
        response, urlopen = self.finish_login()
        self.assertRedirects(response, "/overlays/", fetch_redirect_response=False)
        user = get_user_model().objects.get(email="streamer@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.oidc_identity.subject, "kc-user-1")
        self.assertIn(ID_TOKEN_SESSION_KEY, self.client.session)
        token_request = urlopen.call_args.args[0]
        sent = parse_qs(token_request.data.decode())
        self.assertEqual(sent["client_secret"], ["client-secret"])
        self.assertIn("code_verifier", sent)
        self.assertTrue(token_request.get_header("User-agent").startswith("Nexora/"))

    def test_callback_links_existing_account_by_verified_email(self):
        existing = get_user_model().objects.create_user("local", "Streamer@Example.com", "pw")
        self.finish_login()
        self.assertEqual(int(self.client.session["_auth_user_id"]), existing.pk)
        self.assertEqual(OIDCIdentity.objects.get().user, existing)

    def test_callback_does_not_link_by_unverified_email(self):
        existing = get_user_model().objects.create_user("local", "streamer@example.com", "pw")
        self.finish_login(fake_id_token(email_verified=False))
        self.assertNotEqual(int(self.client.session["_auth_user_id"]), existing.pk)
        self.assertNotEqual(OIDCIdentity.objects.get().user, existing)

    def test_returning_user_is_found_by_subject(self):
        user = get_user_model().objects.create_user("renamed")
        OIDCIdentity.objects.create(user=user, subject="kc-user-1")
        self.finish_login(fake_id_token(email="new@example.com"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_new_username_avoids_collisions(self):
        get_user_model().objects.create_user("streamer@example.com", "other@example.com")
        self.finish_login(fake_id_token(email_verified=False))
        self.assertTrue(get_user_model().objects.filter(username="streamer@example.com-2").exists())

    def test_admin_group_controls_admin_rights(self):
        self.finish_login(fake_id_token(groups=["admins"]))
        user = get_user_model().objects.get()
        self.assertTrue(user.is_staff and user.is_superuser)
        self.client.logout()
        self.finish_login(fake_id_token(groups=[]))
        user.refresh_from_db()
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_admin_rights_stay_when_no_groups_are_sent(self):
        user = get_user_model().objects.create_superuser("boss", "streamer@example.com", "pw")
        self.finish_login()
        user.refresh_from_db()
        self.assertTrue(user.is_superuser)

    @override_settings(OIDC_REQUIRED_GROUP="dev-access")
    def test_required_group_is_enforced(self):
        response, _ = self.finish_login(fake_id_token(groups=["admins"]))
        self.assert_rejected(response)
        response, _ = self.finish_login(fake_id_token(groups=["dev-access"]))
        self.assertIn("_auth_user_id", self.client.session)

    def test_inactive_user_is_rejected(self):
        user = get_user_model().objects.create_user("gone", is_active=False)
        OIDCIdentity.objects.create(user=user, subject="kc-user-1")
        response, _ = self.finish_login()
        self.assert_rejected(response)

    def test_state_mismatch_is_rejected_without_token_request(self):
        response, urlopen = self.finish_login(state="forged")
        self.assert_rejected(response)
        urlopen.assert_not_called()

    def test_cancelled_sign_in_is_rejected(self):
        _, login_session = self.start_login()
        response = self.client.get(
            reverse("oidc_callback"),
            {"state": login_session["state"], "error": "access_denied"},
        )
        self.assert_rejected(response)

    def test_invalid_id_tokens_are_rejected(self):
        for id_token in (
            fake_id_token(nonce="replayed"),
            fake_id_token(iss="https://other.example/realms/x"),
            fake_id_token(aud=["account"]),
            fake_id_token(exp=time.time() - 10),
            fake_id_token(sub=None),
            "not-a-jwt",
            "header.W10.signature",
        ):
            with self.subTest(id_token=id_token):
                response, _ = self.finish_login(id_token)
                self.assert_rejected(response)

    def test_unreachable_login_server_is_rejected(self):
        _, login_session = self.start_login()
        with patch("app.oidc.urlrequest.urlopen", side_effect=urlerror.URLError("down")):
            response = self.client.get(
                reverse("oidc_callback"),
                {"state": login_session["state"], "code": "auth-code"},
            )
        self.assert_rejected(response)

    def test_token_response_without_id_token_is_rejected(self):
        _, login_session = self.start_login()
        response_mock = token_response("unused")
        response_mock.read.return_value = b'{"access_token": "x"}'
        with patch("app.oidc.urlrequest.urlopen", return_value=response_mock):
            response = self.client.get(
                reverse("oidc_callback"),
                {"state": login_session["state"], "code": "auth-code"},
            )
        self.assert_rejected(response)

    def test_logout_also_ends_keycloak_session(self):
        id_token = fake_id_token()
        self.finish_login(id_token)
        response = self.client.post(reverse("logout"))
        location = urlsplit(response["Location"])
        query = parse_qs(location.query)
        self.assertTrue(response["Location"].startswith(f"{ISSUER}/protocol/openid-connect/logout"))
        self.assertEqual(query["id_token_hint"], [id_token])
        self.assertEqual(query["post_logout_redirect_uri"], ["http://testserver/"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_local_logout_is_unchanged(self):
        user = get_user_model().objects.create_user("local", password="pw")
        self.client.force_login(user)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
