"""Orchestration of operation-by-operation procedure generation."""

from __future__ import annotations

from procedure.models import ProcedureModel

from .context_builder import OperationContextBuilder
from .llm import OperationGenerator
from .models import (
    OperationDraft,
    ProcedureDraft,
)


class ProcedureAgent:
    """Generate a complete structured procedure draft."""

    def __init__(
        self,
        generator: OperationGenerator,
        context_builder: OperationContextBuilder | None = None,
    ) -> None:
        self.generator = generator
        self.context_builder = (
            context_builder
            or OperationContextBuilder()
        )

    def generate(
        self,
        procedure: ProcedureModel,
    ) -> ProcedureDraft:
        """Generate one draft per procedure operation."""

        contexts = self.context_builder.build_all(
            procedure
        )

        generated_operations: list[OperationDraft] = []
        generation_warnings: list[str] = []

        for context in contexts:
            try:
                draft = self.generator.generate(context)
            except Exception as exc:
                draft = OperationDraft(
                    operation_number=context.operation_number,
                    bpmn_element_id=context.bpmn_element_id,
                    description=context.raw_name,
                    confidence=0.0,
                    requires_validation=True,
                    warnings=[
                        (
                            "La génération de la description a échoué : "
                            f"{exc}"
                        )
                    ],
                )

                generation_warnings.append(
                    (
                        "Échec de génération pour l’opération "
                        f"{context.operation_number} "
                        f"({context.bpmn_element_id})."
                    )
                )

            generated_operations.append(draft)

        return ProcedureDraft(
            process_id=procedure.metadata.process_id,
            title=procedure.metadata.title,
            operations=generated_operations,
            generation_warnings=generation_warnings,
        )