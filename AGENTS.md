# Repository Guidelines

## Project Structure & Module Organization

This is a small Django project. `manage.py` is the main command entry point. The `nexora/` package contains project configuration, including `settings.py`, root URL routing, and WSGI/ASGI setup. The `app/` package contains the primary application: views, app URLs, models, admin registration, migrations, and tests. Templates live under `app/templates/app/`, static CSS and JavaScript under `app/static/css/` and `app/static/js/`, and image assets under `app/static/imgs/`.

## Build, Test, and Development Commands

Use the project virtual environment before running Django commands:

```powershell
.\.venv\Scripts\Activate.ps1
```

Key commands:

- `python manage.py runserver` starts the local Django development server.
- `python manage.py test` runs the Django test suite.
- `python manage.py makemigrations` creates migrations after model changes.
- `python manage.py migrate` applies pending database migrations.
- `python manage.py collectstatic` gathers static files for deployment-style checks.

No dependency manifest is currently present; if recreating the environment, install Django in the virtual environment and add a requirements file when dependencies become shared.

## Coding Style & Naming Conventions

Follow standard Python and Django conventions: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and lowercase app/module names. Keep Django view names descriptive and align URL names with their page purpose, such as `home` or `about`. Template filenames should stay lowercase and live in `app/templates/app/`. Keep static files grouped by type and use page-specific names like `home.css` or `about.js` when behavior or styling is scoped to one page.

## Testing Guidelines

Use Django's built-in test framework in `app/tests.py` or split larger suites into `app/tests/`. Name test classes after the behavior under test, for example `HomeViewTests`, and name methods with `test_...`. Add tests for new views, URL routes, model behavior, and regressions. Run `python manage.py test` before submitting changes.

## Commit & Pull Request Guidelines

Recent commits use short, Title Case summaries such as `Base Site Created` and `Add .gitignore`. Keep commits concise and focused; prefer clear action-oriented subjects. Pull requests should include a brief description, testing performed, linked issue when applicable, and screenshots for template, CSS, or image changes.

## Security & Configuration Tips

Do not commit local secrets, `.env` files, virtual environments, logs, or generated static output. Treat `db.sqlite3` as local development data even if it exists in the workspace. Move production secrets out of `nexora/settings.py` before deployment.
