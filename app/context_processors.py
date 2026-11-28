from django.conf import settings
from django.templatetags.static import static

from app import oidc

PUBLIC_INDEXABLE_URLS = {"home", "demo", "about"}


def app_metadata(request):
    current_url = getattr(request.resolver_match, "url_name", None)

    return {
        "APP_VERSION": settings.APP_VERSION,
        "CANONICAL_URL": request.build_absolute_uri(request.path),
        "IS_PUBLIC_INDEXABLE": current_url in PUBLIC_INDEXABLE_URLS,
        "OIDC_ENABLED": oidc.is_configured(),
        "SHARE_IMAGE_URL": request.build_absolute_uri(static("imgs/og-image.png")),
        "OIDC_ONLY": oidc.oidc_only(),
        "SIGNUP_ENABLED": settings.SIGNUP_ENABLED and not oidc.oidc_only(),
        "TITLE_SUFFIX": settings.TITLE_SUFFIX,
    }
