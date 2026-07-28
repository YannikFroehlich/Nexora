import json
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from app.models import (
    OverlayAsset,
    ScoreOverlay,
    ScoreParticipant,
    SpotifyOverlay,
    TimerOverlay,
    WinChallenge,
    WinChallengeGame,
)

BASE_INPUT_CLASS = "form-control"
MAX_OVERLAY_IMPORT_SIZE = 256 * 1024


class OverlayAssetSelect(forms.Select):
    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        asset = getattr(value, "instance", None)
        if asset is not None:
            option["attrs"]["data-asset-url"] = asset.public_url
        return option


def _configure_branding_fields(form, asset_owner):
    font_family = form.fields.get("font_family")
    if font_family is not None:
        font_family.label = _("Preset font")
        font_family.required = False
        font_family.widget.attrs.update(
            {
                "class": BASE_INPUT_CLASS,
                "data-branding-font-family": "",
            }
        )

    owner_assets = (
        OverlayAsset.objects.filter(owner=asset_owner)
        if asset_owner and asset_owner.is_authenticated
        else OverlayAsset.objects.none()
    )
    field_config = {
        "font_asset": (OverlayAsset.KIND_FONT, _("Custom font")),
        "logo_asset": (OverlayAsset.KIND_IMAGE, _("Logo")),
        "background_asset": (OverlayAsset.KIND_IMAGE, _("Background image")),
    }

    for field_name, (kind, label) in field_config.items():
        field = form.fields.get(field_name)
        if field is None:
            continue
        field.queryset = owner_assets.filter(kind=kind)
        field.label = label
        field.required = False
        field.empty_label = _("None")
        widget_attrs = {
            "class": BASE_INPUT_CLASS,
            "data-branding-field": field_name,
        }
        if not field.queryset.exists():
            widget_attrs.update(
                {
                    "disabled": True,
                    "aria-disabled": "true",
                }
            )
        field.widget = OverlayAssetSelect(
            attrs=widget_attrs,
            choices=field.choices,
        )


def _selected_font_family(form):
    return (
        form.cleaned_data.get("font_family")
        or form.instance.font_family
        or form.instance.FONT_SYSTEM
    )


def _prepare_accessible_auth_fields(form):
    """Connect auth inputs to help and error text for assistive technology."""

    for field_name, field in form.fields.items():
        bound_field = form[field_name]
        described_by = []

        if field.help_text:
            described_by.append(f"{bound_field.auto_id}_helptext")

        if bound_field.errors:
            described_by.append(f"{bound_field.auto_id}_error")
            field.widget.attrs["aria-invalid"] = "true"

        if described_by:
            field.widget.attrs["aria-describedby"] = " ".join(described_by)

    if form.errors:
        for field in form.fields.values():
            field.widget.attrs.pop("autofocus", None)


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _prepare_accessible_auth_fields(self)


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
        _prepare_accessible_auth_fields(self)


