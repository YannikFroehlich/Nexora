import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app import overlay_transfer, overlay_versions, spotify_api
from app.forms import OverlayAssetUploadForm, SpotifyOverlayForm
from app.models import OverlayVersion, SpotifyOverlay
from app.views.common import (
    conditional_state_response,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_spotify_overlays
from app.views.pages import safe_next_url
from app.views.presets import manageable_presets


def get_manageable_spotify_overlay(request, pk):
    return get_object_or_404(manageable_spotify_overlays(request), pk=pk)


def spotify_obs_url(request, overlay):
    return request.build_absolute_uri(reverse("spotify_overlay", args=[overlay.public_token]))


def spotify_editor_context(request, form, overlay, is_create):
    context = {
        "form": form,
        "overlay": overlay,
        "is_create": is_create,
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
        "spotify_configured": spotify_api.is_configured(),
        "obs_url": "" if is_create else spotify_obs_url(request, overlay),
        "sample_playback": {
            "title": "Midnight Drive",
            "artist": "Nova Waves",
            "album": "Neon Horizons",
            "image_url": "",
            "progress_ms": 102000,
            "duration_ms": 228000,
            "is_playing": True,
        },
    }
    if not is_create:
        context.update(overlay_versions.editor_version_context(overlay))
        context["style_presets"] = manageable_presets(request)
    return context


@login_required
def spotify_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")


@login_required
def spotify_create(request):
    overlay = SpotifyOverlay()

    if request.method == "POST":
        form = SpotifyOverlayForm(
            request.POST,
            instance=overlay,
            asset_owner=request.user,
        )

        if form.is_valid():
            overlay = form.save(commit=False)
            overlay.owner = request.user
            overlay.connection = spotify_api.connection_for_owner(request.user)
            overlay.save()
            overlay_versions.record_version(overlay, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Spotify overlay created."))
            return redirect("spotify_manage", pk=overlay.pk)
    else:
        form = SpotifyOverlayForm(instance=overlay, asset_owner=request.user)

    return render(
        request,
        "app/spotify/create.html",
        spotify_editor_context(request, form, overlay, True),
    )


@login_required
def spotify_manage(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)

    if request.method == "POST":
        form = SpotifyOverlayForm(
            request.POST,
            instance=overlay,
            asset_owner=request.user,
        )

        if form.is_valid():
            overlay = form.save()
            overlay_versions.record_version(overlay, OverlayVersion.REASON_MANUAL)
            messages.success(request, _("Spotify overlay saved."))
            return redirect("spotify_manage", pk=overlay.pk)
    else:
        form = SpotifyOverlayForm(instance=overlay, asset_owner=request.user)

    return render(
        request,
        "app/spotify/create.html",
        spotify_editor_context(request, form, overlay, False),
    )


@login_required
@require_POST
def spotify_autosave(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)
    form = SpotifyOverlayForm(
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
    return JsonResponse(
        {
            "ok": True,
            "updated_at": overlay.updated_at.isoformat(),
        }
    )


@login_required
@require_POST
def spotify_delete(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)
    overlay_name = overlay.display_name
    overlay_versions.delete_versions(overlay)
    overlay.delete()
    messages.success(
        request,
        _("Spotify overlay deleted: %(name)s") % {"name": overlay_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")


@login_required
@require_POST
def spotify_duplicate(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(overlay, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(
        request,
        _("Spotify overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")


@login_required
@require_GET
def spotify_export(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)
    return json_export_response(
        overlay_transfer.spotify_export_payload(overlay),
        overlay_transfer.SPOTIFY_TYPE,
        overlay.display_name,
    )


@login_required
@require_POST
def spotify_renew_obs_link(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)
    return renew_public_obs_link(
        request,
        overlay,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


@login_required
def spotify_connect(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)

    if not spotify_api.is_configured():
        messages.error(
            request,
            _("Add your Spotify client credentials to the environment before connecting."),
        )
        return redirect("spotify_manage", pk=overlay.pk)

    state = secrets.token_urlsafe(32)
    request.session["spotify_oauth"] = {
        "state": state,
        "overlay_id": overlay.pk,
    }
    return redirect(spotify_api.authorization_url(request, state))


@login_required
def spotify_callback(request):
    oauth_session = request.session.pop("spotify_oauth", None)
    received_state = request.GET.get("state", "")
    overlay_id = oauth_session.get("overlay_id") if oauth_session else None

    if (
        not oauth_session
        or not overlay_id
        or not received_state
        or not secrets.compare_digest(received_state, oauth_session.get("state", ""))
    ):
        messages.error(request, _("The Spotify connection could not be verified."))
        return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")

    overlay = get_manageable_spotify_overlay(request, overlay_id)

    if request.GET.get("error"):
        messages.error(request, _("Spotify access was not granted."))
        return redirect("spotify_manage", pk=overlay.pk)

    code = request.GET.get("code", "")

    if not code:
        messages.error(request, _("Spotify returned no authorization code."))
        return redirect("spotify_manage", pk=overlay.pk)

    try:
        spotify_api.exchange_authorization_code(request, overlay, code)
    except spotify_api.SpotifyAPIError:
        messages.error(
            request,
            _("Spotify could not be connected. Check your app settings."),
        )
    else:
        messages.success(request, _("Spotify connected successfully."))

    return redirect("spotify_manage", pk=overlay.pk)


@login_required
@require_POST
def spotify_disconnect(request, pk):
    overlay = get_manageable_spotify_overlay(request, pk)
    spotify_api.disconnect(overlay)
    messages.success(request, _("Spotify disconnected from all overlays."))
    return redirect("spotify_manage", pk=overlay.pk)


@never_cache
def spotify_overlay(request, public_token):
    overlay = get_object_or_404(
        SpotifyOverlay.objects.select_related(
            "connection",
            "font_asset",
            "logo_asset",
            "background_asset",
        ),
        public_token=public_token,
    )
    response = render(
        request,
        "app/spotify/public_overlay.html",
        {
            "overlay": overlay,
            "sample_playback": spotify_api.empty_playback(),
        },
    )
    return no_store(response)


@never_cache
def spotify_overlay_state(request, public_token):
    overlay = get_object_or_404(
        SpotifyOverlay.objects.select_related(
            "connection",
            "font_asset",
            "logo_asset",
            "background_asset",
        ),
        public_token=public_token,
    )
    payload = spotify_api.overlay_state_payload(overlay)
    connection_version = ""

    if overlay.connection_id:
        cached_at = overlay.connection.playback_cached_at
        connection_version = (
            f"{overlay.connection.updated_at.isoformat()}:"
            f"{cached_at.isoformat() if cached_at else ''}"
        )

    return conditional_state_response(
        request,
        payload,
        f"{overlay.updated_at.isoformat()}:{connection_version}",
    )
