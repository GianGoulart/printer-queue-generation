"""SKU Layout: compile pattern (mask/regex) and match against text."""

import re
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel


# Optional separator for allow_hyphen_variants: space, dash, underscore
SEP_OPTIONAL = r"[-_\s]*"


def mask_to_regex(mask: str, allow_optional_sep: bool = True, anchored: bool = True) -> str:
    """
    Convert mask pattern to regex.
    Mask placeholders: {name} or {nome-imagem} -> named group (letters, numbers, _, -).
    anchored=False: do not add ^ $ (caller adds \\b for find-in-text).
    """
    # Escape regex specials except { }
    literal = re.sub(r"([.*+?^$()\[\]\\|])", r"\\\1", mask)
    # Placeholder: {categoria}, {nome-imagem}, etc. (allow hyphen in name)
    placeholder_re = r"\{([a-zA-Z_][a-zA-Z0-9_\-]*)\}"
    # Default group: 1-60 chars alphanumeric and hyphen (allow single char e.g. "m", "9")
    group_pattern = r"[a-z0-9][a-z0-9\-]{0,59}" if allow_optional_sep else r"[a-z0-9\-]+"
    regex = re.sub(
        placeholder_re,
        lambda m: f"(?P<{m.group(1)}>{group_pattern})",
        literal,
        flags=re.IGNORECASE,
    )
    # Allow hyphen or underscore between segments (not inside group pattern)
    if allow_optional_sep:
        regex = regex.replace(")-(", ")[-_](")
    return f"^{regex}$" if anchored else (r"\b" + regex + r"\b")


def compile_layout_regex(
    pattern: str,
    pattern_type: str,
    allow_hyphen_variants: bool = True,
    anchored: bool = True,
) -> re.Pattern:
    """
    Return a compiled regex for the layout.
    anchored=False: use \\b boundaries so finditer finds matches inside longer text.
    """
    if pattern_type == "mask":
        raw = mask_to_regex(
            pattern,
            allow_optional_sep=allow_hyphen_variants,
            anchored=anchored,
        )
    else:
        raw = pattern.strip()
        if not anchored:
            raw = r"\b" + raw + r"\b"
        if allow_hyphen_variants:
            raw = raw.replace("[- ]", "[-_\\s]")
    try:
        return re.compile(raw, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"Invalid regex: {e}") from e


def find_matches(
    text: str,
    pattern: str,
    pattern_type: str = "regex",
    allow_hyphen_variants: bool = True,
) -> List[Tuple[str, int, int, Optional[dict]]]:
    """
    Find all non-overlapping matches of the pattern in text.
    Returns list of (full_match, start, end, groups_dict).
    """
    try:
        rx = compile_layout_regex(
            pattern, pattern_type, allow_hyphen_variants, anchored=False
        )
    except ValueError:
        return []
    out = []
    for m in rx.finditer(text):
        g = m.groupdict() if m.lastindex or m.groupdict() else None
        if g and not g:
            g = None
        out.append((m.group(0), m.start(), m.end(), g or None))
    return out


def normalize_sku_for_catalog(raw: str, lowercase: bool = True, strip_seps: bool = True) -> str:
    """Normalize extracted SKU to match catalog: lowercase, remove separators."""
    s = raw.lower() if lowercase else raw
    if strip_seps:
        s = re.sub(r"[-_\s]+", "", s)
    return re.sub(r"[^a-z0-9]", "", s) if lowercase else re.sub(r"[^a-zA-Z0-9]", "", s)


class LayoutTestResult(BaseModel):
    """Result of testing a layout against sample text."""

    matches: List[dict]  # [{full_match, start, end, groups}]
    normalized: Optional[List[str]] = None
    error: Optional[str] = None
