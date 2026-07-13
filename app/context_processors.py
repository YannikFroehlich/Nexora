from django.conf import settings


def app_metadata(request):
    return {
        "APP_VERSION": settings.APP_VERSION,
    }
