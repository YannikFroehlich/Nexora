from django.urls import path

from app import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('spotify/new/', views.spotify_create, name='spotify_create'),
    path('winchallenges/', views.winchallenge_list, name='winchallenge_list'),
    path('winchallenges/new/', views.winchallenge_create, name='winchallenge_create'),
    path('winchallenges/<int:pk>/', views.winchallenge_manage, name='winchallenge_manage'),
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
