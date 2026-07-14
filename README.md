<p align="center">
  <img src="app/static/imgs/icons/nexora_logo.png" alt="Nexora logo" width="420">
</p>

<h1 align="center">Nexora</h1>

<p align="center">
  <strong>Build it. Style it. Stream it.</strong><br>
  A Django platform for creating, customizing, and managing browser overlays for OBS.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.0-7c3aed?style=for-the-badge">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.0.7-092E20?style=for-the-badge&logo=django&logoColor=white">
  <img alt="OBS" src="https://img.shields.io/badge/OBS-Browser_Source-302E31?style=for-the-badge&logo=obsstudio&logoColor=white">
</p>

---

## ✨ What is Nexora?

**Nexora** turns configurable web components into stream-ready overlays. Design an overlay in the browser, copy its generated URL, and add it to OBS as a **browser source**.

Content and design changes are managed directly in Nexora. The browser-source URL in your OBS scene remains unchanged.

> **One platform. One link. Your stream design.**

## 🚀 Features

### 🎵 Spotify overlay

Create a freely positioned now-playing overlay for your Spotify playback.

- Drag-and-drop visual editor
- Configurable canvas dimensions
- Custom colors, opacity, borders, and corner radii
- Freely combinable elements:
  - Artwork
  - Track title
  - Artist
  - Album
  - Progress bar
  - Elapsed time
  - Total duration
  - Playback status
- Spotify connection through OAuth
- Public OBS browser-source URL
- Live playback updates

### 🏆 Win Challenge overlay

Manage challenges for one or more games and display their progress live on stream.

- Custom challenge titles
- Up to **20 games** per challenge
- Separate current wins and target wins for each game
- Direct win increment and decrement controls
- Rename and delete games
- Automatic total-win calculation
- Per-game progress indicators
- Automatic pagination for larger game lists
- Three design presets:
  - Minimal
  - Glass
  - Neon
- Configurable colors, spacing, font sizes, borders, and shadows
- Flexible overlay width and optional fixed height
- Public browser-source URL with live updates

### 🌍 Platform

- German and English user interface
- Responsive glass-style design
- Light and dark themes
- User accounts with private overlay libraries
- Owner-based access control for all management pages and actions
- Public OBS overlay URLs protected by hard-to-guess UUID tokens
- Automatic adoption of existing ownerless overlays by the first registered account
- SQLite database for local development
- Version display based on the `VERSION` file

## 🧭 How it works

```text
Create an account
      ↓
Create an overlay
      ↓
Customize its design and content
      ↓
Copy the browser-source URL
      ↓
Add the URL to OBS
      ↓
Update values in Nexora whenever needed
```

Management pages require an authenticated account. Public UUID-based overlay URLs remain accessible to OBS without a login.

## 🛠️ Local installation

### Requirements

- Python 3.12 or newer
- `pip`
- Git when cloning the repository
- A Spotify Developer app when using the Spotify overlay

### 1. Prepare the project

```bash
git clone <YOUR-REPOSITORY-URL>
cd Nexora
```

You can also download and extract the project as a ZIP archive.

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example environment file:

**Windows PowerShell**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS**

```bash
cp .env.example .env
```

Update the values in `.env`:

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=true

