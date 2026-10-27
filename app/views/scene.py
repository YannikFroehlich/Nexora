from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from app import overlay_transfer, overlay_versions
from app.forms import OverlayAssetUploadForm, SceneOverlayForm
from app.models import OverlayVersion, SceneOverlay
from app.views.common import (
    conditional_state_response,
    control_url,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_scene_overlays
from app.views.pages import safe_next_url
from app.views.presets import manageable_presets

SCENE_ACTIONS = {
    SceneOverlay.SCENE_STARTING,
    SceneOverlay.SCENE_BRB,
    SceneOverlay.SCENE_ENDING,
    "restart",
}


def get_manageable_scene_overlay(request, pk):
    return get_object_or_404(manageable_scene_overlays(request), pk=pk)


def scene_obs_url(request, scene):
    return request.build_absolute_uri(reverse("scene_overlay", args=[scene.public_token]))


def scene_control_rows(request, scene):
    return [
        {
            "label": scene.display_name,
            "actions": [
                (label, control_url(request, "scene_remote_control", scene, action))
                for action, label in (
                    *SceneOverlay.SCENE_CHOICES,
                    ("restart", _("Restart countdown")),
                )
            ],
        }
    ]


def scene_editor_context(request, form, scene, is_create):
    context = {
        "form": form,
        "scene": scene,
        "is_create": is_create,
        "obs_url": "" if is_create else scene_obs_url(request, scene),
        "control_rows": [] if is_create else scene_control_rows(request, scene),
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
    }
    if not is_create:
        context.update(overlay_versions.editor_version_context(scene))
        context["style_presets"] = manageable_presets(request)
    return context


@login_required
def scene_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#scene-overlays")


@login_required
def scene_create(request):
    scene = SceneOverlay()

    if request.method == "POST":
        form = SceneOverlayForm(request.POST, instance=scene, asset_owner=request.user)
        if form.is_valid():
            scene = form.save(commit=False)
            scene.owner = request.user
            scene.save()
            overlay_versions.record_version(scene, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Scene overlay created."))
            return redirect("scene_manage", pk=scene.pk)
    else:
        form = SceneOverlayForm(instance=scene, asset_owner=request.user)

    return render(
        request,
        "app/scene/create.html",
        scene_editor_context(request, form, scene, True),
    )


@login_required
def scene_manage(request, pk):
    scene = get_manageable_scene_overlay(request, pk)

    if request.method == "POST":
        form = SceneOverlayForm(request.POST, instance=scene, asset_owner=request.user)
        if form.is_valid():
            scene = form.save()
            overlay_versions.record_version(scene, OverlayVersion.REASON_MANUAL)
            messages.success(request, _("Scene overlay saved."))
            return redirect("scene_manage", pk=scene.pk)
    else:
        form = SceneOverlayForm(instance=scene, asset_owner=request.user)

    return render(
        request,
        "app/scene/create.html",
        scene_editor_context(request, form, scene, False),
    )


@login_required
@require_POST
def scene_autosave(request, pk):
    scene = get_manageable_scene_overlay(request, pk)
    form = SceneOverlayForm(request.POST, instance=scene, asset_owner=request.user)

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    scene = form.save()
    overlay_versions.record_version(scene, OverlayVersion.REASON_AUTOSAVE)
    return JsonResponse({"ok": True, "updated_at": scene.updated_at.isoformat()})


def run_scene_action(scenes, action):
    # Switching scenes, even to the current one, (re)starts that scene's countdown.
    with transaction.atomic():
        scene = get_object_or_404(scenes.select_for_update())
        if action != "restart":
            scene.active_scene = action
        scene.restart_countdown(timezone.now())
        scene.save(update_fields=("active_scene", "countdown_ends_at", "updated_at"))

    return no_store(JsonResponse(scene.state_payload()))


@login_required
@require_POST
def scene_control(request, pk):
    action = request.POST.get("action", "")

    if action not in SCENE_ACTIONS:
        return JsonResponse({"error": _("Unknown scene action.")}, status=400)

    return run_scene_action(SceneOverlay.objects.filter(owner=request.user, pk=pk), action)


@csrf_exempt
@never_cache
@require_http_methods(["GET", "POST"])
def scene_remote_control(request, control_token, action):
    if action not in SCENE_ACTIONS:
        raise Http404

    return run_scene_action(SceneOverlay.objects.filter(control_token=control_token), action)


@login_required
@require_POST
def scene_delete(request, pk):
    scene = get_manageable_scene_overlay(request, pk)
    scene_name = scene.display_name
    overlay_versions.delete_versions(scene)
    scene.delete()
    messages.success(request, _("Scene overlay deleted: %(name)s") % {"name": scene_name})
    return redirect(f"{reverse('overlay_dashboard')}#scene-overlays")


@login_required
@require_POST
def scene_duplicate(request, pk):
    scene = get_manageable_scene_overlay(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(scene, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(
        request,
        _("Scene overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#scene-overlays")


@login_required
@require_GET
def scene_export(request, pk):
    scene = get_manageable_scene_overlay(request, pk)
    return json_export_response(
        overlay_transfer.scene_export_payload(scene),
        overlay_transfer.SCENE_TYPE,
        scene.display_name,
    )


@login_required
@require_POST
def scene_renew_obs_link(request, pk):
    scene = get_manageable_scene_overlay(request, pk)
    return renew_public_obs_link(
        request,
        scene,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


def public_scene(public_token):
    return get_object_or_404(
        SceneOverlay.objects.select_related("font_asset", "logo_asset", "background_asset"),
        public_token=public_token,
    )


@never_cache
def scene_overlay(request, public_token):
    scene = public_scene(public_token)
    return no_store(render(request, "app/scene/public_overlay.html", {"scene": scene}))


@never_cache
def scene_overlay_state(request, public_token):
    scene = public_scene(public_token)
    return conditional_state_response(
        request,
        scene.state_payload(),
        scene.updated_at.isoformat(),
    )
