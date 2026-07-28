"""LLM abstraction used by the procedure agent."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import OperationContext, OperationDraft


class OperationGenerator(ABC):
    """Interface implemented by operation-description generators."""

    @abstractmethod
    def generate(
        self,
        context: OperationContext,
    ) -> OperationDraft:
        """Generate a structured draft for one operation."""


class DeterministicOperationGenerator(OperationGenerator):
    """
    Temporary generator used before connecting a real LLM.

    It creates simple descriptions deterministically and is useful for
    testing the complete agent pipeline.
    """

    def generate(
        self,
        context: OperationContext,
    ) -> OperationDraft:
        actor = context.actor_name

        if actor:
            description = (
                f"{actor} réalise l’opération suivante : "
                f"{context.raw_name}."
            )
        else:
            description = (
                f"L’opération suivante est réalisée : "
                f"{context.raw_name}."
            )

        input_document_names = [
            document.name
            for document in context.input_documents
        ]

        output_document_names = [
            document.name
            for document in context.output_documents
        ]

        warnings: list[str] = []

        requires_validation = False

        if not actor:
            warnings.append(
                "Aucun acteur responsable n’a été identifié."
            )
            requires_validation = True

        if context.order_ambiguous:
            warnings.append(
                "L’ordre de cette opération est potentiellement ambigu."
            )
            requires_validation = True

        confidence = 0.95

        if requires_validation:
            confidence = 0.65

        return OperationDraft(
            operation_number=context.operation_number,
            bpmn_element_id=context.bpmn_element_id,
            description=description,
            input_document_names=input_document_names,
            output_document_names=output_document_names,
            incorporated_note_ids=[],
            confidence=confidence,
            requires_validation=requires_validation,
            warnings=warnings,
        )