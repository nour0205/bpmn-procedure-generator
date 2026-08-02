"""Prompt construction for controlled narrative rewriting."""

from __future__ import annotations

import json


SYSTEM_PROMPT = (
    "Tu es un rédacteur fonctionnel spécialisé dans les processus BPMN.\n\n"
    "Python a déjà analysé le graphe et construit des faits fiables dans "
    "leur ordre exact. Tu ne reconstruis jamais le processus.\n\n"
    "MISSION\n\n"
    "Python injecte directement les faits structurels verrouillés. "
    "Les faits présents dans la requête sont uniquement ceux que tu "
    "dois reformuler.\n\n"
    "Pour chaque fait fourni :\n"
    "- reformule-le en français professionnel sans supprimer ni "
    "ajouter d'information ;\n"
    "- corrige uniquement les fautes d’orthographe, d’accord et de "
    "ponctuation ;\n"
    "- transforme les fragments issus des notes en phrases complètes "
    "et naturelles.\n\n"
    "RÈGLES ABSOLUES\n\n"
    "- Retourne exactement un élément par fact_id et dans le même ordre.\n"
    "- Ne fusionne et ne supprime aucun fait.\n"
    "- Ne change jamais un acteur, un canal, un document ou un scénario.\n"
    "- Une opération automatisée reste attribuée au système ou au SI.\n"
    "- Un événement reste un événement ou une communication.\n"
    "- Un sous-processus reste un sous-processus.\n"
    "- Conserve exactement les repères J+X, J+Y et tout libellé J+...\n"
    "- Ne crée aucune cause, finalité, conséquence, durée, retard, "
    "dépassement, impact, risque, bénéfice ou résultat.\n"
    "- N'ajoute aucun connecteur au début des phrases : Python les ajoute.\n"
    "- N'utilise jamais les formulations techniques « annotations "
    "associées » ou « données factuelles » dans le texte final.\n"
    "- N'utilise aucun identifiant technique, titre Markdown, liste ou "
    "commentaire.\n"
    "- Retourne uniquement l'objet JSON demandé."
)


def build_unit_prompt(
    *,
    process_title: str,
    unit: dict,
    validation_error: str | None,
) -> str:
    rewritable_facts = [
        fact
        for fact in unit["facts"]
        if not fact["locked"]
    ]

    if not rewritable_facts:
        raise ValueError(
            f"{unit['unit_id']} contains no rewritable facts."
        )

    payload = {
        "process_title": process_title,
        "unit_type": unit["unit_type"],
        "branch_label": unit.get("branch_label"),
        "facts": [
            {
                "fact_id": fact["fact_id"],
                "sentence_to_preserve_or_rewrite": fact["text"],
                "source_information": fact["source_text"],
                "actor_to_preserve": fact.get("actor"),
                "execution_mode": fact.get("execution_mode"),
            }
            for fact in rewritable_facts
        ],
    }

    correction = ""

    if validation_error:
        correction = (
            "\n\nLa tentative précédente a été rejetée :\n\n"
            f"{validation_error}\n\n"
            "Corrige uniquement cette erreur. "
            "Ne modifie pas les autres faits."
        )

    expected = {
        "sentences": [
            {
                "fact_id": fact["fact_id"],
                "sentence": "Phrase finale.",
            }
            for fact in rewritable_facts
        ]
    }

    return (
        "DONNÉES FACTUELLES\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + correction
        + "\n\nFORMAT JSON OBLIGATOIRE\n\n"
        + json.dumps(expected, ensure_ascii=False, indent=2)
    )
