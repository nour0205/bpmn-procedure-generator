"""Deterministic descriptions and validation of model output."""

from __future__ import annotations

import math
import re
from collections import defaultdict

from procedure_generation.models import GeneratedOperationContent
from procedure_generation.text import (
    CONTROLLED_UNSUPPORTED_TERMS,
    PLACEHOLDER_PATTERNS,
    PURPOSE_MARKER_PATTERN,
    SUBPROCESS_EXPANSION_PATTERN,
    clean_sentence,
    collect_texts,
    contains_timer_label,
    extract_timer_labels,
    lowercase_first_letter,
    meaningful_tokens,
    mentions_no_response,
    normalize_text,
)


def effective_actor(context: dict) -> str | None:
    execution_mode = str(
        context.get("execution_mode", "")
    ).casefold()

    if execution_mode == "automated":
        return "Le système"

    if execution_mode == "event":
        return None

    actor = str(
        context.get("actor_name", "") or ""
    ).strip()

    return actor or None


def deterministic_event_description(
    context: dict,
) -> str:
    raw_name = str(
        context.get("raw_name", "")
    ).strip()
    normalized_name = normalize_text(
        raw_name
    )

    timers = extract_timer_labels(
        raw_name
    )
    timer = timers[0] if timers else None

    if (
        timer
        and mentions_no_response(
            raw_name
        )
    ):
        supplier = (
            " du Fournisseur"
            if "fournisseur"
            in normalized_name
            else ""
        )

        return clean_sentence(
            f"À l’événement « {timer} », "
            f"aucune réponse{supplier} "
            "n’a été reçue"
        )

    if (
        "communication d une nouvelle date "
        "de reception"
        in normalized_name
        and "fournisseur"
        in normalized_name
    ):
        channel = (
            " sur le portail"
            if "portail"
            in normalized_name
            else ""
        )

        return clean_sentence(
            "Une nouvelle date de réception "
            "est communiquée par le "
            f"Fournisseur{channel}"
        )

    if timer:
        return clean_sentence(
            "Le processus atteint le repère "
            f"temporel « {timer} »"
        )

    event_role = str(
        context.get("event_role", "") or ""
    ).casefold()

    if event_role == "start":
        return clean_sentence(
            f"L’événement « {raw_name} » "
            "déclenche le processus"
        )

    if event_role == "end":
        return clean_sentence(
            f"L’événement « {raw_name} » "
            "marque la fin du processus"
        )

    return clean_sentence(
        f"L’événement « {raw_name} » "
        "intervient dans le processus"
    )


def _integrate_notes(
    base_sentence: str,
    notes: list[dict],
) -> tuple[str, list[str]]:
    base = clean_sentence(
        base_sentence
    ).rstrip(".")
    sentences: list[str] = [base]
    incorporated_ids: list[str] = []

    for note in notes:
        note_id = str(note["id"])
        raw_note = " ".join(
            str(note["text"]).split()
        ).strip().rstrip(".")

        if not raw_note:
            continue

        on_basis_match = re.match(
            r"^(Sur la base d['’]un|"
            r"Sur la base de|À partir de|Selon)\b",
            raw_note,
            flags=re.IGNORECASE,
        )
        possible_match = re.match(
            r"^Il est possible de\s+(.+)$",
            raw_note,
            flags=re.IGNORECASE,
        )
        additional_match = re.match(
            r"^Avec une possibilité de\s+(.+)$",
            raw_note,
            flags=re.IGNORECASE,
        )

        if (
            on_basis_match
            and len(sentences) == 1
        ):
            sentences[0] += (
                " "
                + lowercase_first_letter(
                    raw_note
                )
            )
        elif possible_match:
            sentences.append(
                "Cette activité permet de "
                + lowercase_first_letter(
                    possible_match.group(1)
                )
            )
        elif additional_match:
            sentences.append(
                "Elle permet également de "
                + lowercase_first_letter(
                    additional_match.group(1)
                )
            )
        else:
            sentences.append(raw_note)

        incorporated_ids.append(note_id)

    description = " ".join(
        clean_sentence(sentence)
        for sentence in sentences
    )

    return description, incorporated_ids