SPOTIFY_CLIENT_ID=your-spotify-client-id
SPOTIFY_CLIENT_SECRET=your-spotify-client-secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/spotify/callback/
```

> `.env` contains sensitive credentials and must never be committed to Git.

### 5. Prepare the database

```bash
python manage.py migrate
```

You can optionally create an administrator account for the Django admin:

```bash
python manage.py createsuperuser
```

### 6. Start the development server

```bash
python manage.py runserver
```

Nexora is now available at:

```text
http://127.0.0.1:8000/
```

Create a regular Nexora account at:

```text
http://127.0.0.1:8000/accounts/signup/
```

The first registered account automatically becomes the owner of existing overlays that do not yet have an owner.

## 🎧 Spotify setup

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Open the Spotify app settings.
3. Add this exact redirect URI:

```text
http://127.0.0.1:8000/spotify/callback/
```

4. Add the Spotify `Client ID` and `Client Secret` to `.env`.
5. Restart the Django server.
6. Open a Spotify overlay in Nexora and select **Connect with Spotify**.

For a production domain, `SPOTIFY_REDIRECT_URI` must use the same public HTTPS URL in both `.env` and the Spotify Developer Dashboard.

## 🎥 Add an overlay to OBS

1. Create or open an overlay in Nexora.
2. Copy its browser-source URL.
3. Open your OBS scene.
4. Select `+` in the **Sources** panel.
5. Choose **Browser**.
6. Paste the Nexora URL into the **URL** field.
7. Apply the recommended width and height shown in Nexora.
8. Optionally enable **Refresh browser when scene becomes active**.

Future changes made in Nexora are picked up by the overlay without recreating the source in OBS.

## 📁 Project structure

```text
Nexora/
├── app/
│   ├── migrations/          # Database migrations
│   ├── static/              # CSS, JavaScript, images, and icons
│   ├── templates/           # Pages, editors, authentication, and overlays
│   ├── forms.py             # Forms and input validation
│   ├── models.py            # Spotify and Win Challenge models
│   ├── spotify_api.py       # Spotify OAuth and playback API client
│   ├── urls.py              # Application routes
│   └── views.py             # Authentication, management, and overlay views
├── locale/                  # German and English translations
├── nexora/                  # Django project configuration
├── .env.example             # Environment variable template
├── manage.py
├── requirements.txt
└── VERSION
```

## 🔗 Important routes

| Area | Route | Access |
|---|---|---|
| Home | `/` | Public |
| About | `/about/` | Public |
| Sign in | `/accounts/login/` | Public |
| Create account | `/accounts/signup/` | Public |
| Spotify overlays | `/spotify/` | Authenticated |
| New Spotify overlay | `/spotify/new/` | Authenticated |
| Win Challenges | `/winchallenges/` | Authenticated |
| New Win Challenge | `/winchallenges/new/` | Authenticated |
| Django admin | `/admin/` | Staff |

Public OBS routes are generated individually for each overlay and use UUID tokens.

## 🌐 Update translations

Extract translatable strings after changing Python or template text:

```bash
python manage.py makemessages -l de
python manage.py makemessages -l en
```

Edit the generated `django.po` files and compile them:

```bash
python manage.py compilemessages
```

## ✅ Project checks

Run the Django system check:

```bash
python manage.py check
```

Run the automated test suite:

```bash
python manage.py test
```

Check for missing model migrations:

```bash
python manage.py makemigrations --check --dry-run
```

## 🔐 Production notes

The current configuration primarily targets local development. Before deploying Nexora publicly, at minimum:

- Set `DJANGO_DEBUG=false`
- Use a long, unique `DJANGO_SECRET_KEY`
- Configure `ALLOWED_HOSTS`
- Serve the application exclusively over HTTPS
- Enable secure session and CSRF cookies
- Configure HSTS and HTTPS redirects carefully
- Use a production-ready database and backup strategy
- Configure `STATIC_ROOT` and serve static files through an appropriate web server
- Keep Spotify credentials outside the repository
- Encrypt stored Spotify access and refresh tokens
- Protect open registration with invitations, email verification, or rate limiting when required

## 🗺️ Possible next steps

- Additional overlay types such as counters, timers, goals, and social alerts
- Account recovery and profile management
- Template gallery and reusable personal presets
- Overlay duplication and import/export
- Regeneratable public OBS tokens
- WebSocket- or Server-Sent Events-based live updates
- Docker setup for development and deployment
- CI checks and broader browser-level test coverage

## 🤝 Contributing

Ideas, bug reports, and improvements are welcome.

1. Fork the repository.
2. Create a focused feature branch.
3. Implement and test your changes.
4. Create a concise, meaningful commit.
5. Open a pull request with a description and relevant screenshots.

## 📄 License

This repository does not currently include a license file. Add an appropriate `LICENSE` before publicly distributing the project, then update this section accordingly.

---

<p align="center">
  <strong>Nexora</strong><br>
  Create. Connect. Go live. ✦
</p>
