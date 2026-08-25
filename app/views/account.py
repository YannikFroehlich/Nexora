from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from app import twitch_api
from app.forms import AccountDeleteForm, AccountEmailForm, AccountPasswordChangeForm
from app.models import OverlayAsset

TEMPLATE = "app/registration/account_settings.html"


def _context(request, email_form=None, password_form=None, delete_form=None):
    return {
        "email_form": email_form or AccountEmailForm(instance=request.user),
        "password_form": password_form or AccountPasswordChangeForm(request.user),
        "delete_form": delete_form or AccountDeleteForm(request.user),
    }


@login_required
def account_settings(request):
    return render(request, TEMPLATE, _context(request))


@login_required
@require_POST
def account_email_update(request):
    form = AccountEmailForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, _("Email address updated."))
        return redirect("account_settings")
    return render(request, TEMPLATE, _context(request, email_form=form))


@login_required
@require_POST
def account_password_change(request):
    form = AccountPasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, _("Your password has been changed."))
        return redirect("account_settings")
    return render(request, TEMPLATE, _context(request, password_form=form))


@login_required
@require_POST
def account_delete(request):
    form = AccountDeleteForm(request.user, request.POST)
    if not form.is_valid():
        return render(request, TEMPLATE, _context(request, delete_form=form))

    user = request.user
    # spotify_api.disconnect() takes an overlay, not a user, and has no revoke call anyway;
    # the SpotifyConnection row is removed below by the owner CASCADE on user.delete().
    twitch_api.disconnect(user)
    for asset in OverlayAsset.objects.filter(owner=user):
        asset.file.delete(save=False)

    messages.success(request, _("Your account and all associated data have been deleted."))
    logout(request)
    user.delete()
    return redirect("home")
