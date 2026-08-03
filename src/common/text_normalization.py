"""Shared business-text normalization utilities."""

from __future__ import annotations

import re
import unicodedata


def normalize_french_business_text(
    value: str | None,
) -> str:
    """Return a corrected display form without changing business meaning."""

    if value is None:
        return ""

    text = str(value)
    text = text.replace("\u00ad", "")
    text = text.replace("\ufffe", "-")
    text = text.replace("\uffff", "-")
    text = " ".join(text.split()).strip()

    replacements: tuple[tuple[str, str], ...] = (
        (r"\bpdts\b", "produits"),
        (
            r"\bmodèle\s+pré[- ]définis?\b",
            "modèle prédéfini",
        ),
        (
            r"\bmodèle\s+pré[- ]définie\b",
            "modèle prédéfini",
        ),
        (
            r"\bDirection\s+Financi[èé]re\b",
            "Direction Financière",
        ),
        (
            r"\bcouverture de stock relatif\b",
            "couverture de stock relative",
        ),
        (
            (
                r"\bDétermination des quantités "
                r"par (?:des )?articles?\b"
            ),
            "Détermination des quantités par article",
        ),
        (
            (
                r"\bLes prévisions de vente,\s*"
                r"niveau de stock actuel\b"
            ),
            (
                "les prévisions de vente et "
                "le niveau de stock actuel"
            ),
        ),
        (
            (
                r"\bDétermination des quantités "
                r"par article par code besoin "
                r"\(par poste\)\s*/\s*spécialité"
                r",?\s*etc\.?"
            ),
            (
                "Les quantités sont déterminées "
                "par article, selon le code besoin "
                "(par poste) ou la spécialité."
            ),
        ),
        (
            (
                r"\bhospitalier,\s*"
                r"Officinal,\s*"
                r"vaccin\b"
            ),
            "hospitalier, officinal, vaccin",
        ),
    )

    for pattern, replacement in replacements:
        text = re.sub(
            pattern,
            replacement,
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(r"\s+([,.])", r"\1", text)
    text = re.sub(r"\s*([;:!?])", r" \1", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def canonical_business_text(
    value: str | None,
) -> str:
    """Return a canonical value for semantic equality comparisons."""

    text = normalize_french_business_text(value)
    text = unicodedata.normalize("NFKC", text)
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("«", '"')
        .replace("»", '"')
    )
    text = text.casefold()

    # Ignore harmless typography differences during comparison.
    text = re.sub(r"\s*([,;:!?])\s*", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text