def deterministic_description(
    context: dict,
) -> tuple[str, list[str]]:
    raw_name = str(
        context["raw_name"]
    ).strip()
    execution_mode = str(
        context.get("execution_mode", "")
    ).casefold()
    actor = effective_actor(context)

    if execution_mode == "event":
        base = deterministic_event_description(
            context
        )
    elif execution_mode == "automated":
        base = clean_sentence(
            "Le système exécute automatiquement "
            f"l’activité « {raw_name} »"
        )
    elif execution_mode == "subprocess":
        if actor:
            base = clean_sentence(
                f"{actor} déclenche le "
                f"sous-processus « {raw_name} »"
            )
        else:
            base = clean_sentence(
                "Le flux atteint le "
                f"sous-processus « {raw_name} »"
            )
    elif actor:
        base = clean_sentence(
            f"{actor} réalise l’activité "
            f"« {raw_name} »"
        )
    else:
        base = clean_sentence(
            f"L’activité « {raw_name} » "
            "est exécutée"
        )

    return _integrate_notes(
        base,
        context.get("notes", []),
    )


def actor_is_preserved(
    actor: str,
    description: str,
) -> bool:
    normalized_actor = normalize_text(
        actor
    )
    normalized_description = normalize_text(
        description
    )

    if normalized_actor in normalized_description:
        return True

    actor_tokens = meaningful_tokens(actor)
    description_tokens = meaningful_tokens(
        description
    )

    if not actor_tokens:
        return True

    overlap = len(
        actor_tokens
        & description_tokens
    )
    required = max(
        1,
        math.ceil(
            0.60 * len(actor_tokens)
        ),
    )

    return overlap >= required


def _note_is_covered(
    note_text: str,
    description: str,
) -> bool:
    normalized_note = normalize_text(
        note_text
    )
    normalized_description = normalize_text(
        description
    )

    if (
        normalized_note
        and normalized_note
        in normalized_description
    ):
        return True

    note_tokens = meaningful_tokens(
        note_text
    )

    if not note_tokens:
        return False

    description_tokens = meaningful_tokens(
        description
    )
    overlap = len(
        note_tokens
        & description_tokens
    )
    required = max(
        1,
        math.ceil(
            0.35 * len(note_tokens)
        ),
    )

    return overlap >= required


def _source_text(context: dict) -> str:
    parts = [
        str(
            context.get("raw_name", "")
        ),
        str(
            context.get("actor_name", "")
            or ""
        ),
    ]

    for field_name in (
        "notes",
        "business_rules",
        "input_documents",
        "output_documents",
    ):
        parts.extend(
            collect_texts(
                context,
                field_name,
            )
        )

    return " ".join(parts)


