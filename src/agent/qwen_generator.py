"""Qwen implementation of the operation-description generator."""

from __future__ import annotations

from typing import Any

import torch

from .json_parser import (
    LlmOutputError,
    parse_generated_content,
)
from .llm import OperationGenerator
from .models import OperationContext, OperationDraft
from .prompts import (
    SYSTEM_PROMPT,
    build_operation_prompt,
)


class QwenOperationGenerator(OperationGenerator):
    """Generate structured operation drafts with Qwen."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        *,
        max_new_tokens: int = 350,
        max_attempts: int = 2,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self.max_attempts = max_attempts

    def generate(
        self,
        context: OperationContext,
    ) -> OperationDraft:
        """Generate and validate one operation draft."""

        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            user_prompt = build_operation_prompt(context)

            if attempt > 1:
                user_prompt += (
                    "\n\nLa réponse précédente était invalide. "
                    "Retourne uniquement un objet JSON conforme au schéma."
                )

            raw_response = self._generate_text(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )

            try:
                content = parse_generated_content(
                    raw_response
                )

                self._validate_note_ids(
                    context=context,
                    note_ids=content.incorporated_note_ids,
                )

                return OperationDraft(
                    operation_number=context.operation_number,
                    bpmn_element_id=context.bpmn_element_id,
                    description=content.description,
                    input_document_names=[
                        document.name
                        for document in context.input_documents
                    ],
                    output_document_names=[
                        document.name
                        for document in context.output_documents
                    ],
                    incorporated_note_ids=(
                        content.incorporated_note_ids
                    ),
                    confidence=content.confidence,
                    requires_validation=(
                        content.requires_validation
                        or context.order_ambiguous
                    ),
                    warnings=self._merge_warnings(
                        context=context,
                        generated_warnings=content.warnings,
                    ),
                )

            except LlmOutputError as exc:
                last_error = exc

        raise LlmOutputError(
            f"Qwen failed after {self.max_attempts} attempts: "
            f"{last_error}"
        )

    def _generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]

        prompt_text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

        model_inputs = self.tokenizer(
            prompt_text,
            return_tensors="pt",
        ).to(self.model.device)

        with torch.inference_mode():
            generated_ids = self.model.generate(
                **model_inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        new_tokens = generated_ids[
            0,
            model_inputs["input_ids"].shape[1] :,
        ]

        return self.tokenizer.decode(
            new_tokens,
            skip_special_tokens=True,
        ).strip()

    @staticmethod
    def _validate_note_ids(
        context: OperationContext,
        note_ids: list[str],
    ) -> None:
        allowed_ids = {
            note.id
            for note in context.notes
        }

        invalid_ids = [
            note_id
            for note_id in note_ids
            if note_id not in allowed_ids
        ]

        if invalid_ids:
            raise LlmOutputError(
                "The model returned unknown annotation IDs: "
                + ", ".join(invalid_ids)
            )

    @staticmethod
    def _merge_warnings(
        context: OperationContext,
        generated_warnings: list[str],
    ) -> list[str]:
        warnings = list(generated_warnings)

        if context.order_ambiguous:
            order_warning = (
                "L’ordre de cette opération est potentiellement ambigu."
            )

            if order_warning not in warnings:
                warnings.append(order_warning)

        return warnings