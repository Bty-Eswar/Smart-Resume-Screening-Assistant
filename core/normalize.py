# core/normalize.py — SDD §2 / BUILD_PROMPTS M7
import re
import unicodedata


def normalize_ws(s: str) -> str:
    """Normalize whitespace and unicode compatibility characters.

    Applies NFKC normalization, collapses all whitespace runs to single spaces, and strips ends.
    Deterministic, pure, and locale-independent.
    """
    if not s:
        return ""
    # NFKC compatibility decomposition and canonical composition
    normalized = unicodedata.normalize("NFKC", s)
    # Collapse all whitespace runs (spaces, tabs, newlines, carriage returns) to a single space
    collapsed = re.sub(r"\s+", " ", normalized)
    return collapsed.strip()
