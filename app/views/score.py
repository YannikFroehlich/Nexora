from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app import overlay_transfer, overlay_versions
from app.forms import (
    OverlayAssetUploadForm,
    ScoreOverlayCreateForm,
    ScoreOverlayForm,
    ScoreParticipantForm,
)
from app.models import OverlayVersion, ScoreOverlay, ScoreParticipant, default_score_elements
from app.views.common import (
    conditional_state_response,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_score_overlays
from app.views.pages import safe_next_url


def get_manageable_score_overlay(request, pk):
    return get_object_or_404(manageable_score_overlays(request), pk=pk)


def score_obs_url(request, overlay):
    return request.build_absolute_uri(reverse("score_overlay", args=[overlay.public_token]))


def touch_score_overlay(overlay):
    ScoreOverlay.objects.filter(pk=overlay.pk).update(updated_at=timezone.now())
    overlay._prefetched_objects_cache.pop("participants", None)


def fresh_score_overlay(overlay):
    return get_object_or_404(
        ScoreOverlay.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ).prefetch_related("participants__image_asset"),
        pk=overlay.pk,
    )


def state_response(overlay):
    return no_store(JsonResponse(fresh_score_overlay(overlay).state_payload()))


def score_editor_context(request, form, overlay, is_create):
    context = {
        "form": form,
        "overlay": overlay,
        "is_create": is_create,
        "participant_form": ScoreParticipantForm(owner=request.user),
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
        "obs_url": "" if is_create else score_obs_url(request, overlay),
    }
    if not is_create:
        context.update(overlay_versions.editor_version_context(overlay))
    return context


def score_elements_for_participant(participant, index, overlay):
    row = index % ScoreOverlay.MAX_PARTICIPANTS
    y = 26 + (row * 74)
    return [
        {
            "id": f"participant-{participant.public_id}-image",
            "type": "participant_image",
            "participant_id": str(participant.public_id),
            "x": 28,
            "y": y,
            "width": 58,
            "height": 58,
            "font_size": 22,
            "color": "#ffffff",
            "background_color": participant.accent_color,
            "border_radius": 15,
            "text_align": "center",
        },
        {
            "id": f"participant-{participant.public_id}-name",
            "type": "participant_name",
            "participant_id": str(participant.public_id),
            "x": 100,
            "y": y + 7,
            "width": max(overlay.canvas_width - 300, 160),
            "height": 28,
            "font_size": 22,
            "color": "#ffffff",
            "background_color": "#111827",
            "border_radius": 8,
            "text_align": "left",
        },
        {
            "id": f"participant-{participant.public_id}-score",
            "type": "participant_score",
            "participant_id": str(participant.public_id),
            "x": max(overlay.canvas_width - 150, 170),
            "y": y,
            "width": 120,
            "height": 58,
            "font_size": 42,
            "color": "#ffffff",
            "background_color": participant.accent_color,
            "border_radius": 14,
            "text_align": "center",
        },
    ]


@login_required
def score_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#score-overlays")


