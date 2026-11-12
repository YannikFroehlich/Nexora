import json
import secrets
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from app import overlay_transfer, overlay_versions, twitch_api
from app.forms import OverlayAssetUploadForm, TwitchAlertOverlayForm
from app.models import OverlayVersion, TwitchAlertEvent, TwitchAlertOverlay, TwitchConnection
from app.views.common import (
    conditional_state_response,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_twitch_alert_overlays
from app.views.pages import safe_next_url
from app.views.presets import manageable_presets

TEST_ALERT_AMOUNTS = {
    TwitchAlertEvent.TYPE_FOLLOW: 0,
    TwitchAlertEvent.TYPE_SUBSCRIPTION: 6,
    TwitchAlertEvent.TYPE_GIFT: 5,
    TwitchAlertEvent.TYPE_CHEER: 500,
    TwitchAlertEvent.TYPE_RAID: 42,
}


def get_manageable_twitch_alert(request, pk):
    return get_object_or_404(manageable_twitch_alert_overlays(request), pk=pk)


def twitch_alert_obs_url(request, overlay):
    return request.build_absolute_uri(reverse("twitch_alert_overlay", args=[overlay.public_token]))


def twitch_alert_editor_context(request, form, overlay, is_create):
    connection = TwitchConnection.objects.filter(owner=request.user).first()
    callback_url = twitch_api.eventsub_callback_url(request)
    context = {
        "form": form,
        "overlay": overlay,
        "is_create": is_create,
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
        "twitch_configured": twitch_api.is_configured(),
        "twitch_connection": connection if connection and connection.is_connected else None,
        "missing_scopes": twitch_api.missing_alert_scopes(connection) if connection else [],
        "active_alert_types": sorted(
            (connection.eventsub_subscriptions or {}) if connection else {}
        ),
        "callback_is_public": callback_url.startswith("https://"),
        "test_alert_types": TwitchAlertEvent.TYPE_CHOICES,
        "obs_url": "" if is_create else twitch_alert_obs_url(request, overlay),
    }
    if not is_create:
        context.update(overlay_versions.editor_version_context(overlay))
        context["style_presets"] = manageable_presets(request)
    return context


def activate_alerts(request, connection):
    try:
        twitch_api.sync_alert_subscriptions(connection, twitch_api.eventsub_callback_url(request))
    except twitch_api.TwitchAPIError:
        messages.error(request, _("Twitch alerts could not be activated."))
        return False
    messages.success(request, _("Twitch alerts are active."))
    return True


@login_required
def twitch_alert_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#twitch-alert-overlays")


@login_required
def twitch_alert_create(request):
    overlay = TwitchAlertOverlay()
    if request.method == "POST":
        form = TwitchAlertOverlayForm(request.POST, instance=overlay, asset_owner=request.user)
        if form.is_valid():
            overlay = form.save(commit=False)
            overlay.owner = request.user
            overlay.save()
            overlay_versions.record_version(overlay, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Twitch alert overlay created."))
            return redirect("twitch_alert_manage", pk=overlay.pk)
    else:
        form = TwitchAlertOverlayForm(instance=overlay, asset_owner=request.user)
    return render(
        request,
        "app/twitch_alert/create.html",
        twitch_alert_editor_context(request, form, overlay, True),
    )


@login_required
def twitch_alert_manage(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    if request.method == "POST":
        form = TwitchAlertOverlayForm(request.POST, instance=overlay, asset_owner=request.user)
        if form.is_valid():
            overlay = form.save()
            overlay_versions.record_version(overlay, OverlayVersion.REASON_MANUAL)
            messages.success(request, _("Twitch alert overlay saved."))
            return redirect("twitch_alert_manage", pk=overlay.pk)
    else:
        form = TwitchAlertOverlayForm(instance=overlay, asset_owner=request.user)
    return render(
        request,
        "app/twitch_alert/create.html",
        twitch_alert_editor_context(request, form, overlay, False),
    )


@login_required
@require_POST
def twitch_alert_autosave(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    form = TwitchAlertOverlayForm(request.POST, instance=overlay, asset_owner=request.user)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    overlay = form.save()
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return JsonResponse({"ok": True, "updated_at": overlay.updated_at.isoformat()})


@login_required
@require_POST
def twitch_alert_delete(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    name = overlay.display_name
    overlay_versions.delete_versions(overlay)
    overlay.delete()
    messages.success(request, _("Twitch alert overlay deleted: %(name)s") % {"name": name})
    return redirect(f"{reverse('overlay_dashboard')}#twitch-alert-overlays")


@login_required
@require_POST
def twitch_alert_duplicate(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(overlay, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(
        request,
        _("Twitch alert overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#twitch-alert-overlays")


@login_required
@require_GET
def twitch_alert_export(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    return json_export_response(
        overlay_transfer.twitch_alert_export_payload(overlay),
        overlay_transfer.TWITCH_ALERT_TYPE,
        overlay.display_name,
    )


@login_required
@require_POST
def twitch_alert_renew_obs_link(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    return renew_public_obs_link(
        request,
        overlay,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


@login_required
def twitch_alert_connect(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    if not twitch_api.is_configured():
        messages.error(request, _("Add Twitch client credentials before connecting."))
        return redirect("twitch_alert_manage", pk=overlay.pk)
    connection = twitch_api.connection_for_owner(request.user)
    scopes = {*(connection.scopes or []), *twitch_api.ALERT_SCOPES}
    state = secrets.token_urlsafe(32)
    request.session["twitch_oauth"] = {
        "state": state,
        "alert_id": overlay.pk,
        "scopes": sorted(scopes),
    }
    return redirect(twitch_api.authorization_url(request, state, scopes))


@login_required
@require_POST
def twitch_alert_activate(request, pk):
    overlay = get_manageable_twitch_alert(request, pk)
    connection = TwitchConnection.objects.filter(owner=request.user).first()
    if connection is None or not connection.is_connected:
        messages.error(request, _("Connect Twitch first."))
    else:
        activate_alerts(request, connection)
    return redirect("twitch_alert_manage", pk=overlay.pk)


@login_required
@require_POST
def twitch_alert_test(request, pk):
    get_manageable_twitch_alert(request, pk)
    event_type = request.POST.get("event_type", TwitchAlertEvent.TYPE_FOLLOW)
    if event_type not in TEST_ALERT_AMOUNTS:
        return JsonResponse({"ok": False, "error": _("Unknown alert type.")}, status=400)
    has_message = event_type in {TwitchAlertEvent.TYPE_SUBSCRIPTION, TwitchAlertEvent.TYPE_CHEER}
    event = TwitchAlertEvent.objects.create(
        owner=request.user,
        message_id=f"test-{uuid.uuid4()}",
        event_type=event_type,
        user_name="NexoraFan",
        amount=TEST_ALERT_AMOUNTS[event_type],
        message=_("This is a test alert from Nexora.") if has_message else "",
        is_test=True,
    )
    twitch_api.prune_alert_events()
    return JsonResponse({"ok": True, "event": event.payload()})


@csrf_exempt
@require_POST
def twitch_eventsub_callback(request):
    body = request.body
    if not twitch_api.verify_eventsub_signature(request.headers, body):
        return HttpResponse(status=403)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)

    message_type = request.headers.get("Twitch-Eventsub-Message-Type", "")
    if message_type == "webhook_callback_verification":
        return HttpResponse(str(payload.get("challenge", "")), content_type="text/plain")
    if message_type == "notification":
        twitch_api.record_alert_notification(
            request.headers["Twitch-Eventsub-Message-Id"],
            payload,
        )
    elif message_type == "revocation":
        twitch_api.forget_alert_subscription((payload.get("subscription") or {}).get("id"))
    return HttpResponse(status=204)


def public_twitch_alert(public_token):
    return get_object_or_404(
        TwitchAlertOverlay.objects.select_related("font_asset", "logo_asset", "background_asset"),
        public_token=public_token,
    )


@never_cache
def twitch_alert_overlay(request, public_token):
    overlay = public_twitch_alert(public_token)
    return no_store(render(request, "app/twitch_alert/public_overlay.html", {"overlay": overlay}))


@never_cache
def twitch_alert_overlay_state(request, public_token):
    overlay = public_twitch_alert(public_token)
    payload = overlay.state_payload()
    latest_id = payload["events"][-1]["id"] if payload["events"] else 0
    return conditional_state_response(request, payload, f"{payload['updated_at']}:{latest_id}")
