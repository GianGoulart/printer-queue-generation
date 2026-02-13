"""SKU extraction from filenames."""

import re
from typing import List, Optional


# Unicode ligatures that must be expanded to ASCII before [^a-z0-9] strip (e.g. PDF "ﬂoyd" -> "floyd")
_UNICODE_LIGATURES = (
    ("\uFB02", "fl"),   # ﬂ (LATIN SMALL LIGATURE FL)
    ("\uFB01", "fi"),   # ﬁ
    ("\uFB00", "ff"),   # ﬀ
    ("\uFB04", "ffl"),  # ﬄ
    ("\uFB03", "ffi"),  # ﬃ
)

# Position suffixes to remove from end (tenant size is via sizing_prefixes only)
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

    # Expand Unicode ligatures so "ﬂoyd" -> "floyd" (otherwise ﬂ is stripped by [^a-z0-9])
    for lig, ascii_eq in _UNICODE_LIGATURES:
        sku = sku.replace(lig, ascii_eq)

    # Remove separators
    sku = sku.replace("-", "").replace("_", "").replace(" ", "")

    # Keep only alphanumeric
    sku = re.sub(r"[^a-z0-9]", "", sku)

    return sku


def sku_to_design(sku: str, sizing_prefixes: Optional[List[str]] = None) -> str:
    """Return the design part of a SKU by stripping tenant sizing prefixes.

    Same logic as the worker's resolver: normalize, strip longest prefix from start,
    then optionally strip leading digits (e.g. inf1213sonic8 -> inf12 -> 13sonic8 -> sonic8).

    Args:
        sku: Raw SKU (e.g. from picklist: inf1213sonic8, bl74butterfly).
        sizing_prefixes: Tenant sku_prefix values (e.g. ["inf-12", "bl-7"]). Can contain hyphens.

    Returns:
        Design-only SKU for display/lookup, or normalized sku if no prefix matched.
    """
    if not sku:
        return ""
    sku_norm = normalize_sku(sku)
    if not sizing_prefixes:
        return sku_norm
    # Normalize prefixes like the worker: lower, no hyphens
    prefixes_norm = [
        p.strip().lower().replace("-", "").replace("_", "")
        for p in sizing_prefixes
        if p and p.strip()
    ]
    prefixes_norm = sorted(set(prefixes_norm), key=len, reverse=True)
    remainder = sku_norm
    for prefix in prefixes_norm:
        if not prefix or not sku_norm.startswith(prefix):
            continue
        remainder = sku_norm[len(prefix) :].lstrip("-_")
        break
    if not remainder:
        return sku_norm
    # Strip leading numeric segment (e.g. 13sonic8 -> sonic8)
    m = re.match(r"^[0-9]+[-_]?", remainder)
    if m:
        design = remainder[m.end() :].strip("-_") or remainder
    else:
        design = remainder
    return design or sku_norm


def extract_sku(
    filename: str,
    sizing_prefixes: Optional[List[str]] = None,
) -> str:
    """Extract and normalize SKU from filename.

    Uses only tenant sizing profile prefixes (sku_prefix): strip from start only those.
    No global size list; position suffixes (FRENTE, COSTAS, etc.) are stripped from end.

    Args:
        filename: Filename to extract SKU from
        sizing_prefixes: List of tenant sizing profile prefixes (e.g. ["bl-", "inf-2", "u-11"]).
            Only these are stripped from the start (longest match first). When None, nothing is stripped from start.

    Returns:
        Extracted and normalized SKU (lowercase, no separators)
    """
    if not filename:
        return ""

    sku = filename.rsplit(".", 1)[0]
    sku_upper = sku.upper()

    # Strip from start only tenant sizing prefixes (longest first)
    if sizing_prefixes:
        sorted_prefixes = sorted(
            [p.strip() for p in sizing_prefixes if p and p.strip()],
            key=len,
            reverse=True,
        )
        while True:
            changed = False
            for prefix in sorted_prefixes:
                if not prefix:
                    continue
                prefix_upper = prefix.upper()
                if sku_upper.startswith(prefix_upper):
                    sku_upper = sku_upper[len(prefix_upper) :].lstrip("-_ ")
                    changed = True
                    break
            if not changed:
                break

    # Remove position suffixes from end only
    for suffix in POSITION_SUFFIXES:
        for sep in ["-", "_", " "]:
            pattern = f"{sep}{suffix}$"
            sku_upper = re.sub(pattern, "", sku_upper)

    # If we stripped a sizing prefix, also strip leading numeric segment (position index)
    # so "7-skull-gg" -> "skull-gg" and design-only assets match (e.g. skullgg like butterflyp)
    if sizing_prefixes and sku_upper:
        m = re.match(r"^[0-9]+[-_\s]*", sku_upper)
        if m:
            sku_upper = sku_upper[m.end() :].strip("-_ ")

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
