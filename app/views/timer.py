from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app import overlay_transfer, overlay_versions
from app.forms import OverlayAssetUploadForm, TimerOverlayForm
from app.models import OverlayVersion, TimerOverlay
from app.views.common import (
    conditional_state_response,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_timer_overlays
from app.views.pages import safe_next_url


def get_manageable_timer_overlay(request, pk):
    return get_object_or_404(manageable_timer_overlays(request), pk=pk)


def timer_obs_url(request, timer):
    return request.build_absolute_uri(reverse("timer_overlay", args=[timer.public_token]))


def timer_editor_context(request, form, timer, is_create):
    context = {
        "form": form,
        "timer": timer,
        "is_create": is_create,
        "obs_url": "" if is_create else timer_obs_url(request, timer),
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
    }
    if not is_create:
        context.update(overlay_versions.editor_version_context(timer))
    return context


@login_required
def timer_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#timer-overlays")


@login_required
def timer_create(request):
    timer = TimerOverlay()

    if request.method == "POST":
        form = TimerOverlayForm(
            request.POST,
            instance=timer,
            asset_owner=request.user,
        )
        if form.is_valid():
            timer = form.save(commit=False)
            timer.owner = request.user
            timer.save()
            overlay_versions.record_version(timer, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Timer overlay created."))
            return redirect("timer_manage", pk=timer.pk)
    else:
        form = TimerOverlayForm(instance=timer, asset_owner=request.user)

    return render(
        request,
        "app/timer/create.html",
        timer_editor_context(request, form, timer, True),
    )


@login_required
def timer_manage(request, pk):
    timer = get_manageable_timer_overlay(request, pk)

    if request.method == "POST":
        form = TimerOverlayForm(
            request.POST,
            instance=timer,
            asset_owner=request.user,
        )
        if form.is_valid():
            timer = form.save()
            overlay_versions.record_version(timer, OverlayVersion.REASON_MANUAL)
            messages.success(request, _("Timer overlay saved."))
            return redirect("timer_manage", pk=timer.pk)
    else:
        form = TimerOverlayForm(instance=timer, asset_owner=request.user)

    return render(
        request,
        "app/timer/create.html",
        timer_editor_context(request, form, timer, False),
    )


@login_required
@require_POST
def timer_autosave(request, pk):
    timer = get_manageable_timer_overlay(request, pk)
    form = TimerOverlayForm(
        request.POST,
        instance=timer,
        asset_owner=request.user,
    )

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    timer = form.save()
    overlay_versions.record_version(timer, OverlayVersion.REASON_AUTOSAVE)
    return JsonResponse({"ok": True, "updated_at": timer.updated_at.isoformat()})


@login_required
@require_POST
def timer_control(request, pk):
    action = request.POST.get("action", "")

    if action not in {"start", "pause", "reset"}:
        return JsonResponse({"error": _("Unknown timer action.")}, status=400)

    with transaction.atomic():
        timer = get_object_or_404(
            TimerOverlay.objects.select_for_update().filter(owner=request.user),
            pk=pk,
        )
        now = timezone.now()
        elapsed = timer.elapsed_seconds(now)
        limit = (
            timer.duration_seconds
            if timer.mode == TimerOverlay.MODE_COUNTDOWN
            else TimerOverlay.MAX_SECONDS
        )

        if action == "reset":
            timer.accumulated_seconds = 0
            timer.started_at = None
            timer.is_running = False
        elif action == "pause":
            timer.accumulated_seconds = elapsed
            timer.started_at = None
            timer.is_running = False
        else:
            if elapsed >= limit:
                elapsed = 0
            timer.accumulated_seconds = elapsed
            timer.started_at = now
            timer.is_running = True

        timer.save(
            update_fields=(
                "accumulated_seconds",
                "started_at",
                "is_running",
                "updated_at",
            )
        )

    return no_store(JsonResponse(timer.state_payload()))


@login_required
@require_POST
def timer_delete(request, pk):
    timer = get_manageable_timer_overlay(request, pk)
    timer_name = timer.display_name
    overlay_versions.delete_versions(timer)
    timer.delete()
    messages.success(
        request,
        _("Timer overlay deleted: %(name)s") % {"name": timer_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#timer-overlays")


@login_required
@require_POST
def timer_duplicate(request, pk):
    timer = get_manageable_timer_overlay(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(timer, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(
        request,
        _("Timer overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#timer-overlays")


@login_required
@require_GET
def timer_export(request, pk):
    timer = get_manageable_timer_overlay(request, pk)
    return json_export_response(
        overlay_transfer.timer_export_payload(timer),
        overlay_transfer.TIMER_TYPE,
        timer.display_name,
    )


@login_required
@require_POST
def timer_renew_obs_link(request, pk):
    timer = get_manageable_timer_overlay(request, pk)
    return renew_public_obs_link(
        request,
        timer,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


@never_cache
def timer_overlay(request, public_token):
    timer = get_object_or_404(
        TimerOverlay.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ),
        public_token=public_token,
    )
    response = render(request, "app/timer/public_overlay.html", {"timer": timer})
    return no_store(response)


@never_cache
def timer_overlay_state(request, public_token):
    timer = get_object_or_404(
        TimerOverlay.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ),
        public_token=public_token,
    )
    return conditional_state_response(
        request,
        timer.state_payload(),
        timer.updated_at.isoformat(),
    )