@login_required
def score_create(request):
    overlay = ScoreOverlay()

    if request.method == "POST":
        form = ScoreOverlayCreateForm(
            request.POST,
            instance=overlay,
            asset_owner=request.user,
        )

        if form.is_valid():
            overlay = form.save(commit=False)
            overlay.owner = request.user
            overlay.save()
            participants = [
                ScoreParticipant.objects.create(
                    overlay=overlay,
                    name=form.cleaned_data["player_one_name"],
                    accent_color="#38bdf8",
                    sort_order=0,
                ),
                ScoreParticipant.objects.create(
                    overlay=overlay,
                    name=form.cleaned_data["player_two_name"],
                    accent_color="#fb7185",
                    sort_order=1,
                ),
            ]
            overlay.elements = default_score_elements(participants)
            overlay.save(update_fields=["elements", "updated_at"])
            overlay_versions.record_version(overlay, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Score HUD created."))
            return redirect("score_manage", pk=overlay.pk)
    else:
        form = ScoreOverlayCreateForm(instance=overlay, asset_owner=request.user)

    return render(
        request,
        "app/score/create.html",
        score_editor_context(request, form, overlay, True),
    )


@login_required
def score_manage(request, pk):
    overlay = get_manageable_score_overlay(request, pk)

    if request.method == "POST":
        form = ScoreOverlayForm(
            request.POST,
            instance=overlay,
            asset_owner=request.user,
        )

        if form.is_valid():
            overlay = form.save()
            overlay_versions.record_version(overlay, OverlayVersion.REASON_MANUAL)
            messages.success(request, _("Score HUD saved."))
            return redirect("score_manage", pk=overlay.pk)
    else:
        form = ScoreOverlayForm(instance=overlay, asset_owner=request.user)

    return render(
        request,
        "app/score/create.html",
        score_editor_context(request, form, overlay, False),
    )


@login_required
@require_POST
def score_autosave(request, pk):
    overlay = get_manageable_score_overlay(request, pk)
    form = ScoreOverlayForm(
        request.POST,
        instance=overlay,
        asset_owner=request.user,
    )

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    overlay = form.save()
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return JsonResponse({"ok": True, "updated_at": overlay.updated_at.isoformat()})


@login_required
@require_POST
def score_delete(request, pk):
    overlay = get_manageable_score_overlay(request, pk)
    overlay_name = overlay.display_name
    overlay_versions.delete_versions(overlay)
    overlay.delete()
    messages.success(request, _("Score HUD deleted: %(name)s") % {"name": overlay_name})
    return redirect(f"{reverse('overlay_dashboard')}#score-overlays")


@login_required
@require_POST
def score_duplicate(request, pk):
    overlay = get_manageable_score_overlay(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(overlay, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(request, _("Score HUD duplicated: %(name)s") % {"name": duplicate.display_name})
    return redirect(f"{reverse('overlay_dashboard')}#score-overlays")


@login_required
@require_GET
def score_export(request, pk):
    overlay = get_manageable_score_overlay(request, pk)
    return json_export_response(
        overlay_transfer.score_export_payload(overlay),
        overlay_transfer.SCORE_TYPE,
        overlay.display_name,
    )


@login_required
@require_POST
def score_renew_obs_link(request, pk):
    overlay = get_manageable_score_overlay(request, pk)
    return renew_public_obs_link(
        request,
        overlay,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


@login_required
@require_POST
def score_participant_add(request, pk):
    overlay = get_manageable_score_overlay(request, pk)

    if overlay.participants.count() >= ScoreOverlay.MAX_PARTICIPANTS:
        return JsonResponse(
            {"error": _("A maximum of 8 participants is allowed.")},
            status=400,
        )

    form = ScoreParticipantForm(request.POST, owner=request.user)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    max_order = overlay.participants.aggregate(max_order=Max("sort_order"))["max_order"]
    participant = form.save(commit=False)
    participant.overlay = overlay
    participant.sort_order = 0 if max_order is None else max_order + 1
    participant.save()
    overlay.elements = [
        *overlay.elements,
        *score_elements_for_participant(participant, overlay.participants.count() - 1, overlay),
    ]
    overlay.save(update_fields=["elements", "updated_at"])
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return state_response(overlay)


@login_required
@require_POST
def score_participant_update(request, pk, participant_id):
    overlay = get_manageable_score_overlay(request, pk)
    participant = get_object_or_404(ScoreParticipant, public_id=participant_id, overlay=overlay)
    form = ScoreParticipantForm(request.POST, instance=participant, owner=request.user)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    form.save()
    touch_score_overlay(overlay)
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return state_response(overlay)


@login_required
@require_POST
def score_participant_delete(request, pk, participant_id):
    overlay = get_manageable_score_overlay(request, pk)

    if overlay.participants.count() <= ScoreOverlay.MIN_PARTICIPANTS:
        return JsonResponse(
            {"error": _("At least two participants are required.")},
            status=400,
        )

    participant = get_object_or_404(ScoreParticipant, public_id=participant_id, overlay=overlay)
    participant_id = str(participant.public_id)
    participant.delete()
    overlay.elements = [
        element
        for element in overlay.elements
        if str(element.get("participant_id")) != participant_id
    ]
    overlay.save(update_fields=["elements", "updated_at"])
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return state_response(overlay)


@login_required
@require_POST
def score_participant_score(request, pk, participant_id):
    overlay = get_manageable_score_overlay(request, pk)

    try:
        delta = int(request.POST.get("delta", 0))
    except ValueError:
        return JsonResponse({"error": _("Invalid score change.")}, status=400)

    if delta not in (-1, 1):
        return JsonResponse({"error": _("Invalid score change.")}, status=400)

    with transaction.atomic():
        participant = get_object_or_404(
            ScoreParticipant.objects.select_for_update(),
            public_id=participant_id,
            overlay=overlay,
        )

        if delta > 0 and participant.score < ScoreOverlay.MAX_SCORE:
            ScoreParticipant.objects.filter(pk=participant.pk).update(score=F("score") + 1)
        elif delta < 0:
            minimum = ScoreOverlay.MIN_SCORE if overlay.allow_negative_scores else 0
            if participant.score > minimum:
                ScoreParticipant.objects.filter(pk=participant.pk).update(score=F("score") - 1)

        touch_score_overlay(overlay)
        overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)

    return state_response(overlay)


@login_required
@require_POST
def score_participant_reset(request, pk, participant_id):
    overlay = get_manageable_score_overlay(request, pk)
    participant = get_object_or_404(ScoreParticipant, public_id=participant_id, overlay=overlay)
    participant.score = 0
    participant.save(update_fields=["score"])
    touch_score_overlay(overlay)
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return state_response(overlay)


@login_required
@require_POST
def score_reset_all(request, pk):
    overlay = get_manageable_score_overlay(request, pk)
    overlay.participants.update(score=0)
    touch_score_overlay(overlay)
    overlay_versions.record_version(overlay, OverlayVersion.REASON_AUTOSAVE)
    return state_response(overlay)


@never_cache
def score_overlay(request, public_token):
    overlay = get_object_or_404(
        ScoreOverlay.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ).prefetch_related("participants__image_asset"),
        public_token=public_token,
    )
    response = render(
        request,
        "app/score/public_overlay.html",
        {"overlay": overlay},
    )
    return no_store(response)


@never_cache
def score_overlay_state(request, public_token):
    overlay = get_object_or_404(
        ScoreOverlay.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ).prefetch_related("participants__image_asset"),
        public_token=public_token,
    )
    return conditional_state_response(
        request,
        overlay.state_payload(),
        overlay.updated_at.isoformat(),
    )
