from django.conf import settings

PUBLIC_INDEXABLE_URLS = {"home", "demo", "about"}


def app_metadata(request):
    current_url = getattr(request.resolver_match, "url_name", None)

    return {
        "APP_VERSION": settings.APP_VERSION,
        "CANONICAL_URL": request.build_absolute_uri(request.path),
        "IS_PUBLIC_INDEXABLE": current_url in PUBLIC_INDEXABLE_URLS,
    }
