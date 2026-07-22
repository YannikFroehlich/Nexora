from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FONT_BYTES = 3 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
FONT_SIGNATURES = {
    ".woff": (b"wOFF",),
    ".woff2": (b"wOF2",),
    ".ttf": (b"\x00\x01\x00\x00", b"true", b"typ1"),
    ".otf": (b"OTTO",),
}


def _rewind(uploaded_file, position=0):
    try:
        uploaded_file.seek(position)
    except (AttributeError, OSError):
        pass


def validate_overlay_asset(uploaded_file, asset_kind):
    extension = Path(uploaded_file.name).suffix.lower()

    if asset_kind == "image":
        _validate_image(uploaded_file, extension)
        return

    if asset_kind == "font":
        _validate_font(uploaded_file, extension)
        return

    raise ValidationError(_("Select a valid asset type."))


def _validate_image(uploaded_file, extension):
    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise ValidationError(_("Images may not exceed 5 MB."))

    if extension not in IMAGE_EXTENSIONS:
        raise ValidationError(_("Use a PNG, JPEG, or WebP image."))

    position = uploaded_file.tell()
    try:
        image = Image.open(uploaded_file)
        if image.format not in IMAGE_FORMATS:
            raise ValidationError(_("Use a PNG, JPEG, or WebP image."))
        width, height = image.size
        if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
            raise ValidationError(_("The image dimensions are too large."))
        image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise ValidationError(_("The uploaded image is invalid.")) from error
    finally:
        _rewind(uploaded_file, position)


def _validate_font(uploaded_file, extension):
    if uploaded_file.size > MAX_FONT_BYTES:
        raise ValidationError(_("Fonts may not exceed 3 MB."))

    signatures = FONT_SIGNATURES.get(extension)
    if not signatures:
        raise ValidationError(_("Use a WOFF, WOFF2, TTF, or OTF font."))

    position = uploaded_file.tell()
    signature = uploaded_file.read(4)
    _rewind(uploaded_file, position)

    if signature not in signatures:
        raise ValidationError(_("The uploaded font is invalid."))


def asset_content_type(filename):
    extension = Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
    }.get(extension, "application/octet-stream")
