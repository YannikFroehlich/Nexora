import hashlib
import json
import uuid

from django.contrib import messages
from django.http import FileResponse, HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import parse_etags
from django.utils.text import slugify
from django.utils.translation import gettext as _

from app.models import OverlayAsset
from app.upload_validators import asset_content_type


def no_store(response):
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def conditional_state_response(request, payload, version):
    digest = hashlib.sha256(str(version).encode("utf-8")).hexdigest()
    etag = f'"{digest}"'

    if etag in parse_etags(request.headers.get("If-None-Match", "")):
        response = HttpResponseNotModified()
    else:
        response = JsonResponse(payload)

    response["ETag"] = etag
    return no_store(response)


def json_export_response(payload, overlay_type, overlay_name):
    filename_slug = slugify(str(overlay_name))[:60] or "overlay"
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="nexora-{overlay_type}-{filename_slug}.json"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return no_store(response)


def renew_public_obs_link(request, overlay, redirect_url):
    overlay.public_token = uuid.uuid4()
    overlay.save(update_fields=("public_token", "updated_at"))
    messages.success(
        request,
        _("OBS link renewed. Replace the previous URL in OBS."),
    )
    return redirect(redirect_url)


def overlay_asset_file(request, public_token):
    asset = get_object_or_404(OverlayAsset, public_token=public_token)
    response = FileResponse(
        asset.file.open("rb"),
        content_type=asset_content_type(asset.file.name),
        filename=asset.file.name.rsplit("/", 1)[-1],
        as_attachment=False,
    )
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response
