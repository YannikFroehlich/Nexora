from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from app import spotify_api
from app.forms import SignUpForm
from app.models import ScoreOverlay, SpotifyOverlay, TimerOverlay, WinChallenge


def home(request):
    return render(request, "app/home.html")


def demo(request):
    return render(request, "app/demo.html")


def about(request):
    return render(request, "app/about.html")


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    content = "\n".join(
        (
            "User-agent: *",
            "Allow: /",
            "Disallow: /accounts/",
            "Disallow: /admin/",
            "Disallow: /overlays/",
            "Disallow: /goals/",
            "Disallow: /scores/",
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


def safe_next_url(request, fallback="home"):
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
        return redirect(safe_next_url(request))

    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                is_first_user = not (get_user_model().objects.exclude(pk=user.pk).exists())

                if is_first_user:
                    SpotifyOverlay.objects.filter(owner__isnull=True).update(owner=user)
                    ScoreOverlay.objects.filter(owner__isnull=True).update(owner=user)
                    TimerOverlay.objects.filter(owner__isnull=True).update(owner=user)
                    WinChallenge.objects.filter(owner__isnull=True).update(owner=user)
                    spotify_api.adopt_connections(user)

            login(request, user)
            return redirect(safe_next_url(request))
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
