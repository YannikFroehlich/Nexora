import django.core.validators
from django.db import migrations, models


LAYOUT_BROADCAST_DUEL = "broadcast_duel"
LAYOUT_BROADCAST_LIST = "broadcast_list"
LAYOUT_CUSTOM = "custom"
DEFAULT_ACCENTS = (
    "#38bdf8",
    "#fb7185",
    "#22c55e",
    "#f59e0b",
    "#8b5cf6",
    "#06b6d4",
    "#f97316",
    "#a3e635",
)
LEGACY_CANVAS_DEFAULTS = {
    "canvas_width": 960,
    "canvas_height": 240,
    "background_color": "#0f172a",
    "background_opacity": 72,
    "border_color": "#38bdf8",
    "border_width": 1,
    "corner_radius": 28,
}
DUEL_CANVAS = (960, 200)
LIST_CANVAS_WIDTH = 960
LIST_ROW_HEIGHT = 72
LIST_VERTICAL_PADDING = 16


def _participant_id(participant, index):
    return str(getattr(participant, "public_id", f"slot-{index + 1}"))


def _participant_accent(participant, index):
    return getattr(participant, "accent_color", "") or DEFAULT_ACCENTS[index % len(DEFAULT_ACCENTS)]


def _element(element_id, element_type, participant, **values):
    return {
        "id": element_id,
        "type": element_type,
        "participant_id": participant["id"],
        **values,
    }


def _participants(participants):
    return [
        {"id": _participant_id(participant, index), "accent_color": _participant_accent(participant, index)}
        for index, participant in enumerate(participants[:8])
    ]


def _new_duel_elements(participants):
    data = _participants(participants)
    elements = []
    slots = (
        {"prefix": "participant-1", "image_x": 32, "name_x": 152, "score_x": 366, "align": "left"},
        {"prefix": "participant-2", "image_x": 820, "name_x": 608, "score_x": 490, "align": "right"},
    )
    for participant, slot in zip(data[:2], slots):
        elements.extend(
            [
                _element(
                    f"{slot['prefix']}-image",
                    "participant_image",
                    participant,
                    x=slot["image_x"],
                    y=40,
                    width=108,
                    height=108,
                    font_size=34,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=26,
                    text_align="center",
                ),
                _element(
                    f"{slot['prefix']}-name",
                    "participant_name",
                    participant,
                    x=slot["name_x"],
                    y=46,
                    width=200,
                    height=38,
                    font_size=26,
                    color="#ffffff",
                    background_color="#0b1020",
                    border_radius=14,
                    text_align=slot["align"],
                ),
                _element(
                    f"{slot['prefix']}-score",
                    "participant_score",
                    participant,
                    x=slot["score_x"],
                    y=58,
                    width=104,
                    height=84,
                    font_size=58,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=18,
                    text_align="center",
                ),
            ]
        )
    return elements


def _new_list_elements(participants):
    elements = []
    for index, participant in enumerate(_participants(participants)):
        row_y = LIST_VERTICAL_PADDING + (index * LIST_ROW_HEIGHT)
        prefix = f"participant-{index + 1}"
        elements.extend(
            [
                _element(
                    f"{prefix}-image",
                    "participant_image",
                    participant,
                    x=32,
                    y=row_y + 8,
                    width=56,
                    height=56,
                    font_size=22,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=16,
                    text_align="center",
                ),
                _element(
                    f"{prefix}-name",
                    "participant_name",
                    participant,
                    x=104,
                    y=row_y + 13,
                    width=680,
                    height=46,
                    font_size=28,
                    color="#ffffff",
                    background_color="#0b1020",
                    border_radius=14,
                    text_align="left",
                ),
                _element(
                    f"{prefix}-score",
                    "participant_score",
                    participant,
                    x=808,
                    y=row_y + 8,
                    width=120,
                    height=56,
                    font_size=42,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=16,
                    text_align="center",
                ),
            ]
        )
    return elements


def _legacy_duel_elements(participants):
    data = _participants(participants)
    elements = []
    positions = (
        {"image_x": 34, "name_x": 142, "score_x": 302, "align": "left", "accent": "#38bdf8"},
        {"image_x": 806, "name_x": 560, "score_x": 458, "align": "right", "accent": "#fb7185"},
    )
    for index, participant in enumerate(data[:2]):
        position = positions[index]
        prefix = f"participant-{index + 1}"
        elements.extend(
            [
                _element(
                    f"{prefix}-image",
                    "participant_image",
                    participant,
                    x=position["image_x"],
                    y=50,
                    width=120,
                    height=120,
                    font_size=38,
                    color="#ffffff",
                    background_color=position["accent"],
                    border_radius=24,
                    text_align="center",
                ),
                _element(
                    f"{prefix}-name",
                    "participant_name",
                    participant,
                    x=position["name_x"],
                    y=62,
                    width=240,
                    height=40,
                    font_size=28,
                    color="#ffffff",
                    background_color="#111827",
                    border_radius=10,
                    text_align=position["align"],
                ),
                _element(
                    f"{prefix}-score",
                    "participant_score",
                    participant,
                    x=position["score_x"],
                    y=103,
                    width=140,
                    height=78,
                    font_size=62,
                    color="#ffffff",
                    background_color=position["accent"],
                    border_radius=18,
                    text_align="center",
                ),
            ]
        )
    return elements


