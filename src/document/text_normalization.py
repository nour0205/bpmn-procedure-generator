"""Document text-normalization compatibility module."""

from __future__ import annotations

import re

from common.text_normalization import (
    canonical_business_text,
    normalize_french_business_text,
)

__all__ = [
    "canonical_business_text",
    "normalize_french_business_text",
]


_SYMBOLIC_DELAY = re.compile(
    r"\bJ\s*\+\s*[A-Za-z]\b",
    flags=re.IGNORECASE,
)


def normalize_branch_label(value: str | None) -> str | None:
    """Normalize common yes/no labels without changing other labels."""

    if value is None:
        return None

    cleaned = " ".join(str(value).split()).strip()
    lowered = cleaned.casefold()

    if lowered == "oui":
        return "Oui"

    if lowered == "non":
        return "Non"

    return cleaned or None


def symbolic_delay_labels(value: str | None) -> list[str]:
    """Return unresolved symbolic delays such as J+X or J+Y."""

    if not value:
        return []

    labels = [
        re.sub(r"\s+", "", match.group(0)).upper()
        for match in _SYMBOLIC_DELAY.finditer(str(value))
    ]

    return list(dict.fromkeys(labels))