class OverlayImportForm(forms.Form):
    overlay_file = forms.FileField(
        label=_("Overlay export file"),
        help_text=_("Select a JSON file previously exported from Nexora."),
        widget=forms.FileInput(
            attrs={
                "class": "dashboard-import__input",
                "accept": ".json,application/json",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        described_by = ["id_overlay_file_help"]

        if self["overlay_file"].errors:
            described_by.append("id_overlay_file_error")
            self.fields["overlay_file"].widget.attrs["aria-invalid"] = "true"

        self.fields["overlay_file"].widget.attrs["aria-describedby"] = " ".join(described_by)

    def clean_overlay_file(self):
        overlay_file = self.cleaned_data["overlay_file"]

        if overlay_file.size > MAX_OVERLAY_IMPORT_SIZE:
            raise forms.ValidationError(_("The import file is too large."))

        if not overlay_file.name.lower().endswith(".json"):
            raise forms.ValidationError(_("Select a JSON file."))

        return overlay_file


class OverlayAssetUploadForm(forms.ModelForm):
    class Meta:
        model = OverlayAsset
        fields = ("name", "kind", "file")
        labels = {
            "name": _("Asset name"),
            "kind": _("Asset type"),
            "file": _("File"),
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "placeholder": _("My logo or font"),
                    "form": "overlay-asset-upload-form",
                }
            ),
            "kind": forms.Select(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "form": "overlay-asset-upload-form",
                }
            ),
            "file": forms.FileInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "accept": ".png,.jpg,.jpeg,.webp,.woff,.woff2,.ttf,.otf",
                    "form": "overlay-asset-upload-form",
                }
            ),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def save(self, commit=True):
        asset = super().save(commit=False)
        asset.owner = self.owner
        if commit:
            asset.save()
        return asset


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
            "font_family",
            "font_asset",
            "logo_asset",
            "background_asset",
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
            "title": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": _("Road to Diamond")}
            ),
            "design_template": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "background_color": ColorInput(attrs={"class": "color-control"}),
            "background_opacity": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 100, "step": 1}
            ),
            "text_color": ColorInput(attrs={"class": "color-control"}),
            "accent_color": ColorInput(attrs={"class": "color-control"}),
            "border_color": ColorInput(attrs={"class": "color-control"}),
            "border_width": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 12, "step": 1}
            ),
            "corner_radius": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 64, "step": 1}
            ),
            "padding": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 64, "step": 1}
            ),
            "overlay_width": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 260, "max": 1200, "step": 1}
            ),
            "overlay_height": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 1000, "step": 1}
            ),
            "label_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 6, "max": 32, "step": 1}
            ),
            "title_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 10, "max": 64, "step": 1}
            ),
            "total_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 40, "step": 1}
            ),
            "game_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 48, "step": 1}
            ),
            "game_score_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 36, "step": 1}
            ),
            "pager_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 8, "max": 32, "step": 1}
            ),
            "page_interval_seconds": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 1, "max": 60, "step": 1}
            ),
            "item_spacing": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 4, "max": 28, "step": 1}
            ),
            "shadow_enabled": forms.CheckboxInput(attrs={"class": "toggle-control"}),
            "show_games_list": forms.CheckboxInput(attrs={"class": "toggle-control"}),
        }

    def __init__(self, *args, **kwargs):
        asset_owner = kwargs.pop("asset_owner", None)
        super().__init__(*args, **kwargs)
        _configure_branding_fields(self, asset_owner)
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

    def clean_font_family(self):
        return _selected_font_family(self)


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
            "font_family",
            "font_asset",
            "logo_asset",
            "background_asset",
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
                    "max": WinChallengeGame.MAX_WINS,
                    "placeholder": 0,
                }
            ),
            "target_wins": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "min": 1,
                    "max": WinChallengeGame.MAX_WINS,
                    "placeholder": 10,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wins"].min_value = 0
        self.fields["wins"].max_value = WinChallengeGame.MAX_WINS
        self.fields["wins"].widget.attrs["min"] = 0
        self.fields["wins"].widget.attrs["max"] = WinChallengeGame.MAX_WINS
        self.fields["target_wins"].min_value = 1
        self.fields["target_wins"].max_value = WinChallengeGame.MAX_WINS
        self.fields["target_wins"].widget.attrs["min"] = 1
        self.fields["target_wins"].widget.attrs["max"] = WinChallengeGame.MAX_WINS

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
            "font_family",
            "font_asset",
            "logo_asset",
            "background_asset",
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
        asset_owner = kwargs.pop("asset_owner", None)
        super().__init__(*args, **kwargs)
        _configure_branding_fields(self, asset_owner)
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

    def clean_font_family(self):
        return _selected_font_family(self)

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


