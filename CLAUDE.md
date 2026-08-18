# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Nexora is a Django 6 / Python 3.12 app that generates browser overlays for OBS. Users design an
overlay in an authenticated editor; OBS loads a public, UUID-tokenized URL that polls a JSON state
endpoint. Single Django app (`app/`), SQLite, no frontend build step, stdlib `urllib` for all
outbound HTTP (no `requests`).

## Commands

Activate the venv first (Windows PowerShell): `.\.venv\Scripts\Activate.ps1`

```bash
python manage.py runserver
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py check
```

Tests, lint, coverage (dev deps: `pip install -r requirements-dev.txt`):

```bash
python manage.py test
python manage.py test app.tests.ScoreOverlayEndpointTests
python manage.py test app.tests.ScoreOverlayEndpointTests.test_create_starts_with_two_zero_score_participants
ruff format . && ruff check .
coverage run manage.py test && coverage report
```

Coverage is branch coverage with `fail_under = 80`. `app/e2e_tests.py` does not match Django's
`test*.py` discovery pattern, so the Playwright suite never runs as part of `manage.py test` — run
it explicitly (it is also omitted from coverage):

```bash
python -m playwright install chromium
python manage.py test app.e2e_tests
```

Translations — both `de` and `en` must be regenerated after touching any `gettext` string or
template text (`de` is `LANGUAGE_CODE`):

```bash
python manage.py makemessages -l de && python manage.py makemessages -l en
python manage.py compilemessages
```

Hourly production job for Twitch token validation: `python manage.py validate_twitch_tokens`.

## Architecture

### Overlay types

Five parallel overlay families, each an independent model + editor + public page:
`SpotifyOverlay` (`/spotify/`), `TwitchGoalOverlay` (`/goals/`), `ScoreOverlay` (`/scores/`),
`TimerOverlay` (`/timers/`), `WinChallenge` (+ `WinChallengeGame`, `/winchallenges/`).
Each has a view module in [app/views/](app/views/), a template dir under
[app/templates/app/](app/templates/app/), and one CSS + one JS file in `app/static/`.

### Two-audience request split

- **Management routes** (`/spotify/<pk>/…`) are `@login_required` and always resolve the object
  through the owner-scoped querysets in [app/views/dashboard.py](app/views/dashboard.py)
  (`manageable_*_overlays(request)`) via a per-module `get_manageable_*` helper. Never fetch an
  overlay by `pk` alone in a management view — ownership is enforced by the queryset, not by a
  separate permission check.
- **Public routes** (`/overlays/<type>/<uuid:public_token>/`) have no auth. They are `@never_cache`,
  wrapped in `no_store()`, and must never leak tokens, scopes, or upstream API errors. Their
  `…/state/` sibling returns `conditional_state_response(request, payload, version)` from
  [app/views/common.py](app/views/common.py), which derives a SHA-256 ETag from a per-type version
  string so OBS polling gets `304`s. Rotating a link is `renew_public_obs_link()`, which regenerates
  `public_token`.

### Cross-cutting modules

- [app/views/common.py](app/views/common.py) — `no_store`, `conditional_state_response`,
  `json_export_response`, `renew_public_obs_link`, `overlay_asset_file`.
- [app/views/__init__.py](app/views/__init__.py) — explicit re-export facade. `app/urls.py` and the
  tests import `views.<name>`, and tests patch e.g. `app.views.spotify_api` / `app.views.timezone`
  through it. **A new view is not reachable until it is added to both the imports and `__all__`.**
- [app/overlay_versions.py](app/overlay_versions.py) — automatic snapshot history on every autosave,
  deduplicated by fingerprint, capped at `MAX_VERSIONS_PER_OVERLAY = 30`. Restore first records the
  current state, so it stays reversible. Contains a `_restore_<type>` branch per overlay type.
- [app/overlay_transfer.py](app/overlay_transfer.py) — JSON export/import (`nexora-overlay`
  envelope, `FORMAT_VERSION`) and `duplicate_overlay()`. Explicit per-type field tuples plus
  `<type>_export_payload` / `_import_<type>` functions; import validates envelope keys strictly.
- [app/overlay_presets.py](app/overlay_presets.py) — `OverlayPreset` (the "template gallery"): a
  named, cross-type snapshot of the 9 identically-shaped branding/style fields every overlay type
  shares (font, logo/background assets, background/border color, opacity, border width, corner
  radius). `apply_style()` clamps numeric fields to the *target* type's own validators before
  saving, since max bounds differ per type (e.g. `corner_radius` maxes out at 64/80/100 depending on
  the overlay). Applying records a version snapshot first, so it stays reversible.
