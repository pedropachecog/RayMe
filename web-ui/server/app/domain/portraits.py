"""Portrait upload validation for character assets."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import PurePath, PureWindowsPath

from PIL import Image, UnidentifiedImageError

MAX_PORTRAIT_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PORTRAIT_DIMENSION = 4096
SUPPORTED_PORTRAIT_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


class PortraitValidationError(ValueError):
    """Raised when an uploaded portrait is unsafe or unsupported."""


@dataclass(frozen=True, slots=True)
class ValidatedPortrait:
    content: bytes
    content_type: str
    extension: str
    width: int
    height: int


def validate_portrait_upload(filename: str, content: bytes) -> ValidatedPortrait:
    """Validate untrusted portrait bytes before filesystem storage."""

    _validate_client_filename(filename)
    if len(content) > MAX_PORTRAIT_UPLOAD_BYTES:
        raise PortraitValidationError("Portrait file is over 10 MiB")
    if _looks_like_svg(filename, content):
        raise PortraitValidationError("Portrait must be PNG, JPEG, or WebP")

    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PortraitValidationError("Portrait image cannot be read") from exc

    if image_format not in SUPPORTED_PORTRAIT_FORMATS:
        raise PortraitValidationError("Portrait must be PNG, JPEG, or WebP")
    if width > MAX_PORTRAIT_DIMENSION or height > MAX_PORTRAIT_DIMENSION:
        raise PortraitValidationError("Portrait dimensions must be 4096 x 4096 or smaller")

    content_type, extension = SUPPORTED_PORTRAIT_FORMATS[image_format]
    return ValidatedPortrait(
        content=content,
        content_type=content_type,
        extension=extension,
        width=width,
        height=height,
    )


def _validate_client_filename(filename: str) -> None:
    if not filename or filename in {".", ".."}:
        raise PortraitValidationError("Portrait filename is invalid")
    if "\x00" in filename or "/" in filename or "\\" in filename:
        raise PortraitValidationError("Portrait filename must not contain path separators")
    if PurePath(filename).is_absolute() or PureWindowsPath(filename).is_absolute():
        raise PortraitValidationError("Portrait filename must not be a path")
    if PurePath(filename).name != filename:
        raise PortraitValidationError("Portrait filename must not contain path components")


def _looks_like_svg(filename: str, content: bytes) -> bool:
    if filename.lower().endswith(".svg"):
        return True
    prefix = content[:256].lstrip().lower()
    return prefix.startswith(b"<svg") or b"<svg" in prefix[:64]


__all__ = [
    "MAX_PORTRAIT_DIMENSION",
    "MAX_PORTRAIT_UPLOAD_BYTES",
    "PortraitValidationError",
    "SUPPORTED_PORTRAIT_FORMATS",
    "ValidatedPortrait",
    "validate_portrait_upload",
]
