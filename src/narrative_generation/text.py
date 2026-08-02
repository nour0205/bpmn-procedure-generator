"""Text normalization and conservative semantic helpers."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any


PLACEHOLDER_PATTERNS = (
    "texte à générer",
    "texte a generer",
    "à compléter",
    "a completer",
    "todo",
    "tbd",
    "placeholder",
)

CONTROLLED_UNSUPPORTED_TERMS = (
    "retard",
    "dépassement",
    "expiration",
    "optimisation",
    "efficacité",
    "risque",
    "conformité",
    "impact économique",
    "impact financier",
    "besoin stratégique",
    "contrainte opérationnelle",
)

STOPWORDS = {
    "a",
    "au",
    "aux",
    "avec",
    "ce",
    "ces",
    "cette",
    "de",
    "des",
    "du",
    "en",
    "et",
    "la",
    "le",
    "les",
    "l",
    "par",
    "pour",
    "sur",
    "un",
    "une",
    "dans",
    "qui",
    "que",
    "se",
    "son",
    "sa",
    "ses",
    "leur",
    "leurs",
    "est",
    "sont",
    "etre",
    "être",
    "via",
    "ainsi",
    "apres",
    "avant",
    "plus",
}

PURPOSE_MARKER_PATTERN = re.compile(
    r"\b(?:pour|afin\s+d(?:e|['’])?|"
    r"en\s+vue\s+d(?:e|['’])?|"
    r"dans\s+le\s+but\s+d(?:e|['’])?|"
    r"permettant\s+d(?:e|['’])?|"
    r"ce\s+qui\s+permet\s+d(?:e|['’])?)",
    flags=re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9+]+", " ", normalized)
    return " ".join(normalized.split())


def normalize_business_french(text: str) -> str:
    """Apply conservative display-language corrections to generated prose."""

    value = " ".join(str(text).split()).strip()
    value = re.sub(
        r"\bmodèle\s+pré[-\s]?définis\b",
        "modèle prédéfini",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\bpré[-\s]?défini(e?s?|s)?\b",
        lambda match: "prédéfini" + (match.group(1) or ""),
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\bpdts\b",
        "produits",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    return value


def clean_sentence(text: str) -> str:
    sentence = normalize_business_french(text)

    if not sentence:
        raise ValueError("A factual sentence cannot be empty.")

    if sentence[-1] not in ".!?":
        sentence += "."

    return sentence


def lowercase_first_letter(text: str) -> str:
    characters = list(str(text))

    for index, character in enumerate(characters):
        if character.isalpha():
            characters[index] = character.lower()
            break

    return "".join(characters)


def semantic_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()

    if not isinstance(item, dict):
        return str(item).strip()

    for key in (
        "text",
        "name",
        "label",
        "description",
        "value",
        "content",
    ):
        value = item.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    return ""


def collect_texts(
    operation: dict,
    field_name: str,
) -> list[str]:
    result: list[str] = []

    for item in operation.get(field_name, []) or []:
        text = semantic_text(item)

        if text and text not in result:
            result.append(text)

    return result


def light_stem(token: str) -> str:
    stem = token

    for suffix in (
        "issements",
        "issement",
        "atrices",
        "ateurs",
        "ations",
        "ation",
        "ements",
        "ement",
        "ées",
        "ée",
        "és",
        "es",
        "s",
    ):
        if stem.endswith(suffix) and len(stem) > len(suffix) + 3:
            stem = stem[: -len(suffix)]
            break

    if stem.startswith("repond") or stem.startswith("repons"):
        return "reponse"

    if stem.startswith("communic"):
        return "communic"

    if stem.startswith("valid"):
        return "valid"

    if stem.startswith("gener"):
        return "gener"

    return stem


def meaningful_tokens(text: str) -> set[str]:
    result: set[str] = set()

    for token in normalize_text(text).split():
        if token in STOPWORDS or len(token) < 3:
            continue

        result.add(light_stem(token))

    return result


def extract_timer_labels(text: str) -> list[str]:
    labels: list[str] = []

    for match in re.finditer(
        r"\bJ\s*\+\s*([A-Za-z0-9]+)\b",
        str(text),
        flags=re.IGNORECASE,
    ):
        label = f"J+{match.group(1)}"

        if label not in labels:
            labels.append(label)

    return labels


def contains_timer_label(
    text: str,
    timer_label: str,
) -> bool:
    suffix = timer_label.split("+", 1)[1]

    return (
        re.search(
            rf"\bJ\s*\+\s*{re.escape(suffix)}\b",
            str(text),
            flags=re.IGNORECASE,
        )
        is not None
    )


def mentions_no_response(text: str) -> bool:
    normalized = normalize_text(text)

    return any(
        marker in normalized
        for marker in (
            "sans reponse",
            "absence de reponse",
            "aucune reponse",
            "non reponse",
            "n a pas repondu",
        )
    )


def stable_hash(payload: dict) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()