def validate_generated_content(
    *,
    context: dict,
    generated: GeneratedOperationContent,
) -> tuple[str, list[str], list[str]]:
    description = clean_sentence(
        generated.description
    )
    normalized_description = normalize_text(
        description
    )
    source_text = _source_text(
        context
    )
    normalized_source = normalize_text(
        source_text
    )

    for placeholder in PLACEHOLDER_PATTERNS:
        if (
            normalize_text(placeholder)
            in normalized_description
        ):
            raise ValueError(
                "The generated description contains "
                "a placeholder."
            )

    execution_mode = str(
        context.get("execution_mode", "")
    ).casefold()
    actor = effective_actor(context)

    if (
        execution_mode
        in {
            "human",
            "subprocess",
            "unknown",
        }
        and actor
        and not actor_is_preserved(
            actor,
            description,
        )
    ):
        raise ValueError(
            "The generated description does not "
            f"preserve actor {actor!r}."
        )

    if execution_mode == "automated":
        words = set(
            normalized_description.split()
        )

        if not (
            "systeme" in words
            or "si" in words
        ):
            raise ValueError(
                "An automated operation must be "
                "attributed to the system."
            )

    if execution_mode == "event":
        for timer in extract_timer_labels(
            context["raw_name"]
        ):
            if not contains_timer_label(
                description,
                timer,
            ):
                raise ValueError(
                    "The event description does not "
                    f"preserve {timer!r}."
                )

        if (
            mentions_no_response(
                context["raw_name"]
            )
            and not mentions_no_response(
                description
            )
        ):
            raise ValueError(
                "The event description does not "
                "preserve the absence of a response."
            )

    if (
        execution_mode == "subprocess"
        and not context.get("notes")
        and SUBPROCESS_EXPANSION_PATTERN.search(
            description
        )
    ):
        raise ValueError(
            "The subprocess description invents "
            "internal content."
        )

    if (
        PURPOSE_MARKER_PATTERN.search(
            description
        )
        and not PURPOSE_MARKER_PATTERN.search(
            source_text
        )
    ):
        raise ValueError(
            "The generated description adds an "
            "unsupported purpose clause."
        )

    for term in CONTROLLED_UNSUPPORTED_TERMS:
        normalized_term = normalize_text(
            term
        )

        if (
            normalized_term
            in normalized_description
            and normalized_term
            not in normalized_source
        ):
            raise ValueError(
                "The generated description adds "
                f"unsupported information: {term!r}."
            )

    raw_tokens = meaningful_tokens(
        context["raw_name"]
    )

    if raw_tokens:
        generated_tokens = meaningful_tokens(
            description
        )
        overlap = len(
            raw_tokens
            & generated_tokens
        )
        required = max(
            1,
            math.ceil(
                0.30 * len(raw_tokens)
            ),
        )

        if overlap < required:
            raise ValueError(
                "The generated description preserves "
                "too little of the operation label "
                f"({overlap}/{required})."
            )

    notes = context.get("notes", [])
    available_ids = {
        note["id"]
        for note in notes
    }
    reported_ids = list(
        dict.fromkeys(
            generated.incorporated_note_ids
        )
    )

    unknown_ids = [
        note_id
        for note_id in reported_ids
        if note_id not in available_ids
    ]

    if unknown_ids:
        raise ValueError(
            "Unknown incorporated note IDs: "
            + ", ".join(unknown_ids)
        )

    covered_ids = [
        note["id"]
        for note in notes
        if _note_is_covered(
            note["text"],
            description,
        )
    ]
    covered_id_set = set(
        covered_ids
    )

    unsupported_reported = [
        note_id
        for note_id in reported_ids
        if note_id not in covered_id_set
    ]

    if unsupported_reported:
        raise ValueError(
            "The model reported notes that are not "
            "actually covered: "
            + ", ".join(
                unsupported_reported
            )
        )

    missing_ids = [
        note["id"]
        for note in notes
        if note["id"]
        not in covered_id_set
    ]

    return (
        description,
        covered_ids,
        missing_ids,
    )


def is_structurally_resolved_ambiguity(
    context: dict,
) -> bool:
    if not context.get("order_ambiguous"):
        return False

    previous_ids = {
        item["id"]
        for item in context.get(
            "previous_operations",
            [],
        )
    }
    next_ids = {
        item["id"]
        for item in context.get(
            "next_operations",
            [],
        )
    }

    loop_target = bool(
        previous_ids
        & next_ids
    )
    terminal_convergence = (
        len(previous_ids) > 1
        and len(next_ids) == 0
    )

    return bool(
        loop_target
        or terminal_convergence
    )


def _document_name(item) -> str | None:
    if not isinstance(item, dict):
        return None

    name = item.get("name")

    if name is None:
        return None

    normalized = str(name).strip()

    return normalized or None


