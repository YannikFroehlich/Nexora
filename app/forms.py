import json
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from app.models import SpotifyOverlay, WinChallenge, WinChallengeGame


BASE_INPUT_CLASS = "form-control"


class LoginForm(AuthenticationForm):
    """Styled login form used by the public authentication page."""

    username = forms.CharField(
        label=_("Username"),
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "autocomplete": "current-password",
            }
        ),
    )


class SignUpForm(UserCreationForm):
    """Create a standard Django user for a private overlay library."""

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": BASE_INPUT_CLASS,
                "autocomplete": "username",
                "autofocus": True,
            }
        )
        self.fields["password1"].widget.attrs.update(
            {
                "class": BASE_INPUT_CLASS,
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "class": BASE_INPUT_CLASS,
                "autocomplete": "new-password",
            }
        )


class ColorInput(forms.TextInput):
    input_type = "color"


class WinChallengeBaseForm(forms.ModelForm):
    """Shared field setup for create and edit flows."""

    class Meta:
        model = WinChallenge
        fields = (
            "title",
            "design_template",
            "background_color",
            "background_opacity",
            "text_color",
            "accent_color",
            "border_color",
            "border_width",
            "corner_radius",
            "padding",
            "overlay_width",
            "overlay_height",
            "label_text_size",
            "title_text_size",
            "total_text_size",
            "game_text_size",
            "game_score_text_size",
            "pager_text_size",
            "page_interval_seconds",
            "item_spacing",
            "shadow_enabled",
            "show_games_list",
        )
        labels = {
            "title": _("Overlay title"),
            "design_template": _("Design template"),
            "background_color": _("Background color"),
            "background_opacity": _("Background opacity"),
            "text_color": _("Text color"),
            "accent_color": _("Accent color"),
            "border_color": _("Border color"),
            "border_width": _("Border width"),
            "corner_radius": _("Corner radius"),
            "padding": _("Padding"),
            "overlay_width": _("Width"),
            "overlay_height": _("Height"),
            "label_text_size": _("Label text size"),
            "title_text_size": _("Title text size"),
            "total_text_size": _("Total wins text size"),
            "game_text_size": _("Game name text size"),
            "game_score_text_size": _("Game score text size"),
            "pager_text_size": _("Page indicator text size"),
            "page_interval_seconds": _("Page interval"),
            "item_spacing": _("Element spacing"),
            "shadow_enabled": _("Show shadow"),
            "show_games_list": _("Show games list"),
        }
        help_texts = {
            "background_opacity": _("0 is transparent, 100 is fully opaque."),
            "overlay_height": _("0 keeps automatic height."),
            "page_interval_seconds": _("Seconds before switching to the next page."),
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": _("Road to Diamond")}),
            "design_template": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "background_color": ColorInput(attrs={"class": "color-control"}),
            "background_opacity": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 100, "step": 1}
            ),
            "text_color": ColorInput(attrs={"class": "color-control"}),
            "accent_color": ColorInput(attrs={"class": "color-control"}),
            "border_color": ColorInput(attrs={"class": "color-control"}),
            "border_width": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 12, "step": 1}),
            "corner_radius": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 64, "step": 1}),
            "padding": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 64, "step": 1}),
            "overlay_width": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 260, "max": 1200, "step": 1}),
            "overlay_height": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 1000, "step": 1}),
            "label_text_size": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 6, "max": 32, "step": 1}),
            "title_text_size": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 10, "max": 64, "step": 1}),
            "total_text_size": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 40, "step": 1}),
            "game_text_size": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 48, "step": 1}),
            "game_score_text_size": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 36, "step": 1}),
            "pager_text_size": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 32, "step": 1}),
            "page_interval_seconds": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 1, "max": 60, "step": 1}),
            "item_spacing": forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 4, "max": 28, "step": 1}),
            "shadow_enabled": forms.CheckboxInput(attrs={"class": "toggle-control"}),
            "show_games_list": forms.CheckboxInput(attrs={"class": "toggle-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sync_numeric_widget_limits()

    def _sync_numeric_widget_limits(self):
        limits = {
            "background_opacity": (0, 100),
            "border_width": (0, 12),
            "corner_radius": (0, 64),
            "padding": (8, 64),
            "overlay_width": (260, 1200),
            "overlay_height": (0, 1000),
            "label_text_size": (6, 32),
            "title_text_size": (10, 64),
            "total_text_size": (8, 40),
            "game_text_size": (8, 48),
            "game_score_text_size": (8, 36),
            "pager_text_size": (8, 32),
            "page_interval_seconds": (1, 60),
            "item_spacing": (4, 28),
        }

        for field_name, (minimum, maximum) in limits.items():
            field = self.fields.get(field_name)

            if field is None:
                continue

            field.min_value = minimum
            field.max_value = maximum
            field.widget.attrs["min"] = minimum
            field.widget.attrs["max"] = maximum

    def clean_title(self):
        return self.cleaned_data["title"].strip()


class WinChallengeCreateForm(WinChallengeBaseForm):
    """Form used when creating a new overlay."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False
        self.fields["title"].widget.attrs["placeholder"] = _("Winchallenge")


class WinChallengeSettingsForm(forms.ModelForm):
    class Meta:
        model = WinChallenge
        fields = ("title",)
        labels = {
            "title": _("Overlay title"),
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": BASE_INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = True

    def clean_title(self):
        return self.cleaned_data["title"].strip()


class WinChallengeDesignForm(WinChallengeBaseForm):
    class Meta(WinChallengeBaseForm.Meta):
        fields = (
            "design_template",
            "background_color",
            "background_opacity",
            "text_color",
            "accent_color",
            "border_color",
            "border_width",
            "corner_radius",
            "padding",
            "overlay_width",
            "overlay_height",
            "label_text_size",
            "title_text_size",
            "total_text_size",
            "game_text_size",
            "game_score_text_size",
            "pager_text_size",
            "page_interval_seconds",
            "item_spacing",
            "shadow_enabled",
            "show_games_list",
        )


class WinChallengeGameForm(forms.ModelForm):
    class Meta:
        model = WinChallengeGame
        fields = ("name", "wins", "target_wins")
        labels = {
            "name": _("Game name"),
            "wins": _("Wins"),
            "target_wins": _("Target wins"),
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "placeholder": _("Rocket League"),
                    "autocomplete": "off",
                }
            ),
            "wins": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "min": 0,
                    "max": 99999,
                    "placeholder": 0,
                }
            ),
            "target_wins": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "min": 1,
                    "max": 99999,
                    "placeholder": 10,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wins"].min_value = 0
        self.fields["wins"].max_value = 99999
        self.fields["wins"].widget.attrs["min"] = 0
        self.fields["wins"].widget.attrs["max"] = 99999
        self.fields["target_wins"].min_value = 1
        self.fields["target_wins"].max_value = 99999
        self.fields["target_wins"].widget.attrs["min"] = 1
        self.fields["target_wins"].widget.attrs["max"] = 99999

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class SpotifyOverlayForm(forms.ModelForm):
    """Overlay settings plus the JSON layout maintained by the visual editor."""

    ALLOWED_ELEMENT_TYPES = {
        "title",
        "artist",
        "album",
        "artwork",
        "progress",
        "elapsed",
        "duration",
        "status",
    }
    ELEMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    elements = forms.CharField(widget=forms.HiddenInput(attrs={"data-elements-input": ""}))

    class Meta:
        model = SpotifyOverlay
        fields = (
            "name",
            "canvas_width",
            "canvas_height",
            "background_color",
            "background_opacity",
            "border_color",
            "border_width",
            "corner_radius",
            "elements",
        )
        labels = {
            "name": _("Overlay name"),
            "canvas_width": _("Overlay width"),
            "canvas_height": _("Overlay height"),
            "background_color": _("Background color"),
            "background_opacity": _("Background opacity"),
            "border_color": _("Border color"),
            "border_width": _("Border width"),
            "corner_radius": _("Corner radius"),
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": _("Spotify-Overlay")}
            ),
            "canvas_width": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 240, "max": 1920, "step": 1}
            ),
            "canvas_height": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 120, "max": 1080, "step": 1}
            ),
            "background_color": ColorInput(attrs={"class": "color-control"}),
            "background_opacity": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 100, "step": 1}
            ),
            "border_color": ColorInput(attrs={"class": "color-control"}),
            "border_width": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 24, "step": 1}
            ),
            "corner_radius": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 80, "step": 1}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = False

        limits = {
            "canvas_width": (240, 1920),
            "canvas_height": (120, 1080),
            "background_opacity": (0, 100),
            "border_width": (0, 24),
            "corner_radius": (0, 80),
        }
        for field_name, (minimum, maximum) in limits.items():
            self.fields[field_name].min_value = minimum
            self.fields[field_name].max_value = maximum
            self.fields[field_name].widget.attrs["min"] = minimum
            self.fields[field_name].widget.attrs["max"] = maximum

        if not self.is_bound:
            self.initial["elements"] = json.dumps(
                self.instance.elements,
                ensure_ascii=False,
                separators=(",", ":"),
            )

    def clean_name(self):
        return self.cleaned_data["name"].strip() or "Spotify-Overlay"

    def clean_elements(self):
        try:
            raw_elements = json.loads(self.cleaned_data["elements"])
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise forms.ValidationError(_("The element layout is invalid.")) from error

        if not isinstance(raw_elements, list):
            raise forms.ValidationError(_("The element layout must be a list."))

        if len(raw_elements) > 30:
            raise forms.ValidationError(_("A maximum of 30 elements is allowed."))

        normalized = []
        used_ids = set()

        for raw_element in raw_elements:
            if not isinstance(raw_element, dict):
                raise forms.ValidationError(_("Every overlay element must be an object."))

            element_id = str(raw_element.get("id", ""))
            element_type = str(raw_element.get("type", ""))

            if not self.ELEMENT_ID_PATTERN.fullmatch(element_id) or element_id in used_ids:
                raise forms.ValidationError(_("Every overlay element needs a unique valid ID."))

            if element_type not in self.ALLOWED_ELEMENT_TYPES:
                raise forms.ValidationError(_("An unknown Spotify element was submitted."))

            used_ids.add(element_id)
            element = {
                "id": element_id,
                "type": element_type,
                "x": self._integer_value(raw_element, "x", 0, 1920),
                "y": self._integer_value(raw_element, "y", 0, 1080),
                "width": self._integer_value(raw_element, "width", 24, 1920),
                "height": self._integer_value(raw_element, "height", 8, 1080),
                "font_size": self._integer_value(raw_element, "font_size", 8, 120),
                "border_radius": self._integer_value(raw_element, "border_radius", 0, 200),
                "color": self._color_value(raw_element, "color"),
                "background_color": self._color_value(raw_element, "background_color"),
            }
            normalized.append(element)

        return normalized

    @staticmethod
    def _integer_value(element, key, minimum, maximum):
        try:
            value = int(element.get(key))
        except (TypeError, ValueError) as error:
            raise forms.ValidationError(_("Element values must be whole numbers.")) from error

        if not minimum <= value <= maximum:
            raise forms.ValidationError(
                _("An element value is outside the allowed range."),
            )

        return value

    @staticmethod
    def _color_value(element, key):
        value = str(element.get(key, ""))

        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise forms.ValidationError(_("Every element color must be a valid hex color."))

        return value.lower()
