"""Sign-in through the central Keycloak realm (OpenID Connect code flow with PKCE).

Uses stdlib urllib like the Spotify and Twitch clients. The ID token comes straight from the token
endpoint over TLS, so its signature is not checked (OpenID Connect Core 3.1.3.7); issuer, audience,
expiry and nonce are.
"""

import base64
import hashlib
import json
import secrets
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _

from app.models import OIDCIdentity

ADMIN_GROUP = "admins"


class OIDCError(Exception):
    pass


def is_configured():
    return bool(settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET)


def oidc_only():
    return settings.OIDC_ONLY and is_configured()


def local_login_allowed(user):
    """With OIDC_ONLY, password sign-in is left to staff as a break-glass login."""
    return not oidc_only() or user.is_staff or user.is_superuser


def _endpoint(name):
    # Keycloak's fixed endpoint layout; saves a discovery request per sign-in.
    return f"{settings.OIDC_ISSUER}/protocol/openid-connect/{name}"


def redirect_uri(request):
    return request.build_absolute_uri(reverse("oidc_callback"))


def new_login_session():
    return {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "verifier": secrets.token_urlsafe(64),
    }


def authorization_url(request, login_session):
    digest = hashlib.sha256(login_session["verifier"].encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    query = urlparse.urlencode(
        {
            "client_id": settings.OIDC_CLIENT_ID,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri(request),
            "state": login_session["state"],
            "nonce": login_session["nonce"],
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{_endpoint('auth')}?{query}"


def logout_url(request, id_token):
    query = urlparse.urlencode(
        {
            "client_id": settings.OIDC_CLIENT_ID,
            "id_token_hint": id_token,
            "post_logout_redirect_uri": request.build_absolute_uri(reverse("home")),
        }
    )
    return f"{_endpoint('logout')}?{query}"


def exchange_code(request, code, login_session):
    """Return (id_token, verified claims) for an authorization code."""
    request_data = urlparse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(request),
            "client_id": settings.OIDC_CLIENT_ID,
            "client_secret": settings.OIDC_CLIENT_SECRET,
            "code_verifier": login_session["verifier"],
        }
    ).encode("utf-8")
    token_request = urlrequest.Request(
        _endpoint("token"),
        data=request_data,
        # Cloudflare in front of Keycloak rejects urllib's default User-Agent (error 1010).
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"Nexora/{settings.APP_VERSION}",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(token_request, timeout=10) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, ValueError) as error:
        raise OIDCError(_("The login server could not complete the sign-in.")) from error
    id_token = token_data.get("id_token") if isinstance(token_data, dict) else None
    if not isinstance(id_token, str):
        raise OIDCError(_("The login server could not complete the sign-in."))
    return id_token, _verified_claims(id_token, login_session["nonce"])


def _verified_claims(id_token, nonce):
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as error:
        raise OIDCError(_("The login server returned an invalid sign-in.")) from error
    if not isinstance(claims, dict):
        raise OIDCError(_("The login server returned an invalid sign-in."))
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    expires_at = claims.get("exp")
    if (
        claims.get("iss") != settings.OIDC_ISSUER
        or settings.OIDC_CLIENT_ID not in audiences
        or not isinstance(expires_at, (int, float))
        or expires_at < time.time()
        or not secrets.compare_digest(str(claims.get("nonce", "")), nonce)
        or not claims.get("sub")
    ):
        raise OIDCError(_("The login server returned an invalid sign-in."))
    return claims


def user_for_claims(claims):
    """Find, link or create the Nexora user for verified ID token claims."""
    groups = claims.get("groups") or []
    if settings.OIDC_REQUIRED_GROUP and settings.OIDC_REQUIRED_GROUP not in groups:
        raise OIDCError(_("Your account has no access to this Nexora instance."))
    user_model = get_user_model()
    with transaction.atomic():
        identity = OIDCIdentity.objects.select_related("user").filter(subject=claims["sub"]).first()
        if identity is not None:
            user = identity.user
        else:
            # Only a verified address may take over an existing local account.
            email = claims.get("email", "") if claims.get("email_verified") is True else ""
            matches = list(user_model.objects.filter(email__iexact=email)[:2]) if email else []
            if len(matches) == 1:
                user = matches[0]
            else:
                user = user_model.objects.create_user(
                    username=_free_username(user_model, claims),
                    email=email,
                )
            OIDCIdentity.objects.create(user=user, subject=claims["sub"])
        # Keycloak is the source of truth for admin rights, but only when it sends groups.
        if "groups" in claims:
            is_admin = ADMIN_GROUP in groups
            if user.is_staff != is_admin or user.is_superuser != is_admin:
                user.is_staff = user.is_superuser = is_admin
                user.save(update_fields=("is_staff", "is_superuser"))
    if not user.is_active:
        raise OIDCError(_("This Nexora account is deactivated."))
    return user


def _free_username(user_model, claims):
    base = (claims.get("preferred_username") or claims.get("email") or claims["sub"])[:140]
    username = base
    suffix = 2
    while user_model.objects.filter(username__iexact=username).exists():
        username = f"{base}-{suffix}"
        suffix += 1
    return username
