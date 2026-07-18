from django.contrib.auth import views as auth_views
from django.urls import path

from app import views
from app.forms import LoginForm

urlpatterns = [
    path('', views.home, name='home'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('sitemap.xml', views.sitemap, name='sitemap'),
    path('demo/', views.demo, name='demo'),
    path('about/', views.about, name='about'),
    path(
        'accounts/login/',
        auth_views.LoginView.as_view(
            template_name='app/registration/login.html',
            authentication_form=LoginForm,
        ),
        name='login',
    ),
    path(
        'accounts/logout/',
        auth_views.LogoutView.as_view(),
        name='logout',
    ),
    path('accounts/signup/', views.signup, name='signup'),
    path('overlays/', views.overlay_dashboard, name='overlay_dashboard'),
    path('overlays/import/', views.overlay_import, name='overlay_import'),
    path('spotify/', views.spotify_list, name='spotify_list'),
    path('spotify/new/', views.spotify_create, name='spotify_create'),
    path('spotify/callback/', views.spotify_callback, name='spotify_callback'),
    path('spotify/<int:pk>/', views.spotify_manage, name='spotify_manage'),
    path('spotify/<int:pk>/autosave/', views.spotify_autosave, name='spotify_autosave'),
    path('spotify/<int:pk>/duplicate/', views.spotify_duplicate, name='spotify_duplicate'),
    path('spotify/<int:pk>/export/', views.spotify_export, name='spotify_export'),
    path('spotify/<int:pk>/delete/', views.spotify_delete, name='spotify_delete'),
    path('spotify/<int:pk>/connect/', views.spotify_connect, name='spotify_connect'),
    path('spotify/<int:pk>/disconnect/', views.spotify_disconnect, name='spotify_disconnect'),
    path(
        'overlays/spotify/<uuid:public_token>/',
        views.spotify_overlay,
        name='spotify_overlay',
    ),
    path(
        'overlays/spotify/<uuid:public_token>/state/',
        views.spotify_overlay_state,
        name='spotify_overlay_state',
    ),
    path('timers/', views.timer_list, name='timer_list'),
    path('timers/new/', views.timer_create, name='timer_create'),
    path('timers/<int:pk>/', views.timer_manage, name='timer_manage'),
    path('timers/<int:pk>/autosave/', views.timer_autosave, name='timer_autosave'),
    path('timers/<int:pk>/control/', views.timer_control, name='timer_control'),
    path('timers/<int:pk>/duplicate/', views.timer_duplicate, name='timer_duplicate'),
    path('timers/<int:pk>/export/', views.timer_export, name='timer_export'),
    path('timers/<int:pk>/delete/', views.timer_delete, name='timer_delete'),
    path(
        'overlays/timer/<uuid:public_token>/',
        views.timer_overlay,
        name='timer_overlay',
    ),
    path(
        'overlays/timer/<uuid:public_token>/state/',
        views.timer_overlay_state,
        name='timer_overlay_state',
    ),
    path('winchallenges/', views.winchallenge_list, name='winchallenge_list'),
    path('winchallenges/new/', views.winchallenge_create, name='winchallenge_create'),
    path('winchallenges/<int:pk>/', views.winchallenge_manage, name='winchallenge_manage'),
    path('winchallenges/<int:pk>/autosave/', views.winchallenge_autosave, name='winchallenge_autosave'),
    path('winchallenges/<int:pk>/duplicate/', views.winchallenge_duplicate, name='winchallenge_duplicate'),
    path('winchallenges/<int:pk>/export/', views.winchallenge_export, name='winchallenge_export'),
    path('winchallenges/<int:pk>/delete/', views.winchallenge_delete, name='winchallenge_delete'),
    path('winchallenges/<int:pk>/games/add/', views.winchallenge_game_add, name='winchallenge_game_add'),
    path(
        'winchallenges/<int:pk>/games/<int:game_pk>/wins/',
        views.winchallenge_game_wins,
        name='winchallenge_game_wins',
    ),
    path(
        'winchallenges/<int:pk>/games/<int:game_pk>/rename/',
        views.winchallenge_game_rename,
        name='winchallenge_game_rename',
    ),
    path(
        'winchallenges/<int:pk>/games/<int:game_pk>/delete/',
        views.winchallenge_game_delete,
        name='winchallenge_game_delete',
    ),
    path(
        'overlays/winchallenge/<uuid:public_token>/',
        views.winchallenge_overlay,
        name='winchallenge_overlay',
    ),
    path(
        'overlays/winchallenge/<uuid:public_token>/state/',
        views.winchallenge_overlay_state,
        name='winchallenge_overlay_state',
    ),
]
