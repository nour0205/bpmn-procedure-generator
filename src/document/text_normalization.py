"""Conservative French text cleanup for generated business documents."""

from __future__ import annotations

import re


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


def normalize_french_business_text(value: str | None) -> str:
    """Apply safe display corrections without changing BPMN meaning."""

    if value is None:
        return ""

    text = str(value)
    text = text.replace("\ufffe", "-").replace(
        "\uffff",
        "-",
    )
    text = text.replace("\u00ad", "")
    text = " ".join(text.split()).strip()

    text = re.sub(
        r"\bpdts\b",
        "produits",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bmodèle\s+pré[- ]définis?\b",
        "modèle prédéfini",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bmodèle\s+pré[- ]définie\b",
        "modèle prédéfini",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bDirection\s+Financi[èé]re\b",
        "Direction Financière",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bcouverture de stock relatif\b",
        "couverture de stock relative",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bDétermination des quantités "
        r"par des articles\b",
        "Détermination des quantités par article",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bLes prévisions de vente,\s*"
        r"niveau de stock actuel\b",
        "les prévisions de vente et "
        "le niveau de stock actuel",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+([,.])",
        r"\1",
        text,
    )
    text = re.sub(
        r"\s*([;:!?])",
        r" \1",
        text,
    )
    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def symbolic_delay_labels(value: str | None) -> list[str]:
    """Return unresolved symbolic delays such as J+X or J+Y."""

    if not value:
        return []

    labels = [
        re.sub(r"\s+", "", match.group(0)).upper()
        for match in _SYMBOLIC_DELAY.finditer(str(value))
    ]

    return list(dict.fromkeys(labels))