def _legacy_list_elements(participants, canvas_width, canvas_height):
    elements = []
    row_height = max(int((canvas_height - 34) / max(len(participants), 1)), 54)
    for index, participant in enumerate(_participants(participants)):
        y = 18 + (index * row_height)
        prefix = f"participant-{participant['id']}"
        item_size = min(row_height - 8, 70)
        item_height = min(row_height - 16, 42)
        elements.extend(
            [
                _element(
                    f"{prefix}-image",
                    "participant_image",
                    participant,
                    x=24,
                    y=y,
                    width=item_size,
                    height=item_size,
                    font_size=22,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=14,
                    text_align="center",
                ),
                _element(
                    f"{prefix}-name",
                    "participant_name",
                    participant,
                    x=100,
                    y=y + 8,
                    width=max(canvas_width - 280, 180),
                    height=item_height,
                    font_size=24,
                    color="#ffffff",
                    background_color="#111827",
                    border_radius=9,
                    text_align="left",
                ),
                _element(
                    f"{prefix}-score",
                    "participant_score",
                    participant,
                    x=max(canvas_width - 150, 170),
                    y=y,
                    width=120,
                    height=item_size,
                    font_size=42,
                    color="#ffffff",
                    background_color=participant["accent_color"],
                    border_radius=14,
                    text_align="center",
                ),
            ]
        )
    return elements


def _has_legacy_canvas_defaults(overlay):
    return all(getattr(overlay, field) == value for field, value in LEGACY_CANVAS_DEFAULTS.items())


def upgrade_score_layouts(apps, schema_editor):
    ScoreOverlay = apps.get_model("app", "ScoreOverlay")
    ScoreParticipant = apps.get_model("app", "ScoreParticipant")

    for overlay in ScoreOverlay.objects.all().iterator():
        participants = list(
            ScoreParticipant.objects.filter(overlay=overlay).order_by("sort_order", "created_at", "pk")
        )
        update_fields = ["layout_mode"]
        if len(participants) == 2 and overlay.elements == _legacy_duel_elements(participants):
            overlay.layout_mode = LAYOUT_BROADCAST_DUEL
            overlay.elements = _new_duel_elements(participants)
            update_fields.append("elements")
            if _has_legacy_canvas_defaults(overlay):
                overlay.canvas_width, overlay.canvas_height = DUEL_CANVAS
                overlay.background_opacity = 0
                overlay.border_width = 0
                overlay.corner_radius = 0
                update_fields.extend(
                    [
                        "canvas_width",
                        "canvas_height",
                        "background_opacity",
                        "border_width",
                        "corner_radius",
                    ]
                )
        elif len(participants) >= 3 and overlay.elements == _legacy_list_elements(
            participants,
            overlay.canvas_width,
            overlay.canvas_height,
        ):
            overlay.layout_mode = LAYOUT_BROADCAST_LIST
            overlay.elements = _new_list_elements(participants)
            update_fields.append("elements")
            if _has_legacy_canvas_defaults(overlay):
                overlay.canvas_width = LIST_CANVAS_WIDTH
                overlay.canvas_height = (LIST_VERTICAL_PADDING * 2) + (len(participants) * LIST_ROW_HEIGHT)
                overlay.background_opacity = 0
                overlay.border_width = 0
                overlay.corner_radius = 0
                update_fields.extend(
                    [
                        "canvas_width",
                        "canvas_height",
                        "background_opacity",
                        "border_width",
                        "corner_radius",
                    ]
                )
        else:
            overlay.layout_mode = LAYOUT_CUSTOM

        overlay.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0014_scoreoverlay_scoreparticipant"),
    ]

    operations = [
        migrations.AddField(
            model_name="scoreoverlay",
            name="layout_mode",
            field=models.CharField(
                choices=[
                    ("broadcast_duel", "Broadcast duel"),
                    ("broadcast_list", "Broadcast list"),
                    ("custom", "Custom"),
                ],
                default="broadcast_duel",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="scoreoverlay",
            name="canvas_height",
            field=models.PositiveSmallIntegerField(
                default=200,
                validators=[
                    django.core.validators.MinValueValidator(140),
                    django.core.validators.MaxValueValidator(1080),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="scoreoverlay",
            name="background_opacity",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="scoreoverlay",
            name="border_width",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(24),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="scoreoverlay",
            name="corner_radius",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(80),
                ],
            ),
        ),
        migrations.RunPython(upgrade_score_layouts, migrations.RunPython.noop),
    ]
