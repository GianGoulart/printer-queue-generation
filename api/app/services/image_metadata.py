"""Image metadata extraction."""

import io
from typing import Any, Dict, Optional

from PIL import Image


class ImageMetadataError(Exception):
    """Exception for image metadata extraction errors."""

    pass


def extract_image_metadata(image_bytes: bytes) -> Dict[str, Any]:
    """Extract metadata from image bytes.

    Args:
        image_bytes: Image content as bytes

    Returns:
        Dict with metadata:
            - width_px: Image width in pixels
            - height_px: Image height in pixels
            - format: Image format (PNG, JPEG, etc)
            - mode: Color mode (RGB, RGBA, etc)
            - dpi: DPI tuple (x, y) if available
            - size_bytes: File size in bytes
            - has_transparency: Whether image has transparency

    Raises:
        ImageMetadataError: If image cannot be opened or metadata extracted

    Examples:
        >>> with open("image.png", "rb") as f:
        ...     metadata = extract_image_metadata(f.read())
        >>> metadata['width_px']
        800
        >>> metadata['format']
        'PNG'
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))

        # Extract DPI (defaults to (72, 72) if not present)
        dpi = img.info.get("dpi", (72, 72))
        if isinstance(dpi, (int, float)):
            dpi = (dpi, dpi)

        # Check for transparency
        has_transparency = False
        if img.mode in ("RGBA", "LA", "P"):
            has_transparency = True
        elif img.mode == "P" and "transparency" in img.info:
            has_transparency = True

        metadata = {
            "width_px": img.width,
            "height_px": img.height,
            "format": img.format if img.format else "UNKNOWN",
            "mode": img.mode,
            "dpi": dpi,
            "size_bytes": len(image_bytes),
            "has_transparency": has_transparency,
        }

        # Add aspect ratio
        if img.height > 0:
            metadata["aspect_ratio"] = round(img.width / img.height, 3)

        # Calculate approximate dimensions in mm at 300 DPI
        dpi_x = dpi[0] if dpi[0] > 0 else 72
        dpi_y = dpi[1] if dpi[1] > 0 else 72

        metadata["width_mm"] = round((img.width / dpi_x) * 25.4, 2)
        metadata["height_mm"] = round((img.height / dpi_y) * 25.4, 2)

        return metadata

    except Exception as e:
        raise ImageMetadataError(f"Failed to extract image metadata: {e}")


def validate_image_for_dtf(metadata: Dict[str, Any], min_dpi: int = 300) -> Dict[str, Any]:
    """Validate image metadata for DTF printing requirements.

    Args:
        metadata: Image metadata dict
        min_dpi: Minimum DPI requirement (default: 300)

    Returns:
        Dict with validation results:
            - valid: Boolean indicating if image meets requirements
            - errors: List of error messages
            - warnings: List of warning messages

    Examples:
        >>> metadata = extract_image_metadata(image_bytes)
        >>> validation = validate_image_for_dtf(metadata)
        >>> validation['valid']
        True
    """
    errors = []
    warnings = []

    # Check DPI
    dpi_x, dpi_y = metadata.get("dpi", (0, 0))
    if dpi_x < min_dpi or dpi_y < min_dpi:
        errors.append(f"DPI too low: {dpi_x}x{dpi_y} (minimum: {min_dpi})")

    # Check format
    format_name = metadata.get("format", "").upper()
    if format_name not in ["PNG", "JPEG", "JPG"]:
        warnings.append(f"Unusual format: {format_name} (recommended: PNG or JPEG)")

    # Check mode
    mode = metadata.get("mode", "")
    if mode not in ["RGB", "RGBA"]:
        warnings.append(f"Color mode {mode} may need conversion (recommended: RGB or RGBA)")

    # Check size
    size_mb = metadata.get("size_bytes", 0) / (1024 * 1024)
    if size_mb > 50:
        warnings.append(f"Large file size: {size_mb:.1f}MB (may slow processing)")

    # Check dimensions
    width = metadata.get("width_px", 0)
    height = metadata.get("height_px", 0)
    if width < 100 or height < 100:
        errors.append(f"Image too small: {width}x{height}px")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
