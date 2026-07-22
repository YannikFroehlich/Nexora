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
    WinChallengeCreateForm,
    WinChallengeDesignForm,
    WinChallengeGameForm,
    WinChallengeSettingsForm,
)
from app.models import OverlayVersion, WinChallenge, WinChallengeGame
from app.views.common import (
    conditional_state_response,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_winchallenges
from app.views.pages import safe_next_url


def get_manageable_winchallenge(request, pk):
    return get_object_or_404(manageable_winchallenges(request), pk=pk)


def winchallenge_obs_url(request, challenge):
    return request.build_absolute_uri(
        reverse("winchallenge_overlay", args=[challenge.public_token])
    )


def touch_challenge(challenge):
    WinChallenge.objects.filter(pk=challenge.pk).update(updated_at=timezone.now())
    challenge._prefetched_objects_cache.pop("games", None)


def fresh_challenge(challenge):
    return get_object_or_404(
        WinChallenge.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ).prefetch_related("games"),
        pk=challenge.pk,
    )


def state_response(challenge):
    return no_store(JsonResponse(fresh_challenge(challenge).state_payload()))


@login_required
def winchallenge_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#winchallenge-overlays")


@login_required
def winchallenge_create(request):
    if request.method == "POST":
        form = WinChallengeCreateForm(request.POST, asset_owner=request.user)

        if form.is_valid():
            challenge = form.save(commit=False)
            challenge.owner = request.user
            challenge.save()
            overlay_versions.record_version(challenge, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Win Challenge created."))
            return redirect("winchallenge_manage", pk=challenge.pk)
    else:
        form = WinChallengeCreateForm(asset_owner=request.user)

    return render(
        request,
        "app/winchallenge/create.html",
        {
            "form": form,
            "preview_challenge": WinChallenge(title=_("Win Challenge")),
            "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
        },
    )


@login_required
def winchallenge_manage(request, pk):
    challenge = get_manageable_winchallenge(request, pk)

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "challenge":
            settings_form = WinChallengeSettingsForm(request.POST, instance=challenge)
            design_form = WinChallengeDesignForm(
                instance=challenge,
                asset_owner=request.user,
            )

            if settings_form.is_valid():
                challenge = settings_form.save()
                overlay_versions.record_version(challenge, OverlayVersion.REASON_MANUAL)
                messages.success(request, _("Challenge settings saved."))
                return redirect(f"{reverse('winchallenge_manage', args=[challenge.pk])}#challenge")
        elif form_type == "design":
            settings_form = WinChallengeSettingsForm(instance=challenge)
            design_form = WinChallengeDesignForm(
                request.POST,
                instance=challenge,
                asset_owner=request.user,
            )

            if design_form.is_valid():
                challenge = design_form.save()
                overlay_versions.record_version(challenge, OverlayVersion.REASON_MANUAL)
                messages.success(request, _("Overlay design saved."))
                return redirect(f"{reverse('winchallenge_manage', args=[challenge.pk])}#design")
        else:
            settings_form = WinChallengeSettingsForm(instance=challenge)
            design_form = WinChallengeDesignForm(
                instance=challenge,
                asset_owner=request.user,
            )
    else:
        settings_form = WinChallengeSettingsForm(instance=challenge)
        design_form = WinChallengeDesignForm(
            instance=challenge,
            asset_owner=request.user,
        )

    context = {
        "challenge": challenge,
        "settings_form": settings_form,
        "design_form": design_form,
        "game_form": WinChallengeGameForm(),
        "obs_url": winchallenge_obs_url(request, challenge),
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
    }
    context.update(overlay_versions.editor_version_context(challenge))
    return render(
        request,
        "app/winchallenge/manage.html",
        context,
    )


@login_required
@require_POST
def winchallenge_autosave(request, pk):
    challenge = get_manageable_winchallenge(request, pk)
    form_type = request.POST.get("form_type")

    if form_type == "challenge":
        form = WinChallengeSettingsForm(request.POST, instance=challenge)
    elif form_type == "design":
        form = WinChallengeDesignForm(
            request.POST,
            instance=challenge,
            asset_owner=request.user,
        )
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
    overlay_versions.record_version(challenge, OverlayVersion.REASON_AUTOSAVE)
    return JsonResponse(
        {
            "ok": True,
            "updated_at": challenge.updated_at.isoformat(),
        }
    )


@login_required
@require_POST
def winchallenge_delete(request, pk):
    challenge = get_manageable_winchallenge(request, pk)
    challenge_title = challenge.display_title
    overlay_versions.delete_versions(challenge)
    challenge.delete()
    messages.success(
        request,
        _("Win Challenge deleted: %(name)s") % {"name": challenge_title},
    )
    return redirect(f"{reverse('overlay_dashboard')}#winchallenge-overlays")


@login_required
@require_POST
def winchallenge_duplicate(request, pk):
    challenge = get_manageable_winchallenge(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(challenge, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(
        request,
        _("Win Challenge duplicated: %(name)s") % {"name": duplicate.display_title},
    )
    return redirect(f"{reverse('overlay_dashboard')}#winchallenge-overlays")


@login_required
@require_GET
def winchallenge_export(request, pk):
    challenge = get_manageable_winchallenge(request, pk)
    return json_export_response(
        overlay_transfer.winchallenge_export_payload(challenge),
        overlay_transfer.WINCHALLENGE_TYPE,
        challenge.display_title,
    )


@login_required
@require_POST
def winchallenge_renew_obs_link(request, pk):
    challenge = get_manageable_winchallenge(request, pk)
    return renew_public_obs_link(
        request,
        challenge,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


@login_required
@require_POST
def winchallenge_game_add(request, pk):
    challenge = get_manageable_winchallenge(request, pk)

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
    touch_challenge(challenge)
    overlay_versions.record_version(challenge, OverlayVersion.REASON_AUTOSAVE)

    return state_response(challenge)


@login_required
@require_POST
def winchallenge_game_wins(request, pk, game_pk):
    challenge = get_manageable_winchallenge(request, pk)

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
            WinChallengeGame.objects.filter(
                pk=game.pk,
                wins__lt=WinChallengeGame.MAX_WINS,
            ).update(wins=F("wins") + 1)
        elif game.wins > 0:
            WinChallengeGame.objects.filter(pk=game.pk).update(wins=F("wins") - 1)

        touch_challenge(challenge)
        overlay_versions.record_version(challenge, OverlayVersion.REASON_AUTOSAVE)

    return state_response(challenge)


@login_required
@require_POST
def winchallenge_game_rename(request, pk, game_pk):
    challenge = get_manageable_winchallenge(request, pk)
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
    touch_challenge(challenge)
    overlay_versions.record_version(challenge, OverlayVersion.REASON_AUTOSAVE)

    return state_response(challenge)


@login_required
@require_POST
def winchallenge_game_delete(request, pk, game_pk):
    challenge = get_manageable_winchallenge(request, pk)
    game = get_object_or_404(WinChallengeGame, pk=game_pk, challenge=challenge)
    game.delete()
    touch_challenge(challenge)
    overlay_versions.record_version(challenge, OverlayVersion.REASON_AUTOSAVE)

    return state_response(challenge)


@never_cache
def winchallenge_overlay(request, public_token):
    challenge = get_object_or_404(
        WinChallenge.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ).prefetch_related("games"),
        public_token=public_token,
    )
    response = render(
        request,
        "app/winchallenge/public_overlay.html",
        {"challenge": challenge},
    )
    return no_store(response)


@never_cache
def winchallenge_overlay_state(request, public_token):
    challenge = get_object_or_404(
        WinChallenge.objects.select_related(
            "font_asset",
            "logo_asset",
            "background_asset",
        ).prefetch_related("games"),
        public_token=public_token,
    )
    return conditional_state_response(
        request,
        challenge.state_payload(),
        challenge.updated_at.isoformat(),
    )
