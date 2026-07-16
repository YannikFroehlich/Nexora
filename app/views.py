import json
import secrets

from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app.forms import (
    SignUpForm,
    OverlayImportForm,
    SpotifyOverlayForm,
    TimerOverlayForm,
    WinChallengeCreateForm,
    WinChallengeDesignForm,
    WinChallengeGameForm,
    WinChallengeSettingsForm,
)
from app.models import SpotifyOverlay, TimerOverlay, WinChallenge, WinChallengeGame
from app import overlay_transfer, spotify_api


def home(request):
    template_name = "app/home.html"
    return render(request, template_name)


def demo(request):
    return render(request, "app/demo.html")


def about(request):
    template_name = "app/about.html"
    return render(request, template_name)


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    content = "\n".join(
        (
            "User-agent: *",
            "Allow: /",
            "Disallow: /accounts/",
            "Disallow: /admin/",
            "Disallow: /overlays/",
            "Disallow: /spotify/",
            "Disallow: /timers/",
            "Disallow: /winchallenges/",
            f"Sitemap: {sitemap_url}",
        )
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap(request):
    public_urls = (
        request.build_absolute_uri(reverse("home")),
        request.build_absolute_uri(reverse("demo")),
        request.build_absolute_uri(reverse("about")),
    )
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in public_urls)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )
    return HttpResponse(content, content_type="application/xml; charset=utf-8")


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
                    TimerOverlay.objects.filter(owner__isnull=True).update(owner=user)
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


def _json_export_response(payload, overlay_type, overlay_name):
    filename_slug = slugify(str(overlay_name))[:60] or "overlay"
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="nexora-{overlay_type}-{filename_slug}.json"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return _no_store(response)


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
    return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")


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
def spotify_autosave(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)
    form = SpotifyOverlayForm(request.POST, instance=overlay)

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    form.save()
    return JsonResponse(
        {
            "ok": True,
            "updated_at": overlay.updated_at.isoformat(),
        }
    )


@login_required
@require_POST
def spotify_delete(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)
    overlay_name = overlay.display_name
    overlay.delete()
    messages.success(request, _("Spotify overlay deleted: %(name)s") % {"name": overlay_name})
    return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")


@login_required
@require_POST
def spotify_duplicate(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(overlay, request.user, _("Copy"))
    messages.success(
        request,
        _("Spotify overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")


@login_required
@require_GET
def spotify_export(request, pk):
    overlay = _get_manageable_spotify_overlay(request, pk)
    return _json_export_response(
        overlay_transfer.spotify_export_payload(overlay),
        overlay_transfer.SPOTIFY_TYPE,
        overlay.display_name,
    )


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
        return redirect(f"{reverse('overlay_dashboard')}#spotify-overlays")

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


def _manageable_timer_overlays(request):
    return TimerOverlay.objects.filter(owner=request.user)


def _overlay_dashboard_context(request, import_form=None):
    spotify_overlays = list(_manageable_spotify_overlays(request))
    win_challenges = list(_manageable_winchallenges(request))
    timer_overlays = list(_manageable_timer_overlays(request))
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
        _overlay_dashboard_context(request),
    )


@login_required
@require_POST
def overlay_import(request):
    import_form = OverlayImportForm(request.POST, request.FILES)

    if import_form.is_valid():
        try:
            payload = overlay_transfer.load_payload(
                import_form.cleaned_data["overlay_file"]
            )
            overlay = overlay_transfer.import_payload(payload, request.user)
        except overlay_transfer.OverlayTransferError as error:
            import_form.add_error("overlay_file", str(error))
        else:
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
        _overlay_dashboard_context(request, import_form),
        status=400,
    )


def _get_manageable_timer_overlay(request, pk):
    return get_object_or_404(_manageable_timer_overlays(request), pk=pk)


def _timer_obs_url(request, timer):
    return request.build_absolute_uri(
        reverse("timer_overlay", args=[timer.public_token])
    )


def _timer_editor_context(request, form, timer, is_create):
    return {
        "form": form,
        "timer": timer,
        "is_create": is_create,
        "obs_url": "" if is_create else _timer_obs_url(request, timer),
    }


@login_required
def timer_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#timer-overlays")


