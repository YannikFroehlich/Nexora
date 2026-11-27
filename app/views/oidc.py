"""Sign-in and sign-out through the central Keycloak realm (see app/oidc.py)."""

import secrets

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from app import oidc
from app.views.pages import safe_next_url

LOGIN_SESSION_KEY = "oidc_login"
ID_TOKEN_SESSION_KEY = "oidc_id_token"


def oidc_login(request):
    if not oidc.is_configured():
        raise Http404
    login_session = oidc.new_login_session()
    login_session["next"] = safe_next_url(request)
    request.session[LOGIN_SESSION_KEY] = login_session
    return redirect(oidc.authorization_url(request, login_session))


def oidc_callback(request):
    if not oidc.is_configured():
        raise Http404
    login_session = request.session.pop(LOGIN_SESSION_KEY, None) or {}
    received_state = request.GET.get("state", "")
    if not received_state or not secrets.compare_digest(
        received_state, login_session.get("state", "")
    ):
        messages.error(request, _("The sign-in could not be verified. Please try again."))
        return redirect("login")
    code = request.GET.get("code", "")
    if request.GET.get("error") or not code:
        messages.error(request, _("The sign-in was cancelled."))
        return redirect("login")
    try:
        id_token, claims = oidc.exchange_code(request, code, login_session)
        user = oidc.user_for_claims(claims)
    except oidc.OIDCError as error:
        messages.error(request, str(error))
        return redirect("login")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session[ID_TOKEN_SESSION_KEY] = id_token
    # `next` was checked by safe_next_url before it went into the session.
    return redirect(login_session["next"])


class LogoutView(auth_views.LogoutView):
    """Also ends the Keycloak session when the user signed in through it."""

    def post(self, request, *args, **kwargs):
        id_token = request.session.get(ID_TOKEN_SESSION_KEY)
        response = super().post(request, *args, **kwargs)
        if id_token and oidc.is_configured():
            return redirect(oidc.logout_url(request, id_token))
        return response
