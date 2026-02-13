"""
SKU layout matching: compile tenant regex/mask and find matches in text.
Mirrors API sku_layout_service logic for use in worker (no API dependency).
"""

import re
from typing import List, Optional, Tuple

# Optional separator: space, dash, underscore
SEP_OPTIONAL = r"[-_\s]*"
GROUP_PATTERN = r"[a-z0-9][a-z0-9\-]{0,59}"


def mask_to_regex(mask: str, allow_optional_sep: bool = True, anchored: bool = True) -> str:
    """Convert mask pattern to regex. anchored=False adds \\b for find-in-text."""
    literal = re.sub(r"([.*+?^$()\[\]\\|])", r"\\\1", mask)
    placeholder_re = r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}"
    regex = re.sub(
        placeholder_re,
        lambda m: f"(?P<{m.group(1)}>{GROUP_PATTERN})",
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
    """Compile layout pattern (regex or mask) for matching."""
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
    return re.compile(raw, re.IGNORECASE)


def find_matches(
    text: str,
    pattern: str,
    pattern_type: str = "regex",
    allow_hyphen_variants: bool = True,
    full_line: bool = False,
) -> List[Tuple[str, int, int, Optional[dict]]]:
    """
    Find all non-overlapping matches of the pattern in text.
    Returns list of (full_match, start, end, groups_dict).
    If full_line=True, only match when the entire (stripped) line matches the pattern,
    so e.g. a 4-segment layout won't match "inf-9-4-naruto-m" (5 segments).
    """
    try:
        rx = compile_layout_regex(
            pattern,
            pattern_type,
            allow_hyphen_variants,
            anchored=full_line,
        )
    except re.error:
        return []
    out = []
    if full_line:
        # Require whole line to match (no partial match)
        stripped = text.strip()
        m = rx.fullmatch(stripped)
        if m:
            g = m.groupdict() if m.groupdict() else None
            if g and all(v is None for v in (g or {}).values()):
                g = None
            out.append((m.group(0), 0, len(m.group(0)), g or None))
        return out
    for m in rx.finditer(text):
        g = m.groupdict() if m.groupdict() else None
        if g and all(v is None for v in (g or {}).values()):
            g = None
        out.append((m.group(0), m.start(), m.end(), g or None))
    return out
