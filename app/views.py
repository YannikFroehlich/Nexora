import secrets

from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from app.forms import (
    SignUpForm,
    SpotifyOverlayForm,
    WinChallengeCreateForm,
    WinChallengeDesignForm,
    WinChallengeGameForm,
    WinChallengeSettingsForm,
)
from app.models import SpotifyOverlay, WinChallenge, WinChallengeGame
from app import spotify_api


def home(request):
    template_name = "app/home.html"
    return render(request, template_name)


def about(request):
    template_name = "app/about.html"
    return render(request, template_name)


def _safe_next_url(request, fallback="home"):
    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url

    return reverse(fallback)


def signup(request):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request))

    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                is_first_user = not (
                    get_user_model().objects.exclude(pk=user.pk).exists()
                )

                if is_first_user:
                    SpotifyOverlay.objects.filter(owner__isnull=True).update(owner=user)
                    WinChallenge.objects.filter(owner__isnull=True).update(owner=user)

            login(request, user)
            return redirect(_safe_next_url(request))
    else:
        form = SignUpForm()

    return render(
        request,
        "app/registration/signup.html",
        {
            "form": form,
            "next": request.POST.get("next") or request.GET.get("next") or "",
        },
    )


def _manageable_spotify_overlays(request):
    return SpotifyOverlay.objects.filter(owner=request.user)


def _get_manageable_spotify_overlay(request, pk):
    return get_object_or_404(_manageable_spotify_overlays(request), pk=pk)


def _spotify_obs_url(request, overlay):
    return request.build_absolute_uri(
        reverse("spotify_overlay", args=[overlay.public_token])
    )


def _spotify_editor_context(request, form, overlay, is_create):
    return {
        "form": form,
        "overlay": overlay,
        "is_create": is_create,
        "spotify_configured": spotify_api.is_configured(),
        "obs_url": "" if is_create else _spotify_obs_url(request, overlay),
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


@login_required
def spotify_list(request):
    return render(
        request,
        "app/spotify/list.html",
        {
            "overlays": _manageable_spotify_overlays(request),
            "sample_playback": {
                "title": "Midnight Drive",
                "artist": "Nova Waves",
                "album": "Neon Horizons",
                "image_url": "",
                "progress_ms": 102000,
                "duration_ms": 228000,
                "is_playing": True,
            },
        },
    )


@login_required
def spotify_create(request):
    overlay = SpotifyOverlay()

    if request.method == "POST":
        form = SpotifyOverlayForm(request.POST, instance=overlay)

        if form.is_valid():
            overlay = form.save(commit=False)

            overlay.owner = request.user
            overlay.save()
            messages.success(request, _("Spotify overlay created."))
            return redirect("spotify_manage", pk=overlay.pk)
    else:
        form = SpotifyOverlayForm(instance=overlay)

    return render(
        request,
        "app/spotify/create.html",
        _spotify_editor_context(request, form, overlay, True),
    )


@login_required
def spotify_manage(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)

    if request.method == "POST":
        form = SpotifyOverlayForm(request.POST, instance=overlay)

        if form.is_valid():
            form.save()
            messages.success(request, _("Spotify overlay saved."))
            return redirect("spotify_manage", pk=overlay.pk)
    else:
        form = SpotifyOverlayForm(instance=overlay)

    return render(
        request,
        "app/spotify/create.html",
        _spotify_editor_context(request, form, overlay, False),
    )


@login_required
@require_POST
def spotify_delete(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)
    overlay_name = overlay.display_name
    overlay.delete()
    messages.success(request, _("Spotify overlay deleted: %(name)s") % {"name": overlay_name})
    return redirect("spotify_list")


@login_required
def spotify_connect(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)

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
        return redirect("spotify_list")

    overlay = _get_manageable_spotify_overlay(request, overlay_id)

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
        messages.error(request, _("Spotify could not be connected. Check your app settings."))
    else:
        messages.success(request, _("Spotify connected successfully."))

    return redirect("spotify_manage", pk=overlay.pk)


@login_required
@require_POST
def spotify_disconnect(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)
    spotify_api.disconnect(overlay)
    messages.success(request, _("Spotify disconnected."))
    return redirect("spotify_manage", pk=overlay.pk)


@never_cache
def spotify_overlay(request, public_token):
    overlay = get_object_or_404(SpotifyOverlay, public_token=public_token)
    response = render(
        request,
        "app/spotify/public_overlay.html",
        {
            "overlay": overlay,
            "sample_playback": spotify_api.empty_playback(),
        },
    )
    return _no_store(response)


@never_cache
def spotify_overlay_state(request, public_token):
    overlay = get_object_or_404(SpotifyOverlay, public_token=public_token)
    return _no_store(JsonResponse(spotify_api.overlay_state_payload(overlay)))


def _manageable_winchallenges(request):
    return WinChallenge.objects.prefetch_related("games").filter(owner=request.user)


def _get_manageable_winchallenge(request, pk):
    return get_object_or_404(_manageable_winchallenges(request), pk=pk)


def _obs_url(request, challenge):
    return request.build_absolute_uri(
        reverse("winchallenge_overlay", args=[challenge.public_token])
    )


def _touch_challenge(challenge):
    WinChallenge.objects.filter(pk=challenge.pk).update(updated_at=timezone.now())


def _fresh_challenge(challenge):
    return get_object_or_404(
        WinChallenge.objects.prefetch_related("games"),
        pk=challenge.pk,
    )


def _no_store(response):
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def _state_response(challenge):
    response = JsonResponse(_fresh_challenge(challenge).state_payload())
    return _no_store(response)


@login_required
def winchallenge_list(request):
    return render(
        request,
        "app/winchallenge/list.html",
        {
            "challenges": _manageable_winchallenges(request),
        },
    )


@login_required
def winchallenge_create(request):
    if request.method == "POST":
        form = WinChallengeCreateForm(request.POST)

        if form.is_valid():
            challenge = form.save(commit=False)

            challenge.owner = request.user
            challenge.save()
            messages.success(request, _("Win Challenge created."))
            return redirect("winchallenge_manage", pk=challenge.pk)
    else:
        form = WinChallengeCreateForm()

    return render(
        request,
        "app/winchallenge/create.html",
        {
            "form": form,
            "preview_challenge": WinChallenge(title=_("Win Challenge")),
        },
    )


@login_required
def winchallenge_manage(request, pk):
    challenge = _get_manageable_winchallenge(request, pk)

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "challenge":
            settings_form = WinChallengeSettingsForm(request.POST, instance=challenge)
            design_form = WinChallengeDesignForm(instance=challenge)

            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, _("Challenge settings saved."))
                return redirect(f"{reverse('winchallenge_manage', args=[challenge.pk])}#challenge")
        elif form_type == "design":
            settings_form = WinChallengeSettingsForm(instance=challenge)
            design_form = WinChallengeDesignForm(request.POST, instance=challenge)

            if design_form.is_valid():
                design_form.save()
                messages.success(request, _("Overlay design saved."))
                return redirect(f"{reverse('winchallenge_manage', args=[challenge.pk])}#design")
        else:
            settings_form = WinChallengeSettingsForm(instance=challenge)
            design_form = WinChallengeDesignForm(instance=challenge)
    else:
        settings_form = WinChallengeSettingsForm(instance=challenge)
        design_form = WinChallengeDesignForm(instance=challenge)

    return render(
        request,
        "app/winchallenge/manage.html",
        {
            "challenge": challenge,
            "settings_form": settings_form,
            "design_form": design_form,
            "game_form": WinChallengeGameForm(),
            "obs_url": _obs_url(request, challenge),
        },
    )


