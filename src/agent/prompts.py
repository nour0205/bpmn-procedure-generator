
"""Prompts used by the procedure-generation agent."""

from __future__ import annotations

import json

from .models import OperationContext


SYSTEM_PROMPT = """
Tu es un assistant spécialisé dans la rédaction de procédures métier
professionnelles en français.

Tu reçois le contexte structuré d'une seule opération issue d'un processus
BPMN déjà analysé et validé.

Règles impératives :
- Utilise uniquement les informations présentes dans le contexte.
- N'invente aucun acteur, document, système, contrôle, délai ou action.
- Conserve exactement le sens de l'opération BPMN.
- Utilise l'acteur responsable comme sujet lorsqu'il est disponible.
- Intègre les annotations pertinentes dans la description.
- Ne transforme pas une annotation en information certaine si elle est ambiguë.
- Ne formule aucune recommandation.
- Ne mentionne pas les termes techniques BPMN.
- Produis une description professionnelle, claire et concise.
- Retourne uniquement un objet JSON valide.
- N'ajoute aucun texte avant ou après le JSON.
""".strip()


def build_operation_prompt(
    context: OperationContext,
) -> str:
    context_json = json.dumps(
        context.model_dump(
            mode="json",
            exclude_none=True,
        ),
        ensure_ascii=False,
        indent=2,
    )

    expected_schema = {
        "description": "Description professionnelle en français.",
        "incorporated_note_ids": [
            "Identifiants exacts des annotations réellement utilisées."
        ],
        "confidence": 0.0,
        "requires_validation": False,
        "warnings": [],
    }

    return f"""
Rédige la description de l'opération ci-dessous.

CONTEXTE FIABLE :
{context_json}

FORMAT JSON ATTENDU :
{json.dumps(expected_schema, ensure_ascii=False, indent=2)}

Consignes supplémentaires :
- La description doit généralement contenir une ou deux phrases.
- Ne copie pas la formulation générique « réalise l'opération suivante ».
- Reformule l'action naturellement.
- Si l'élément est un sous-processus, indique que l'acteur exécute ou déclenche
  le sous-processus, sans inventer son contenu interne.
- Si l'élément est un événement métier, décris le jalon métier naturellement.
- Si l'ordre est ambigu, ne tente pas de résoudre l'ambiguïté : ajoute un
  avertissement et positionne requires_validation à true.
- Les valeurs de incorporated_note_ids doivent obligatoirement provenir de
  context.notes.
""".strip()
