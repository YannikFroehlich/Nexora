from django import forms
from django.utils.translation import gettext_lazy as _

from app.models import WinChallenge, WinChallengeGame


BASE_INPUT_CLASS = "form-control"


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
        self.fields["title"].required = True


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