@login_required
@require_POST
def winchallenge_delete(request, pk):
    challenge = _get_manageable_winchallenge(request, pk)
    challenge_title = challenge.display_title
    challenge.delete()
    messages.success(request, _("Win Challenge deleted: %(name)s") % {"name": challenge_title})

    return redirect("winchallenge_list")


@login_required
@require_POST
def winchallenge_game_add(request, pk):
    challenge = _get_manageable_winchallenge(request, pk)

    if challenge.games.count() >= WinChallenge.MAX_GAMES:
        return JsonResponse(
            {"error": f"Max. {WinChallenge.MAX_GAMES} {_('Games')}."},
            status=400,
        )

    form_data = request.POST.copy()

    if not form_data.get("wins"):
        form_data["wins"] = 0

    form = WinChallengeGameForm(form_data)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    max_order = challenge.games.aggregate(max_order=Max("sort_order"))["max_order"]
    game = form.save(commit=False)
    game.challenge = challenge
    game.sort_order = 0 if max_order is None else max_order + 1
    game.save()
    _touch_challenge(challenge)

    return _state_response(challenge)


@login_required
@require_POST
def winchallenge_game_wins(request, pk, game_pk):
    challenge = _get_manageable_winchallenge(request, pk)

    try:
        delta = int(request.POST.get("delta", 0))
    except ValueError:
        return JsonResponse({"error": _("Invalid win change.")}, status=400)

    if delta not in (-1, 1):
        return JsonResponse({"error": _("Invalid win change.")}, status=400)

    with transaction.atomic():
        game = get_object_or_404(
            WinChallengeGame.objects.select_for_update(),
            pk=game_pk,
            challenge=challenge,
        )

        if delta > 0:
            WinChallengeGame.objects.filter(pk=game.pk).update(wins=F("wins") + 1)
        elif game.wins > 0:
            WinChallengeGame.objects.filter(pk=game.pk).update(wins=F("wins") - 1)

        _touch_challenge(challenge)

    return _state_response(challenge)


@login_required
@require_POST
def winchallenge_game_rename(request, pk, game_pk):
    challenge = _get_manageable_winchallenge(request, pk)
    new_name = request.POST.get("name", "").strip()
    wins = request.POST.get("wins", "").strip()
    target_wins = request.POST.get("target_wins", "").strip()

    if not new_name:
        return JsonResponse({"error": _("Game name is required.")}, status=400)

    game = get_object_or_404(WinChallengeGame, pk=game_pk, challenge=challenge)
    form = WinChallengeGameForm(
        {
            "name": new_name,
            "wins": wins or game.wins,
            "target_wins": target_wins or game.target_wins,
        },
        instance=game,
    )

    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    form.save()
    _touch_challenge(challenge)

    return _state_response(challenge)


@login_required
@require_POST
def winchallenge_game_delete(request, pk, game_pk):
    challenge = _get_manageable_winchallenge(request, pk)
    game = get_object_or_404(WinChallengeGame, pk=game_pk, challenge=challenge)
    game.delete()
    _touch_challenge(challenge)

    return _state_response(challenge)


@never_cache
def winchallenge_overlay(request, public_token):
    challenge = get_object_or_404(
        WinChallenge.objects.prefetch_related("games"),
        public_token=public_token,
    )
    response = render(
        request,
        "app/winchallenge/public_overlay.html",
        {
            "challenge": challenge,
        },
    )

    return _no_store(response)


@never_cache
def winchallenge_overlay_state(request, public_token):
    challenge = get_object_or_404(
        WinChallenge.objects.prefetch_related("games"),
        public_token=public_token,
    )

    return _no_store(JsonResponse(challenge.state_payload()))