class ScoreOverlayForm(forms.ModelForm):
    """Score HUD settings plus the JSON layout maintained by the visual editor."""

    ALLOWED_ELEMENT_TYPES = {
        "participant_image",
        "participant_name",
        "participant_score",
    }
    ELEMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    PARTICIPANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    TEXT_ALIGN_CHOICES = {"left", "center", "right"}
    elements = forms.CharField(widget=forms.HiddenInput(attrs={"data-elements-input": ""}))

    class Meta:
        model = ScoreOverlay
        fields = (
            "name",
            "canvas_width",
            "canvas_height",
            "background_color",
            "background_opacity",
            "border_color",
            "border_width",
            "corner_radius",
            "allow_negative_scores",
            "elements",
            "font_family",
            "font_asset",
            "logo_asset",
            "background_asset",
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
            "allow_negative_scores": _("Allow negative scores"),
        }
        help_texts = {
            "background_opacity": _("0 is transparent, 100 is fully opaque."),
            "allow_negative_scores": _("When disabled, minus buttons stop at 0."),
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": _("Score HUD")}
            ),
            "canvas_width": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 320, "max": 1920, "step": 1}
            ),
            "canvas_height": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 140, "max": 1080, "step": 1}
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
            "allow_negative_scores": forms.CheckboxInput(attrs={"class": "toggle-control"}),
        }

    def __init__(self, *args, **kwargs):
        asset_owner = kwargs.pop("asset_owner", None)
        super().__init__(*args, **kwargs)
        _configure_branding_fields(self, asset_owner)
        self.fields["name"].required = False

        limits = {
            "canvas_width": (320, 1920),
            "canvas_height": (140, 1080),
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
        return self.cleaned_data["name"].strip() or "Score HUD"

    def clean_font_family(self):
        return _selected_font_family(self)

    def clean_elements(self):
        try:
            raw_elements = json.loads(self.cleaned_data["elements"])
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise forms.ValidationError(_("The element layout is invalid.")) from error

        if not isinstance(raw_elements, list):
            raise forms.ValidationError(_("The element layout must be a list."))

        if len(raw_elements) > ScoreOverlay.MAX_PARTICIPANTS * 3:
            raise forms.ValidationError(_("A maximum of 24 elements is allowed."))

        normalized = []
        used_ids = set()

        for raw_element in raw_elements:
            if not isinstance(raw_element, dict):
                raise forms.ValidationError(_("Every overlay element must be an object."))

            element_id = str(raw_element.get("id", ""))
            element_type = str(raw_element.get("type", ""))
            participant_id = str(raw_element.get("participant_id", ""))

            if not self.ELEMENT_ID_PATTERN.fullmatch(element_id) or element_id in used_ids:
                raise forms.ValidationError(_("Every overlay element needs a unique valid ID."))

            if element_type not in self.ALLOWED_ELEMENT_TYPES:
                raise forms.ValidationError(_("An unknown score element was submitted."))

            if not self.PARTICIPANT_ID_PATTERN.fullmatch(participant_id):
                raise forms.ValidationError(_("Every score element needs a participant."))

            used_ids.add(element_id)
            normalized.append(
                {
                    "id": element_id,
                    "type": element_type,
                    "participant_id": participant_id,
                    "x": self._integer_value(raw_element, "x", 0, 1920),
                    "y": self._integer_value(raw_element, "y", 0, 1080),
                    "width": self._integer_value(raw_element, "width", 24, 1920),
                    "height": self._integer_value(raw_element, "height", 8, 1080),
                    "font_size": self._integer_value(raw_element, "font_size", 8, 160),
                    "border_radius": self._integer_value(raw_element, "border_radius", 0, 200),
                    "color": self._color_value(raw_element, "color"),
                    "background_color": self._color_value(raw_element, "background_color"),
                    "text_align": self._text_align_value(raw_element),
                }
            )

        return normalized

    @staticmethod
    def _integer_value(element, key, minimum, maximum):
        try:
            value = int(element.get(key))
        except (TypeError, ValueError) as error:
            raise forms.ValidationError(_("Element values must be whole numbers.")) from error

        if not minimum <= value <= maximum:
            raise forms.ValidationError(_("An element value is outside the allowed range."))

        return value

    @staticmethod
    def _color_value(element, key):
        value = str(element.get(key, ""))

        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise forms.ValidationError(_("Every element color must be a valid hex color."))

        return value.lower()

    def _text_align_value(self, element):
        value = str(element.get("text_align", "center"))
        return value if value in self.TEXT_ALIGN_CHOICES else "center"


class ScoreOverlayCreateForm(ScoreOverlayForm):
    player_one_name = forms.CharField(
        label=_("Player 1"),
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "placeholder": _("Player 1"),
                "autocomplete": "off",
            }
        ),
    )
    player_two_name = forms.CharField(
        label=_("Player 2"),
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT_CLASS,
                "placeholder": _("Player 2"),
                "autocomplete": "off",
            }
        ),
    )

    class Meta(ScoreOverlayForm.Meta):
        fields = (
            "name",
            "player_one_name",
            "player_two_name",
            "canvas_width",
            "canvas_height",
            "background_color",
            "background_opacity",
            "border_color",
            "border_width",
            "corner_radius",
            "allow_negative_scores",
            "elements",
            "font_family",
            "font_asset",
            "logo_asset",
            "background_asset",
        )

    def clean_player_one_name(self):
        return self.cleaned_data["player_one_name"].strip()

    def clean_player_two_name(self):
        return self.cleaned_data["player_two_name"].strip()


