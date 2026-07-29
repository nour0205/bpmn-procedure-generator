"""Prompts used by the independent procedure generator."""

from __future__ import annotations

import json


SYSTEM_PROMPT = """
Tu es un rédacteur spécialisé dans les procédures métier professionnelles
en français.

Tu reçois le contexte fiable d'une seule opération BPMN. Le graphe, les
acteurs et les métadonnées ont déjà été déterminés par Python.

Règles impératives :
- Utilise exclusivement les informations explicitement présentes.
- N'invente aucun acteur, document, système, délai, contrôle, objectif,
  justification, conséquence, paramètre, résultat ou action.
- Conserve exactement le sens de l'opération.
- Utilise l'acteur responsable comme sujet lorsqu'il est disponible.
- Pour une serviceTask, utilise « Le système » ou « Le SI » comme sujet.
- Pour un sous-processus, indique seulement qu'il est déclenché ou exécuté ;
  n'invente jamais son contenu interne.
- Pour un événement, conserve sa nature d'événement ou de jalon.
- Ne mentionne pas les branches, l'ordre, la confiance ou les avertissements
  dans la description.
- Intègre uniquement les annotations directement liées à l'opération.
- Retourne l'identifiant d'une annotation seulement lorsque son contenu est
  réellement exprimé dans la description.
- Ne déduis jamais une finalité absente du libellé, des annotations ou des
  règles métier.
- Rédige une ou deux phrases professionnelles et concises.
- Retourne uniquement un objet JSON valide, sans texte avant ou après.
""".strip()


def build_operation_prompt(
    *,
    context: dict,
    deterministic_fallback: str,
    validation_error: str | None,
) -> str:
    trusted_context = {
        "operation_number": (
            context[
                "operation_number"
            ]
        ),
        "raw_name": context[
            "raw_name"
        ],
        "actor_name": (
            context.get(
                "actor_name"
            )
        ),
        "element_kind": (
            context.get(
                "element_kind"
            )
        ),
        "source_type": (
            context.get(
                "source_type"
            )
        ),
        "execution_mode": (
            context.get(
                "execution_mode"
            )
        ),
        "event_role": (
            context.get(
                "event_role"
            )
        ),
        "notes": context.get(
            "notes",
            [],
        ),
        "business_rules": (
            context.get(
                "business_rules",
                [],
            )
        ),
        "input_documents": (
            context.get(
                "input_documents",
                [],
            )
        ),
        "output_documents": (
            context.get(
                "output_documents",
                [],
            )
        ),
    }

    expected_output = {
        "description": (
            "Description professionnelle "
            "et factuelle."
        ),
        "incorporated_note_ids": [
            "ID d'une annotation réellement intégrée"
        ],
    }

    correction = ""

    if validation_error:
        correction = (
            "\n\nLa tentative précédente a été "
            "rejetée :\n"
            f"{validation_error}\n"
            "Corrige uniquement cette erreur sans "
            "ajouter d'information."
        )

    return (
        "CONTEXTE FIABLE\n\n"
        + json.dumps(
            trusted_context,
            ensure_ascii=False,
            indent=2,
        )
        + "\n\nFORMULATION DÉTERMINISTE SÛRE\n\n"
        + deterministic_fallback
        + correction
        + "\n\nFORMAT JSON OBLIGATOIRE\n\n"
        + json.dumps(
            expected_output,
            ensure_ascii=False,
            indent=2,
        )
    )