@login_required
def timer_create(request):
    timer = TimerOverlay()

    if request.method == "POST":
        form = TimerOverlayForm(request.POST, instance=timer)
        if form.is_valid():
            timer = form.save(commit=False)
            timer.owner = request.user
            timer.save()
            messages.success(request, _("Timer overlay created."))
            return redirect("timer_manage", pk=timer.pk)
    else:
        form = TimerOverlayForm(instance=timer)

    return render(
        request,
        "app/timer/create.html",
        _timer_editor_context(request, form, timer, True),
    )


@login_required
def timer_manage(request, pk):
    timer = _get_manageable_timer_overlay(request, pk)

    if request.method == "POST":
        form = TimerOverlayForm(request.POST, instance=timer)
        if form.is_valid():
            form.save()
            messages.success(request, _("Timer overlay saved."))
            return redirect("timer_manage", pk=timer.pk)
    else:
        form = TimerOverlayForm(instance=timer)

    return render(
        request,
        "app/timer/create.html",
        _timer_editor_context(request, form, timer, False),
    )


@login_required
@require_POST
def timer_autosave(request, pk):
    timer = _get_manageable_timer_overlay(request, pk)
    form = TimerOverlayForm(request.POST, instance=timer)

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    timer = form.save()
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

    return _no_store(JsonResponse(timer.state_payload()))


@login_required
@require_POST
def timer_delete(request, pk):
    timer = _get_manageable_timer_overlay(request, pk)
    timer_name = timer.display_name
    timer.delete()
    messages.success(request, _("Timer overlay deleted: %(name)s") % {"name": timer_name})
    return redirect(f"{reverse('overlay_dashboard')}#timer-overlays")


@login_required
@require_POST
def timer_duplicate(request, pk):
    timer = _get_manageable_timer_overlay(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(timer, request.user, _("Copy"))
    messages.success(
        request,
        _("Timer overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#timer-overlays")


@login_required
@require_GET
def timer_export(request, pk):
    timer = _get_manageable_timer_overlay(request, pk)
    return _json_export_response(
        overlay_transfer.timer_export_payload(timer),
        overlay_transfer.TIMER_TYPE,
        timer.display_name,
    )


@never_cache
def timer_overlay(request, public_token):
    timer = get_object_or_404(TimerOverlay, public_token=public_token)
    response = render(request, "app/timer/public_overlay.html", {"timer": timer})
    return _no_store(response)


@never_cache
def timer_overlay_state(request, public_token):
    timer = get_object_or_404(TimerOverlay, public_token=public_token)
    return _no_store(JsonResponse(timer.state_payload()))


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
    return redirect(f"{reverse('overlay_dashboard')}#winchallenge-overlays")


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
def winchallenge_autosave(request, pk):
    challenge = _get_manageable_winchallenge(request, pk)
    form_type = request.POST.get("form_type")

    if form_type == "challenge":
        form = WinChallengeSettingsForm(request.POST, instance=challenge)
    elif form_type == "design":
        form = WinChallengeDesignForm(request.POST, instance=challenge)
    else:
        return JsonResponse(
            {"ok": False, "error": _("Unknown autosave form.")},
            status=400,
        )

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    form.save(commit=False)
    challenge.save(update_fields=[*form.fields, "updated_at"])
    return JsonResponse(
        {
            "ok": True,
            "updated_at": challenge.updated_at.isoformat(),
        }
    )


@login_required
@require_POST
def winchallenge_delete(request, pk):
    challenge = _get_manageable_winchallenge(request, pk)
    challenge_title = challenge.display_title
    challenge.delete()
    messages.success(request, _("Win Challenge deleted: %(name)s") % {"name": challenge_title})

    return redirect(f"{reverse('overlay_dashboard')}#winchallenge-overlays")


@login_required
@require_POST
def winchallenge_duplicate(request, pk):
    challenge = _get_manageable_winchallenge(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(challenge, request.user, _("Copy"))
    messages.success(
        request,
        _("Win Challenge duplicated: %(name)s") % {"name": duplicate.display_title},
    )
    return redirect(f"{reverse('overlay_dashboard')}#winchallenge-overlays")


@login_required
@require_GET
def winchallenge_export(request, pk):
    challenge = _get_manageable_winchallenge(request, pk)
    return _json_export_response(
        overlay_transfer.winchallenge_export_payload(challenge),
        overlay_transfer.WINCHALLENGE_TYPE,
        challenge.display_title,
    )


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
