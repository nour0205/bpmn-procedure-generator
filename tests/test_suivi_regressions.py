from __future__ import annotations

from pathlib import Path

from agent.context_builder import OperationContextBuilder
from bpmn.parser import BpmnParser
from document.narrative_context import NarrativeContextBuilder
from document.narrative_plan_builder import NarrativePlanBuilder
from document.text_normalization import (
    normalize_french_business_text,
    symbolic_delay_labels,
)
from narrative_generation.units import build_narrative_units
from procedure.mapper import ProcedureMapper


def _suivi_path() -> Path:
    candidates = (
        Path("bpmn_files") / "Suivi des commandes.bpmn",
        Path("Suivi des commandes.bpmn"),
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Suivi des commandes.bpmn")


def _procedure():
    model = BpmnParser().parse_file(_suivi_path())
    process_id = next(
        process.id
        for process in model.processes
        if any(
            node.process_id == process.id
            for node in model.flow_nodes
        )
    )
    return ProcedureMapper().map_process(model, process_id)


def test_structured_order_and_semantic_actors() -> None:
    procedure = _procedure()

    assert [
        operation.raw_name
        for operation in procedure.operations
    ] == [
        "Lancement des commandes",
        "J+X",
        "Relancer le Fournisseur sur le portail et par téléphone",
        "J+Y sans réponse du Fournisseur",
        "Générer les lettres de relance",
        "Valider la lettre de relance",
        "Transmettre la lettre de relance au Fournisseur via le portail et par mail",
        "Communication d'une nouvelle date de réception de la part du Fournisseur sur le portail",
        "Mettre à jour le planning de livraisons prévues",
        "Génération d'un reporting des commandes en cours",
        "Gestion des réceptions",
    ]

    actor_by_name = {
        operation.raw_name: operation.actor_name
        for operation in procedure.operations
    }

    assert actor_by_name["J+X"] == "Événement temporel"
    assert (
        actor_by_name["J+Y sans réponse du Fournisseur"]
        == "Événement temporel"
    )
    assert (
        actor_by_name[
            "Génération d'un reporting des commandes en cours"
        ]
        == "Système d'information"
    )
    assert (
        actor_by_name[
            "Communication d'une nouvelle date de réception de la part du Fournisseur sur le portail"
        ]
        == "Fournisseur"
    )


def test_validation_rejection_is_explicit_loop_back() -> None:
    procedure = _procedure()
    validation = next(
        operation
        for operation in procedure.operations
        if operation.raw_name == "Valider la lettre de relance"
    )

    branches = {
        str(branch.label).casefold(): branch
        for branch in validation.branches
    }

    assert branches["oui"].is_loop_back is False
    assert branches["non"].is_loop_back is True

    target = next(
        operation
        for operation in procedure.operations
        if operation.bpmn_element_id
        == branches["non"].target_element_id
    )
    assert target.raw_name == "Générer les lettres de relance"
    assert target.is_common_continuation is False
    assert target.convergence_gateway_ids == []


def test_nested_validation_is_written_before_sibling_non_branch() -> None:
    procedure = _procedure()
    contexts = OperationContextBuilder().build_all(procedure)
    payload = {
        "process_id": procedure.metadata.process_id,
        "title": procedure.metadata.title,
        "contexts": [
            context.model_dump(mode="json", exclude_none=True)
            for context in contexts
        ],
    }
    narrative_context = NarrativeContextBuilder().build(
        payload,
        default_process_id=procedure.metadata.process_id,
        default_process_title=procedure.metadata.title,
    )
    plan = NarrativePlanBuilder().build(narrative_context)
    units, coverage, warnings = build_narrative_units(
        plan.model_dump(mode="json")
    )

    ids = [unit["unit_id"] for unit in units]
    assert ids.index("block_2_decision") < ids.index(
        "block_1_branch_2"
    )
    assert coverage["missing_operation_numbers"] == []
    assert coverage["duplicated_operation_numbers"] == []
    assert warnings == []


def test_french_normalization_and_symbolic_delays() -> None:
    text = normalize_french_business_text(
        "Sur la base d'un modèle pré-définis pour les pdts."
    )

    assert text == (
        "Sur la base d'un modèle prédéfini pour les produits."
    )
    assert symbolic_delay_labels("J+X puis J+Y") == ["J+X", "J+Y"]
