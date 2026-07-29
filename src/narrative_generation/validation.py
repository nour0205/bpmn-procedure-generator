"""Validate model rewrites and assemble final paragraphs."""

from __future__ import annotations

import math

from narrative_generation.models import GeneratedUnit
from narrative_generation.text import (
    CONTROLLED_UNSUPPORTED_TERMS,
    PLACEHOLDER_PATTERNS,
    PURPOSE_MARKER_PATTERN,
    clean_sentence,
    contains_timer_label,
    lowercase_first_letter,
    meaningful_tokens,
    normalize_text,
)


NEUTRAL_CONNECTORS = (
    "Ensuite",
    "Puis",
    "Par la suite",
    "Après cette étape",
)


def actor_is_preserved(
    actor: str,
    sentence: str,
) -> bool:
    normalized_actor = normalize_text(actor)
    normalized_sentence = normalize_text(sentence)

    if normalized_actor in normalized_sentence:
        return True

    actor_tokens = meaningful_tokens(actor)
    sentence_tokens = meaningful_tokens(sentence)

    if not actor_tokens:
        return True

    overlap = len(actor_tokens & sentence_tokens)
    required = max(
        1,
        math.ceil(0.60 * len(actor_tokens)),
    )

    return overlap >= required


def validate_rewritten_fact(
    fact: dict,
    sentence: str,
) -> None:
    cleaned = clean_sentence(sentence)
    normalized_sentence = normalize_text(cleaned)

    for placeholder in PLACEHOLDER_PATTERNS:
        if normalize_text(placeholder) in normalized_sentence:
            raise ValueError(
                f"Placeholder detected in {fact['fact_id']}."
            )

    if fact["locked"]:
        if (
            " ".join(cleaned.split())
            != " ".join(fact["text"].split())
        ):
            raise ValueError(
                f"{fact['fact_id']} is locked and must be copied exactly."
            )

        return

    for timer_label in fact.get("timer_labels", []):
        if not contains_timer_label(cleaned, timer_label):
            raise ValueError(
                f"{fact['fact_id']} does not preserve "
                f"the marker {timer_label!r}."
            )

    actor = str(fact.get("actor", "") or "").strip()

    if (
        fact.get("kind") == "operation"
        and actor
        and not actor_is_preserved(actor, cleaned)
    ):
        raise ValueError(
            f"{fact['fact_id']} does not preserve actor {actor!r}."
        )

    execution_mode = str(
        fact.get("execution_mode", "")
    ).casefold()

    if (
        fact.get("kind") == "operation"
        and execution_mode == "automated"
    ):
        words = set(normalized_sentence.split())

        if not ("systeme" in words or "si" in words):
            raise ValueError(
                f"{fact['fact_id']} does not attribute "
                "the action to the system."
            )

    if (
        fact.get("kind") == "operation"
        and not fact.get("allow_purpose_clause")
        and PURPOSE_MARKER_PATTERN.search(cleaned)
        and not PURPOSE_MARKER_PATTERN.search(fact["source_text"])
    ):
        raise ValueError(
            f"{fact['fact_id']} adds an unsupported purpose clause."
        )

    for term in CONTROLLED_UNSUPPORTED_TERMS:
        normalized_term = normalize_text(term)

        if (
            normalized_term in normalized_sentence
            and normalized_term
            not in normalize_text(fact["source_text"])
        ):
            raise ValueError(
                f"{fact['fact_id']} adds unsupported information: "
                f"{term!r}."
            )

    expected_tokens = set(fact.get("required_tokens", []))

    if expected_tokens:
        generated_tokens = meaningful_tokens(cleaned)
        overlap = len(expected_tokens & generated_tokens)
        required = max(
            1,
            math.ceil(0.30 * len(expected_tokens)),
        )

        if overlap < required:
            raise ValueError(
                f"{fact['fact_id']} preserves too little "
                f"source information ({overlap}/{required})."
            )


def validate_generated_unit(
    unit: dict,
    generated: GeneratedUnit,
) -> list[str]:
    expected_ids = [
        fact["fact_id"]
        for fact in unit["facts"]
    ]
    received_ids = [
        item.fact_id
        for item in generated.sentences
    ]

    if received_ids != expected_ids:
        raise ValueError(
            "Generated fact IDs or order are incorrect. "
            f"expected={expected_ids}; received={received_ids}."
        )

    result: list[str] = []

    for fact, item in zip(
        unit["facts"],
        generated.sentences,
        strict=True,
    ):
        validate_rewritten_fact(
            fact,
            item.sentence,
        )
        result.append(clean_sentence(item.sentence))

    return result


def assemble_paragraph(
    unit: dict,
    sentences: list[str],
) -> str:
    if not sentences:
        raise ValueError(
            f"{unit['unit_id']} has no sentence."
        )

    prefix = str(unit.get("prefix", "") or "")
    first_sentence = sentences[0].strip()

    if prefix:
        paragraph = (
            prefix
            + lowercase_first_letter(first_sentence)
        )
    else:
        paragraph = first_sentence

    for index, sentence in enumerate(sentences[1:]):
        connector = NEUTRAL_CONNECTORS[
            index % len(NEUTRAL_CONNECTORS)
        ]
        paragraph += (
            f" {connector}, "
            + lowercase_first_letter(sentence.strip())
        )

    return " ".join(paragraph.split()).strip()