def build_operation_output(
    *,
    context: dict,
    description: str,
    incorporated_note_ids: list[str],
    missing_note_ids: list[str],
    fallback_used: bool,
    last_error: str | None,
) -> dict:
    unresolved_ambiguity = bool(
        context.get("order_ambiguous")
        and not is_structurally_resolved_ambiguity(
            context
        )
    )

    warnings: list[str] = []
    confidence = 0.95

    if unresolved_ambiguity:
        confidence -= 0.20
        warnings.append(
            "L’ordre de cette opération est "
            "potentiellement ambigu."
        )

    if missing_note_ids:
        confidence -= 0.10
        warnings.append(
            "Une ou plusieurs annotations associées "
            "n’ont pas été intégrées dans la description."
        )

    if fallback_used:
        confidence -= 0.15
        warnings.append(
            "Un repli déterministe a été appliqué "
            "après l’échec de la reformulation par le modèle."
        )

        if last_error:
            warnings.append(
                "Dernière erreur de génération : "
                f"{last_error}"
            )

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        ),
        2,
    )

    requires_validation = bool(
        unresolved_ambiguity
        or missing_note_ids
        or fallback_used
    )

    input_documents = list(
        context.get("input_documents", [])
        or []
    )
    output_documents = list(
        context.get("output_documents", [])
        or []
    )

    return {
        "operation_number": context[
            "operation_number"
        ],
        "bpmn_element_id": context[
            "bpmn_element_id"
        ],
        "raw_name": context[
            "raw_name"
        ],
        "actor_name": context.get(
            "actor_name"
        ),
        "element_kind": context.get(
            "element_kind"
        ),
        "source_type": context.get(
            "source_type"
        ),
        "execution_mode": context.get(
            "execution_mode"
        ),
        "event_role": context.get(
            "event_role"
        ),
        "description": description,
        "previous_operations": list(
            context.get(
                "previous_operations",
                [],
            )
        ),
        "next_operations": list(
            context.get(
                "next_operations",
                [],
            )
        ),
        "branches": list(
            context.get(
                "branches",
                [],
            )
        ),
        "input_documents": input_documents,
        "output_documents": output_documents,
        "input_document_names": [
            name
            for name in (
                _document_name(item)
                for item in input_documents
            )
            if name
        ],
        "output_document_names": [
            name
            for name in (
                _document_name(item)
                for item in output_documents
            )
            if name
        ],
        "associated_notes": list(
            context.get("notes", [])
        ),
        "business_rules": list(
            context.get(
                "business_rules",
                [],
            )
        ),
        "incorporated_note_ids": (
            incorporated_note_ids
        ),
        "missing_note_ids": (
            missing_note_ids
        ),
        "confidence": confidence,
        "requires_validation": (
            requires_validation
        ),
        "warnings": warnings,
        "validation_issue_codes": list(
            context.get(
                "validation_issue_codes",
                [],
            )
        ),
    }


def build_decisions(
    contexts: list[dict],
) -> list[dict]:
    decisions_by_key: dict[
        tuple[str, int],
        dict,
    ] = {}
    branches_by_key: defaultdict[
        tuple[str, int],
        list[dict],
    ] = defaultdict(list)

    for context in contexts:
        source_number = int(
            context["operation_number"]
        )
        source_id = str(
            context["bpmn_element_id"]
        )

        for branch in context.get(
            "branches",
            [],
        ):
            gateway_id = str(
                branch["gateway_id"]
            )
            key = (
                gateway_id,
                source_number,
            )

            decisions_by_key[key] = {
                "gateway_id": gateway_id,
                "gateway_name": branch.get(
                    "gateway_name"
                ),
                "source_operation_number": (
                    source_number
                ),
                "source_bpmn_element_id": (
                    source_id
                ),
            }
            branches_by_key[key].append(
                {
                    "label": branch.get(
                        "label"
                    ),
                    "condition": branch.get(
                        "condition"
                    ),
                    "is_default": bool(
                        branch.get(
                            "is_default",
                            False,
                        )
                    ),
                    "target_element_id": branch[
                        "target_element_id"
                    ],
                    "target_name": branch.get(
                        "target_name"
                    ),
                }
            )

    decisions: list[dict] = []

    for key in sorted(
        decisions_by_key,
        key=lambda item: (
            item[1],
            item[0],
        ),
    ):
        decision = dict(
            decisions_by_key[key]
        )
        decision["branches"] = (
            branches_by_key[key]
        )
        decisions.append(decision)

    return decisions