class ScoreParticipantForm(forms.ModelForm):
    class Meta:
        model = ScoreParticipant
        fields = ("name", "accent_color", "image_asset")
        labels = {
            "name": _("Name"),
            "accent_color": _("Color"),
            "image_asset": _("Image"),
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "placeholder": _("Player or team"),
                    "autocomplete": "off",
                }
            ),
            "accent_color": ColorInput(attrs={"class": "color-control"}),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        assets = (
            OverlayAsset.objects.filter(owner=owner, kind=OverlayAsset.KIND_IMAGE)
            if owner and owner.is_authenticated
            else OverlayAsset.objects.none()
        )
        self.fields["image_asset"].queryset = assets
        self.fields["image_asset"].required = False
        self.fields["image_asset"].empty_label = _("No image")
        self.fields["image_asset"].widget = OverlayAssetSelect(
            attrs={"class": BASE_INPUT_CLASS},
            choices=self.fields["image_asset"].choices,
        )

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class TimerOverlayForm(forms.ModelForm):
    """Settings and design form for countdown and stopwatch overlays."""

    duration_hours = forms.IntegerField(
        label=_("Hours"),
        min_value=0,
        max_value=99,
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 99, "step": 1}),
    )
    duration_minutes = forms.IntegerField(
        label=_("Minutes"),
        min_value=0,
        max_value=59,
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 59, "step": 1}),
    )
    duration_seconds_part = forms.IntegerField(
        label=_("Seconds"),
        min_value=0,
        max_value=59,
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 59, "step": 1}),
    )

    class Meta:
        model = TimerOverlay
        fields = (
            "name",
            "label",
            "mode",
            "duration_hours",
            "duration_minutes",
            "duration_seconds_part",
            "design_template",
            "background_color",
            "background_opacity",
            "text_color",
            "accent_color",
            "border_color",
            "border_width",
            "corner_radius",
            "overlay_width",
            "overlay_height",
            "label_text_size",
            "timer_text_size",
            "show_progress",
            "shadow_enabled",
            "font_family",
            "font_asset",
            "logo_asset",
            "background_asset",
        )
        labels = {
            "name": _("Overlay name"),
            "label": _("Label"),
            "mode": _("Timer type"),
            "design_template": _("Design template"),
            "background_color": _("Background color"),
            "background_opacity": _("Background opacity"),
            "text_color": _("Text color"),
            "accent_color": _("Accent color"),
            "border_color": _("Border color"),
            "border_width": _("Border width"),
            "corner_radius": _("Corner radius"),
            "overlay_width": _("Width"),
            "overlay_height": _("Height"),
            "label_text_size": _("Label text size"),
            "timer_text_size": _("Timer text size"),
            "show_progress": _("Show progress bar"),
            "shadow_enabled": _("Show shadow"),
        }
        help_texts = {
            "background_opacity": _("0 is transparent, 100 is fully opaque."),
            "label": _("Optional text displayed above the time."),
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": _("Stream Timer")}
            ),
            "label": forms.TextInput(
                attrs={"class": BASE_INPUT_CLASS, "placeholder": _("Starting soon")}
            ),
            "mode": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "design_template": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "background_color": ColorInput(attrs={"class": "color-control"}),
            "background_opacity": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 100, "step": 1}
            ),
            "text_color": ColorInput(attrs={"class": "color-control"}),
            "accent_color": ColorInput(attrs={"class": "color-control"}),
            "border_color": ColorInput(attrs={"class": "color-control"}),
            "border_width": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 12, "step": 1}
            ),
            "corner_radius": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 0, "max": 64, "step": 1}
            ),
            "overlay_width": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 260, "max": 1200, "step": 1}
            ),
            "overlay_height": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 140, "max": 600, "step": 1}
            ),
            "label_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 10, "max": 40, "step": 1}
            ),
            "timer_text_size": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": 36, "max": 160, "step": 1}
            ),
            "show_progress": forms.CheckboxInput(attrs={"class": "toggle-control"}),
            "shadow_enabled": forms.CheckboxInput(attrs={"class": "toggle-control"}),
        }

    def __init__(self, *args, **kwargs):
        asset_owner = kwargs.pop("asset_owner", None)
        super().__init__(*args, **kwargs)
        _configure_branding_fields(self, asset_owner)
        self.fields["name"].required = False
        self.fields["label"].required = False

        if not self.is_bound:
            hours, remainder = divmod(self.instance.duration_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.initial.update(
                {
                    "duration_hours": hours,
                    "duration_minutes": minutes,
                    "duration_seconds_part": seconds,
                }
            )
            if self.instance.pk is None:
                self.initial["name"] = _("Stream Timer")
                self.initial["label"] = _("Starting soon")

    def clean_name(self):
        return self.cleaned_data["name"].strip() or "Stream Timer"

    def clean_font_family(self):
        return _selected_font_family(self)

    def clean_label(self):
        return self.cleaned_data["label"].strip()

    def clean(self):
        cleaned_data = super().clean()
        duration_parts = (
            cleaned_data.get("duration_hours"),
            cleaned_data.get("duration_minutes"),
            cleaned_data.get("duration_seconds_part"),
        )

        if any(value is None for value in duration_parts):
            return cleaned_data

        hours, minutes, seconds = duration_parts
        duration_seconds = (hours * 3600) + (minutes * 60) + seconds

        if duration_seconds < 1:
            self.add_error(
                "duration_seconds_part",
                _("The timer duration must be at least one second."),
            )
        elif duration_seconds > TimerOverlay.MAX_SECONDS:
            self.add_error(
                "duration_hours",
                _("The timer duration must be shorter than 100 hours."),
            )
        else:
            cleaned_data["duration_total_seconds"] = duration_seconds

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.duration_seconds = self.cleaned_data["duration_total_seconds"]
        limit = (
            instance.duration_seconds
            if instance.mode == TimerOverlay.MODE_COUNTDOWN
            else TimerOverlay.MAX_SECONDS
        )
        elapsed = instance.elapsed_seconds()

        if elapsed >= limit:
            instance.accumulated_seconds = limit
            instance.is_running = False
            instance.started_at = None
        elif instance.accumulated_seconds > limit:
            instance.accumulated_seconds = limit

        if commit:
            instance.save()
            self._save_m2m()

        return instance
