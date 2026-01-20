"""SKU extraction from filenames."""

import re
from typing import Optional


# Common size suffixes to remove
SIZE_SUFFIXES = [
    "P", "M", "G", "GG", "XG", "PP",  # Portuguese sizes
    "S", "L", "XL", "XXL", "XXXL",    # English sizes
    "1", "2", "3", "4", "5", "6",     # Numeric sizes
]

# Common side/position suffixes to remove
POSITION_SUFFIXES = [
    "FRENTE", "COSTAS", "FRONT", "BACK",
    "DIREITA", "ESQUERDA", "LEFT", "RIGHT",
    "MANGA", "SLEEVE",
]


def normalize_sku(sku: str) -> str:
    """Normalize SKU string.

    Normalization rules:
    - Convert to lowercase
    - Remove separators (-, _, spaces)
    - Keep only alphanumeric characters
    - Remove leading zeros from numeric parts

    Args:
        sku: SKU string to normalize

    Returns:
        Normalized SKU

    Examples:
        >>> normalize_sku("CAM-001")
        'cam001'
        >>> normalize_sku("CAM_001_P")
        'cam001p'
        >>> normalize_sku("  CAM 001  ")
        'cam001'
    """
    if not sku:
        return ""

    # Convert to lowercase
    sku = sku.lower().strip()

    # Remove separators
    sku = sku.replace("-", "").replace("_", "").replace(" ", "")

    # Keep only alphanumeric
    sku = re.sub(r"[^a-z0-9]", "", sku)

    return sku


def extract_sku(filename: str) -> str:
    """Extract and normalize SKU from filename.

    Extraction rules:
    1. Remove file extension
    2. Remove common size suffixes (P, M, G, GG, etc)
    3. Remove common position suffixes (FRENTE, COSTAS, etc)
    4. Remove separators
    5. Normalize to lowercase alphanumeric

    Args:
        filename: Filename to extract SKU from

    Returns:
        Extracted and normalized SKU

    Examples:
        >>> extract_sku("CAM001-P.png")
        'cam001'
        >>> extract_sku("CAM_001_P_FRENTE.png")
        'cam001'
        >>> extract_sku("001-CAM-M.jpg")
        '001cam'
        >>> extract_sku("LOGO_EMPRESA.png")
        'logoempresa'
        >>> extract_sku("BASIC-SIZE-G.jpeg")
        'basicsize'
    """
    if not filename:
        return ""

    # Remove file extension
    sku = filename.rsplit(".", 1)[0]

    # Convert to uppercase for easier matching
    sku_upper = sku.upper()

    # Remove size suffixes
    for suffix in SIZE_SUFFIXES:
        # Try with separators
        for sep in ["-", "_", " "]:
            pattern = f"{sep}{suffix}$"
            sku_upper = re.sub(pattern, "", sku_upper)
            # Also try with separator before
            pattern = f"^{suffix}{sep}"
            sku_upper = re.sub(pattern, "", sku_upper)

    # Remove position suffixes
    for suffix in POSITION_SUFFIXES:
        # Try with separators
        for sep in ["-", "_", " "]:
            pattern = f"{sep}{suffix}$"
            sku_upper = re.sub(pattern, "", sku_upper)

    # Normalize
    return normalize_sku(sku_upper)


def extract_sku_variants(filename: str) -> list[str]:
    """Extract multiple possible SKU variants from filename.

    Useful for fuzzy matching when exact match fails.

    Args:
        filename: Filename to extract SKU from

    Returns:
        List of possible SKU variants

    Examples:
        >>> extract_sku_variants("CAM001-P.png")
        ['cam001', 'cam001p', 'cam']
    """
    base_sku = extract_sku(filename)
    variants = [base_sku]

    # Add variant with size suffix
    sku_with_ext = filename.rsplit(".", 1)[0]
    normalized_with_suffix = normalize_sku(sku_with_ext)
    if normalized_with_suffix != base_sku:
        variants.append(normalized_with_suffix)

    # Add prefix variant (first letters)
    if len(base_sku) > 3:
        # Get letter prefix
        letters = re.match(r"^[a-z]+", base_sku)
        if letters:
            variants.append(letters.group())

    return list(dict.fromkeys(variants))  # Remove duplicates while preserving order
