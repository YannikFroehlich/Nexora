from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app import overlay_transfer, overlay_versions
from app.forms import ChatOverlayForm, OverlayAssetUploadForm
from app.models import ChatOverlay, OverlayVersion, TwitchConnection
from app.views.common import (
    conditional_state_response,
    json_export_response,
    no_store,
    renew_public_obs_link,
)
from app.views.dashboard import manageable_chat_overlays
from app.views.pages import safe_next_url
from app.views.presets import manageable_presets


def get_manageable_chat_overlay(request, pk):
    return get_object_or_404(manageable_chat_overlays(request), pk=pk)


def chat_obs_url(request, chat):
    return request.build_absolute_uri(reverse("chat_overlay", args=[chat.public_token]))


def chat_editor_context(request, form, chat, is_create):
    context = {
        "form": form,
        "chat": chat,
        "is_create": is_create,
        "obs_url": "" if is_create else chat_obs_url(request, chat),
        "asset_upload_form": OverlayAssetUploadForm(prefix="asset"),
    }
    if not is_create:
        context.update(overlay_versions.editor_version_context(chat))
        context["style_presets"] = manageable_presets(request)
    return context


@login_required
def chat_list(request):
    return redirect(f"{reverse('overlay_dashboard')}#chat-overlays")


@login_required
def chat_create(request):
    chat = ChatOverlay()

    if request.method == "POST":
        form = ChatOverlayForm(request.POST, instance=chat, asset_owner=request.user)
        if form.is_valid():
            chat = form.save(commit=False)
            chat.owner = request.user
            chat.save()
            overlay_versions.record_version(chat, OverlayVersion.REASON_CREATED)
            messages.success(request, _("Chat overlay created."))
            return redirect("chat_manage", pk=chat.pk)
    else:
        form = ChatOverlayForm(instance=chat, asset_owner=request.user)
        # Start with the streamer's own channel when Twitch is already connected.
        connection = TwitchConnection.objects.filter(owner=request.user).first()
        if connection and connection.twitch_login:
            form.initial["channel"] = connection.twitch_login.lower()

    return render(
        request,
        "app/chat/create.html",
        chat_editor_context(request, form, chat, True),
    )


@login_required
def chat_manage(request, pk):
    chat = get_manageable_chat_overlay(request, pk)

    if request.method == "POST":
        form = ChatOverlayForm(request.POST, instance=chat, asset_owner=request.user)
        if form.is_valid():
            chat = form.save()
            overlay_versions.record_version(chat, OverlayVersion.REASON_MANUAL)
            messages.success(request, _("Chat overlay saved."))
            return redirect("chat_manage", pk=chat.pk)
    else:
        form = ChatOverlayForm(instance=chat, asset_owner=request.user)

    return render(
        request,
        "app/chat/create.html",
        chat_editor_context(request, form, chat, False),
    )


@login_required
@require_POST
def chat_autosave(request, pk):
    chat = get_manageable_chat_overlay(request, pk)
    form = ChatOverlayForm(request.POST, instance=chat, asset_owner=request.user)

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    chat = form.save()
    overlay_versions.record_version(chat, OverlayVersion.REASON_AUTOSAVE)
    return JsonResponse({"ok": True, "updated_at": chat.updated_at.isoformat()})


@login_required
@require_POST
def chat_delete(request, pk):
    chat = get_manageable_chat_overlay(request, pk)
    chat_name = chat.display_name
    overlay_versions.delete_versions(chat)
    chat.delete()
    messages.success(request, _("Chat overlay deleted: %(name)s") % {"name": chat_name})
    return redirect(f"{reverse('overlay_dashboard')}#chat-overlays")


@login_required
@require_POST
def chat_duplicate(request, pk):
    chat = get_manageable_chat_overlay(request, pk)
    duplicate = overlay_transfer.duplicate_overlay(chat, request.user, _("Copy"))
    overlay_versions.record_version(duplicate, OverlayVersion.REASON_CREATED)
    messages.success(
        request,
        _("Chat overlay duplicated: %(name)s") % {"name": duplicate.display_name},
    )
    return redirect(f"{reverse('overlay_dashboard')}#chat-overlays")


@login_required
@require_GET
def chat_export(request, pk):
    chat = get_manageable_chat_overlay(request, pk)
    return json_export_response(
        overlay_transfer.chat_export_payload(chat),
        overlay_transfer.CHAT_TYPE,
        chat.display_name,
    )


@login_required
@require_POST
def chat_renew_obs_link(request, pk):
    chat = get_manageable_chat_overlay(request, pk)
    return renew_public_obs_link(
        request,
        chat,
        safe_next_url(request, fallback="overlay_dashboard"),
    )


def public_chat(public_token):
    return get_object_or_404(
        ChatOverlay.objects.select_related("font_asset", "logo_asset", "background_asset"),
        public_token=public_token,
    )


@never_cache
def chat_overlay(request, public_token):
    chat = public_chat(public_token)
    return no_store(render(request, "app/chat/public_overlay.html", {"chat": chat}))


@never_cache
def chat_overlay_state(request, public_token):
    chat = public_chat(public_token)
    return conditional_state_response(
        request,
        chat.state_payload(),
        chat.updated_at.isoformat(),
    )
