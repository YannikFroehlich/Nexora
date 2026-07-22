from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from app import overlay_transfer, overlay_versions
from app.forms import OverlayAssetUploadForm, OverlayImportForm
from app.models import OverlayVersion, SpotifyOverlay, TimerOverlay, WinChallenge
from app.views.pages import safe_next_url


def manageable_spotify_overlays(request):
    return SpotifyOverlay.objects.select_related(
        "connection",
        "font_asset",
        "logo_asset",
        "background_asset",
    ).filter(owner=request.user)


def manageable_winchallenges(request):
    return (
        WinChallenge.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        )
        .prefetch_related("games")
        .filter(owner=request.user)
    )


def manageable_timer_overlays(request):
    return TimerOverlay.objects.select_related(
        "font_asset",
        "logo_asset",
        "background_asset",
    ).filter(owner=request.user)


def overlay_dashboard_context(request, import_form=None):
    spotify_overlays = list(manageable_spotify_overlays(request))
    win_challenges = list(manageable_winchallenges(request))
    timer_overlays = list(manageable_timer_overlays(request))
    return {
        "spotify_overlays": spotify_overlays,
        "win_challenges": win_challenges,
        "timer_overlays": timer_overlays,
        "spotify_count": len(spotify_overlays),
        "winchallenge_count": len(win_challenges),
        "timer_count": len(timer_overlays),
        "overlay_count": len(spotify_overlays) + len(win_challenges) + len(timer_overlays),
        "import_form": import_form or OverlayImportForm(),
    }


@login_required
def overlay_dashboard(request):
    return render(
        request,
        "app/overlay_dashboard.html",
        overlay_dashboard_context(request),
    )


@login_required
@require_POST
def overlay_import(request):
    import_form = OverlayImportForm(request.POST, request.FILES)

    if import_form.is_valid():
        try:
            payload = overlay_transfer.load_payload(import_form.cleaned_data["overlay_file"])
            overlay = overlay_transfer.import_payload(payload, request.user)
        except overlay_transfer.OverlayTransferError as error:
            import_form.add_error("overlay_file", str(error))
        else:
            overlay_versions.record_version(overlay, OverlayVersion.REASON_CREATED)
            display_name = (
                overlay.display_name
                if isinstance(overlay, (SpotifyOverlay, TimerOverlay))
                else overlay.display_title
            )
            messages.success(
                request,
                _("Overlay imported: %(name)s") % {"name": display_name},
            )
            if isinstance(overlay, SpotifyOverlay):
                section = "spotify-overlays"
            elif isinstance(overlay, TimerOverlay):
                section = "timer-overlays"
            else:
                section = "winchallenge-overlays"
            return redirect(f"{reverse('overlay_dashboard')}#{section}")

    return render(
        request,
        "app/overlay_dashboard.html",
        overlay_dashboard_context(request, import_form),
        status=400,
    )


@login_required
@require_POST
def overlay_asset_upload(request):
    form = OverlayAssetUploadForm(
        request.POST,
        request.FILES,
        owner=request.user,
        prefix="asset",
    )
    redirect_url = safe_next_url(request, fallback="overlay_dashboard")

    if form.is_valid():
        asset = form.save()
        messages.success(
            request,
            _("Asset uploaded: %(name)s") % {"name": asset.name},
        )
    else:
        errors = " ".join(
            str(error) for field_errors in form.errors.values() for error in field_errors
        )
        messages.error(request, errors or _("The asset could not be uploaded."))

    return redirect(redirect_url)


@login_required
@require_POST
def overlay_version_restore(request, overlay_type, pk, version_pk):
    model_and_redirect = {
        overlay_transfer.SPOTIFY_TYPE: (SpotifyOverlay, "spotify_manage"),
        overlay_transfer.TIMER_TYPE: (TimerOverlay, "timer_manage"),
        overlay_transfer.WINCHALLENGE_TYPE: (WinChallenge, "winchallenge_manage"),
    }
    model_config = model_and_redirect.get(overlay_type)
    if model_config is None:
        return redirect("overlay_dashboard")

    model, redirect_name = model_config
    overlay = get_object_or_404(model, owner=request.user, pk=pk)
    version = get_object_or_404(
        OverlayVersion,
        owner=request.user,
        overlay_type=overlay_type,
        overlay_id=overlay.pk,
        pk=version_pk,
    )

    try:
        overlay_versions.restore_version(overlay, version)
    except overlay_versions.OverlayVersionError:
        messages.error(request, _("This overlay version could not be restored."))
    else:
        messages.success(request, _("Overlay version restored."))

    return redirect(redirect_name, pk=overlay.pk)
