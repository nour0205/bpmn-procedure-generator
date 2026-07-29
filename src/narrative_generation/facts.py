"""Build grounded narrative facts from deterministic BPMN data."""

from __future__ import annotations

import re

from narrative_generation.text import (
    clean_sentence,
    collect_texts,
    extract_timer_labels,
    lowercase_first_letter,
    meaningful_tokens,
    mentions_no_response,
    normalize_text,
)


def deterministic_event_sentence(operation: dict) -> str:
    raw_name = str(operation.get("raw_name", "")).strip()
    normalized_name = normalize_text(raw_name)

    timers = extract_timer_labels(raw_name)
    timer = timers[0] if timers else None

    if timer and mentions_no_response(raw_name):
        supplier = (
            " du Fournisseur"
            if "fournisseur" in normalized_name
            else ""
        )

        return clean_sentence(
            f"À l’événement « {timer} », "
            f"aucune réponse{supplier} n’a été reçue"
        )

    if (
        "communication d une nouvelle date de reception"
        in normalized_name
        and "fournisseur" in normalized_name
    ):
        channel = (
            " sur le portail"
            if "portail" in normalized_name
            else ""
        )

        return clean_sentence(
            "Une nouvelle date de réception est communiquée "
            f"par le Fournisseur{channel}"
        )

    if timer:
        return clean_sentence(
            f"Le processus atteint le repère temporel « {timer} »"
        )

    event_role = str(operation.get("event_role", "")).casefold()

    if event_role == "start":
        return clean_sentence(
            f"L’événement « {raw_name} » déclenche le processus"
        )

    if event_role == "end":
        return clean_sentence(
            f"L’événement « {raw_name} » marque la fin "
            "explicitement modélisée du processus"
        )

    return clean_sentence(
        f"L’événement « {raw_name} » intervient "
        "dans le déroulement du processus"
    )



def subject_phrase(actor: str) -> str:
    cleaned = " ".join(str(actor).split()).strip()

    if not cleaned:
        return ""

    normalized = normalize_text(cleaned)

    if normalized.startswith(
        (
            "le ",
            "la ",
            "les ",
            "l ",
            "un ",
            "une ",
            "des ",
        )
    ):
        return cleaned

    if cleaned.startswith("Direction "):
        return f"La {cleaned}"

    if cleaned.startswith("Unité "):
        return f"L’{cleaned}"

    if cleaned.startswith("Service "):
        return f"Le {cleaned}"

    if cleaned == "CME":
        return "La CME"

    return cleaned

def deterministic_operation_sentence(operation: dict) -> str:
    raw_name = str(operation.get("raw_name", "")).strip()
    actor = subject_phrase(
        str(operation.get("actor", "") or "")
    )
    execution_mode = str(
        operation.get("execution_mode", "")
    ).casefold()

    if execution_mode == "event":
        return deterministic_event_sentence(operation)

    if execution_mode == "automated":
        return clean_sentence(
            f"Le système exécute automatiquement "
            f"l’activité « {raw_name} »"
        )

    if execution_mode == "subprocess":
        if actor:
            return clean_sentence(
                f"{actor} déclenche le sous-processus "
                f"« {raw_name} »"
            )

        return clean_sentence(
            f"Le flux atteint le sous-processus « {raw_name} »"
        )

    if actor:
        return clean_sentence(
            f"{actor} réalise l’activité « {raw_name} »"
        )

    return clean_sentence(
        f"L’activité « {raw_name} » est exécutée"
    )


def operation_source_text(operation: dict) -> str:
    parts = [
        str(operation.get("raw_name", "")),
        str(operation.get("actor", "") or ""),
        str(operation.get("execution_mode", "")),
    ]

    for field_name in (
        "notes",
        "business_rules",
        "input_documents",
        "output_documents",
    ):
        parts.extend(collect_texts(operation, field_name))

    return " ".join(parts)


def integrate_notes_naturally(
    base_sentence: str,
    notes: list[str],
) -> str:
    base = clean_sentence(base_sentence).rstrip(".")
    sentences: list[str] = [base]

    for note in notes:
        raw_note = " ".join(str(note).split()).strip().rstrip(".")

        if not raw_note:
            continue

        on_basis_match = re.match(
            r"^(Sur la base d['’]un|Sur la base de|"
            r"À partir de|Selon)\b",
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

        if on_basis_match and len(sentences) == 1:
            sentences[0] += " " + lowercase_first_letter(raw_note)
        elif possible_match:
            sentences.append(
                "Cette activité permet de "
                + lowercase_first_letter(possible_match.group(1))
            )
        elif additional_match:
            sentences.append(
                "Elle permet également de "
                + lowercase_first_letter(additional_match.group(1))
            )
        else:
            sentences.append(raw_note)

    return " ".join(clean_sentence(sentence) for sentence in sentences)


def new_fact(
    *,
    fact_id: str,
    kind: str,
    text: str,
    locked: bool,
    source_text: str,
    operation: dict | None = None,
) -> dict:
    fact = {
        "fact_id": fact_id,
        "kind": kind,
        "text": clean_sentence(text),
        "locked": bool(locked),
        "operation_number": None,
        "actor": None,
        "execution_mode": None,
        "timer_labels": extract_timer_labels(text),
        "required_tokens": sorted(meaningful_tokens(source_text)),
        "source_text": source_text,
        "allow_purpose_clause": bool(
            collect_texts(operation or {}, "notes")
            or collect_texts(operation or {}, "business_rules")
        ),
    }

    if operation is not None:
        fact["operation_number"] = int(operation["number"])
        fact["actor"] = operation.get("actor")
        fact["execution_mode"] = operation.get("execution_mode")

    return fact


def operation_fact(operation: dict) -> dict:
    number = int(operation["number"])

    if str(
        operation.get("execution_mode", "")
    ).casefold() == "event":
        return new_fact(
            fact_id=f"op_{number}",
            kind="event",
            text=deterministic_event_sentence(operation),
            locked=True,
            source_text=operation_source_text(operation),
            operation=operation,
        )

    sentence = deterministic_operation_sentence(operation)

    notes = collect_texts(operation, "notes")
    rules = collect_texts(operation, "business_rules")
    inputs = collect_texts(operation, "input_documents")
    outputs = collect_texts(operation, "output_documents")

    sentence = integrate_notes_naturally(sentence, notes)

    extra_sentences: list[str] = []

    for rule in rules:
        extra_sentences.append(
            "La règle métier associée précise que "
            + lowercase_first_letter(rule)
        )

    if inputs:
        extra_sentences.append(
            "Les documents utilisés en entrée sont : "
            + ", ".join(inputs)
        )

    if outputs:
        extra_sentences.append(
            "Les documents produits sont : "
            + ", ".join(outputs)
        )

    if extra_sentences:
        sentence += " " + " ".join(
            clean_sentence(item)
            for item in extra_sentences
        )

    return new_fact(
        fact_id=f"op_{number}",
        kind="operation",
        text=sentence,
        locked=False,
        source_text=operation_source_text(operation),
        operation=operation,
    )
