from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from app import overlay_presets, overlay_versions
from app.models import OverlayPreset


def manageable_presets(request):
    return OverlayPreset.objects.filter(owner=request.user)


@login_required
def preset_list(request):
    return render(
        request,
        "app/presets/list.html",
        {"presets": manageable_presets(request)},
    )


@login_required
@require_POST
def preset_save(request):
    overlay_type = request.POST.get("overlay_type", "")
    pk = request.POST.get("pk", "")
    name = request.POST.get("name", "").strip()

    try:
        model = overlay_presets.model_for(overlay_type)
    except overlay_presets.OverlayPresetError:
        return redirect("preset_list")

    overlay = get_object_or_404(model, owner=request.user, pk=pk)

    if not name:
        messages.error(request, _("Enter a name for the template."))
        return redirect(f"{overlay_type}_manage", pk=overlay.pk)

    OverlayPreset.objects.create(
        owner=request.user,
        name=name,
        style=overlay_presets.capture_style(overlay),
    )
    messages.success(request, _("Template saved: %(name)s") % {"name": name})
    return redirect(f"{overlay_type}_manage", pk=overlay.pk)


@login_required
@require_POST
def preset_apply(request, overlay_type, pk):
    try:
        model = overlay_presets.model_for(overlay_type)
    except overlay_presets.OverlayPresetError:
        return redirect("overlay_dashboard")

    overlay = get_object_or_404(model, owner=request.user, pk=pk)
    preset = get_object_or_404(OverlayPreset, owner=request.user, pk=request.POST.get("preset_id"))

    overlay_versions.record_version(overlay, overlay_versions.OverlayVersion.REASON_AUTOSAVE)
    try:
        overlay_presets.apply_style(overlay, preset)
    except ValidationError:
        messages.error(request, _("This template could not be applied."))
    else:
        overlay_versions.record_version(overlay, overlay_versions.OverlayVersion.REASON_MANUAL)
        messages.success(request, _("Template applied: %(name)s") % {"name": preset.name})

    return redirect(f"{overlay_type}_manage", pk=overlay.pk)


@login_required
@require_POST
def preset_delete(request, pk):
    preset = get_object_or_404(OverlayPreset, owner=request.user, pk=pk)
    name = preset.name
    preset.delete()
    messages.success(request, _("Template deleted: %(name)s") % {"name": name})
    return redirect("preset_list")