- [app/encrypted_fields.py](app/encrypted_fields.py) — `EncryptedTextField` (Fernet, `fernet$`
  prefix) used for all OAuth tokens. The key comes from `NEXORA_OAUTH_TOKEN_ENCRYPTION_KEY`, falls
  back to `SPOTIFY_TOKEN_ENCRYPTION_KEY`, then to a digest of `DJANGO_SECRET_KEY`. Changing the
  effective key makes stored tokens undecryptable (raises `ImproperlyConfigured`) and forces users
  to reconnect.
- [app/models.py](app/models.py) — also holds `OverlayAsset` (user-uploaded fonts/images served by
  random token, never by media path), `OverlayBrandingMixin` (font/logo/background, inherited by all
  overlay models), and the module-level default-element builders (`default_goal_elements`,
  `goal_elements_for_layout`, `broadcast_duel_score_elements`, …) that seed the drag-and-drop canvas
  per layout preset.

### External APIs

[app/spotify_api.py](app/spotify_api.py) and [app/twitch_api.py](app/twitch_api.py) share the same
shape: one `*Connection` row per user (shared by all of that user's overlays of that type), OAuth
code exchange, encrypted token storage, and a short cache column on the connection
(`SPOTIFY_PLAYBACK_CACHE_SECONDS` / `TWITCH_METRIC_CACHE_SECONDS`) refreshed under a
`select_for_update()` + `Q(cached_at__lte=stale_before)` guard, so many concurrent OBS pollers
trigger at most one upstream call. On upstream failure they serve the last known good value.
`twitch_api.reconcile_goal()` additionally advances celebration state under a row lock.

### Frontend

No bundler. Each page loads `theme.css` + `base.css` + a page CSS file, plus plain IIFE scripts that
publish globals:

- [polling.js](app/static/js/polling.js) → `window.NexoraPolling.start({url, interval, onData})` —
  ETag conditional GETs, overlap prevention, exponential backoff to 30 s, slower cadence while
  `document.hidden`.
- [editor-state.js](app/static/js/editor-state.js) — undo/redo history, dirty tracking, debounced
  autosave POSTs, `localStorage` drafts; driven entirely by `data-editor-*` attributes on the markup.
- [overlay-branding.js](app/static/js/overlay-branding.js) — shared branding/asset controls.

Static assets are cache-busted with `?v={{ APP_VERSION }}` (from `APP_VERSION` or the `VERSION` file).

### Config

[nexora/settings.py](nexora/settings.py) parses `.env` itself (`_load_local_environment`, using
`os.environ.setdefault`, so real environment variables win) and validates every value through
`_environment_bool` / `_environment_list` / `_environment_non_negative_int`, raising
`ImproperlyConfigured` on bad input. With `DJANGO_DEBUG=false` it also rejects the placeholder secret
keys. Add new settings through these helpers and mirror them in `.env.example`.

## Conventions

- Ruff: line length 100, double quotes, `select = ["B", "E4", "E7", "E9", "F", "I"]`,
  `app/migrations` excluded. CI runs `ruff format --check`, so format before committing.
- Editor `elements` are JSON canvases. Each overlay form validates them in `clean_elements()`
  against a per-form `ALLOWED_ELEMENT_TYPES` set and `ELEMENT_ID_PATTERN`; never persist element
  JSON that has not gone through the form.
- All user-facing strings go through `gettext` / `{% translate %}`.
- Autosave endpoints return `{"ok": false, "errors": form.errors.get_json_data()}` with HTTP 400 on
  invalid input, and call `overlay_versions.record_version(...)` on success.
- Redirect targets taken from a request use `safe_next_url(request)`
  ([app/views/pages.py](app/views/pages.py)).
- Tests are grouped by behavior in [app/tests.py](app/tests.py), with Twitch split into
  [app/test_twitch_goal.py](app/test_twitch_goal.py); class names like `ScoreOverlayEndpointTests`,
  `AccessControlTests`, `PublicStateConditionalRequestTests`. New overlay behavior needs both an
  endpoint test and an access-control test (public token works unauthenticated, another user's pk
  404s).
- Migrations are sequentially numbered and hand-reviewed; some (`0011`, `0012`) are data migrations
  that centralize connections or backfill assets.
- Commit subjects are short and Title Case; part of the history is German, part English.

## Adding a new overlay type

Touch, in order: `models.py` (model + `OverlayBrandingMixin`, `state_payload`/`design_payload`,
default elements) → migration → `forms.py` (create/settings/design forms with `clean_elements`) →
`views/<type>.py` (list, create, manage, autosave, duplicate, export, delete, renew-obs-link, public
page, public state) → `views/__init__.py` facade → `urls.py` → `views/dashboard.py` (`manageable_*`
+ dashboard context) → `overlay_versions.py` (`overlay_type_for`, `_restore_<type>`) →
`overlay_transfer.py` (field tuple, export payload, `_import_<type>`, `duplicate_overlay`) →
templates (`create.html`, `_overlay.html`, `public_overlay.html`) + CSS/JS → `admin.py` → tests →
`makemessages` / `compilemessages`.
