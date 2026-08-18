import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app import overlay_transfer, overlay_versions, twitch_api
from app.forms import OverlayAssetUploadForm, TwitchGoalOverlayForm
from app.models import OverlayVersion, TwitchGoalOverlay, goal_elements_for_layout
from app.views.common import (
    conditional_state_response,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_twitch_goal_overlays
from app.views.pages import safe_next_url


def get_manageable_twitch_goal(request, pk):
    return get_object_or_404(manageable_twitch_goal_overlays(request), pk=pk)


def twitch_goal_obs_url(request, overlay):
    return request.build_absolute_uri(reverse("twitch_goal_overlay", args=[overlay.public_token]))


def _sample_state(overlay):
    current = 842 if overlay.progress_mode == overlay.MODE_TOTAL else 42
    target = overlay.target_value or 1000
    return {
        **overlay.design_payload(),
        "goal": {
            "raw_value": 842,
            "current_value": current,
            "target_value": target,
            "remaining": max(target - current, 0),
            "progress_percent": min(round((current / target) * 100, 2), 100),
            "is_reached": current >= target,
            "status": "active",
        },
        "channel": {
            "display_name": "NexoraCreator",
            "login": "nexoracreator",
            "avatar_url": "",
        },
        "celebration_sequence": overlay.celebration_sequence,
        "connected": bool(overlay.connection_id and overlay.connection.is_connected),
    }


def twitch_goal_editor_context(request, form, overlay, is_create):
    connection = overlay.connection if overlay.connection_id else None
    required_scope = twitch_api.required_scope(overlay)
    context = {
        "form": form,
        "overlay": overlay,
        "is_create": is_create,
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
        "twitch_configured": twitch_api.is_configured(),
        "twitch_connection": connection,
        "required_scope": required_scope,
        "has_required_scope": bool(connection and connection.has_scope(required_scope)),
        "obs_url": "" if is_create else twitch_goal_obs_url(request, overlay),
        "sample_state": _sample_state(overlay),
        "layout_templates": {
            layout: goal_elements_for_layout(layout)
            for layout in (
                overlay.LAYOUT_HORIZONTAL,
                overlay.LAYOUT_COMPACT,
                overlay.LAYOUT_CARD,
                overlay.LAYOUT_RADIAL,
            )
        },
    }
    if not is_create:
        context.update(overlay_versions.editor_version_context(overlay))
    return context


@login_required
def twitch_goal_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#twitch-goal-overlays")


@login_required
def twitch_goal_create(request):
    overlay = TwitchGoalOverlay(owner=request.user)
    if request.method == "POST":
        form = TwitchGoalOverlayForm(
            request.POST,
            instance=overlay,
            asset_owner=request.user,
        )
        if form.is_valid():
            overlay = form.save(commit=False)
            overlay.connection = twitch_api.connection_for_owner(request.user)
            overlay.save()
            overlay_versions.record_version(overlay, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Twitch goal overlay created."))
            return redirect("twitch_goal_manage", pk=overlay.pk)
    else:
        form = TwitchGoalOverlayForm(instance=overlay, asset_owner=request.user)
    return render(
        request,
        "app/twitch_goal/create.html",
        twitch_goal_editor_context(request, form, overlay, True),
    )


@login_required
def twitch_goal_manage(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    if request.method == "POST":
        form = TwitchGoalOverlayForm(
            request.POST,
            instance=overlay,
            asset_owner=request.user,
        )
        if form.is_valid():
            overlay = form.save()
            overlay_versions.record_version(overlay, OverlayVersion.REASON_MANUAL)
            messages.success(request, _("Twitch goal overlay saved."))
            return redirect("twitch_goal_manage", pk=overlay.pk)
    else:
        form = TwitchGoalOverlayForm(instance=overlay, asset_owner=request.user)
    return render(
        request,
        "app/twitch_goal/create.html",
        twitch_goal_editor_context(request, form, overlay, False),
    )


@login_required
@require_POST
def twitch_goal_autosave(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    form = TwitchGoalOverlayForm(
        request.POST,
        instance=overlay,
        asset_owner=request.user,
    )
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    overlay = form.save()
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return JsonResponse({"ok": True, "updated_at": overlay.updated_at.isoformat()})


@login_required
@require_POST
def twitch_goal_delete(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    name = overlay.display_name
    overlay_versions.delete_versions(overlay)
    overlay.delete()
    messages.success(request, _("Twitch goal overlay deleted: %(name)s") % {"name": name})
    return redirect(f"{reverse('overlay_dashboard')}#twitch-goal-overlays")


@login_required
@require_POST
def twitch_goal_duplicate(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(overlay, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(
        request,
        _("Twitch goal overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#twitch-goal-overlays")


@login_required
@require_GET
def twitch_goal_export(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    return json_export_response(
        overlay_transfer.twitch_goal_export_payload(overlay),
        overlay_transfer.TWITCH_GOAL_TYPE,
        overlay.display_name,
    )


@login_required
@require_POST
def twitch_goal_renew_obs_link(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    return renew_public_obs_link(
        request,
        overlay,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


@login_required
def twitch_connect(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    if not twitch_api.is_configured():
        messages.error(request, _("Add Twitch client credentials before connecting."))
        return redirect("twitch_goal_manage", pk=overlay.pk)
    connection = twitch_api.connection_for_owner(request.user)
    scopes = set(connection.scopes or [])
    scopes.add(twitch_api.required_scope(overlay))
    state = secrets.token_urlsafe(32)
    request.session["twitch_oauth"] = {
        "state": state,
        "overlay_id": overlay.pk,
        "scopes": sorted(scopes),
    }
    return redirect(twitch_api.authorization_url(request, state, scopes))


@login_required
def twitch_callback(request):
    oauth_session = request.session.pop("twitch_oauth", None)
    received_state = request.GET.get("state", "")
    overlay_id = oauth_session.get("overlay_id") if oauth_session else None
    if (
        not oauth_session
        or not overlay_id
        or not received_state
        or not secrets.compare_digest(received_state, oauth_session.get("state", ""))
    ):
        messages.error(request, _("The Twitch connection could not be verified."))
        return redirect(f"{reverse('overlay_dashboard')}#twitch-goal-overlays")
    overlay = get_manageable_twitch_goal(request, overlay_id)
    if request.GET.get("error"):
        messages.error(request, _("Twitch access was not granted."))
        return redirect("twitch_goal_manage", pk=overlay.pk)
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, _("Twitch returned no authorization code."))
        return redirect("twitch_goal_manage", pk=overlay.pk)
    try:
        connection = twitch_api.exchange_authorization_code(
            request,
            request.user,
            code,
            oauth_session.get("scopes") or [],
        )
    except twitch_api.TwitchAPIError:
        messages.error(request, _("Twitch could not be connected. Check the app settings."))
    else:
        overlay.connection = connection
        overlay.save(update_fields=("connection", "updated_at"))
        messages.success(request, _("Twitch connected successfully."))
    return redirect("twitch_goal_manage", pk=overlay.pk)


@login_required
@require_POST
def twitch_disconnect(request):
    next_url = safe_next_url(request, fallback="overlay_dashboard")
    twitch_api.disconnect(request.user)
    messages.success(request, _("Twitch disconnected from all goal overlays."))
    return redirect(next_url)


@login_required
@require_POST
def twitch_goal_campaign_reset(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    if overlay.progress_mode != overlay.MODE_CAMPAIGN:
        return JsonResponse({"ok": False, "error": _("This is not a campaign goal.")}, status=409)
    if not overlay.connection_id or not overlay.connection.is_connected:
        return JsonResponse({"ok": False, "error": _("Connect Twitch first.")}, status=409)
    state = twitch_api.cached_metric_state(overlay.connection, overlay.goal_type)
    raw_value = twitch_api._selected_metric_value(overlay, state)
    if raw_value is None:
        return JsonResponse({"ok": False, "error": _("No Twitch value is available.")}, status=409)
    overlay.campaign_baseline = raw_value
    overlay.goal_revision += 1
    overlay.last_observed_progress = 0
    overlay.completed_at = None
    overlay.save(
        update_fields=(
            "campaign_baseline",
            "goal_revision",
            "last_observed_progress",
            "completed_at",
            "updated_at",
        )
    )
    return JsonResponse({"ok": True, "baseline": raw_value})


@login_required
@require_POST
def twitch_goal_replay(request, pk):
    overlay = get_manageable_twitch_goal(request, pk)
    TwitchGoalOverlay.objects.filter(pk=overlay.pk).update(
        celebration_sequence=F("celebration_sequence") + 1,
        updated_at=timezone.now(),
    )
    overlay.refresh_from_db(fields=("celebration_sequence", "updated_at"))
    return JsonResponse({"ok": True, "celebration_sequence": overlay.celebration_sequence})


@never_cache
def twitch_goal_overlay(request, public_token):
    overlay = get_object_or_404(
        TwitchGoalOverlay.objects.select_related(
            "connection",
            "font_asset",
            "logo_asset",
            "background_asset",
        ),
        public_token=public_token,
    )
    response = render(
        request,
        "app/twitch_goal/public_overlay.html",
        {"overlay": overlay, "initial_state": twitch_api.overlay_state_payload(overlay)},
    )
    return no_store(response)


@never_cache
def twitch_goal_overlay_state(request, public_token):
    overlay = get_object_or_404(
        TwitchGoalOverlay.objects.select_related(
            "connection",
            "font_asset",
            "logo_asset",
            "background_asset",
        ),
        public_token=public_token,
    )
    payload = twitch_api.overlay_state_payload(overlay)
    cached_at = payload["goal"].get("cached_at", "")
    version = f"{payload.get('updated_at', '')}:{cached_at}:{payload['celebration_sequence']}"
    return conditional_state_response(request, payload, version)
