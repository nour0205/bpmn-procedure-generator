"""Model adapter interface and Qwen/Transformers implementation."""

from __future__ import annotations

import json
from typing import Any, Protocol


class TextGenerator(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int,
    ) -> str:
        """Generate one raw text response."""


class QwenTextGenerator:
    """Thin adapter around an already-loaded Transformers model."""

    def __init__(
        self,
        *,
        model,
        tokenizer,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer

    def _apply_chat_template(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        try:
            return self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            return self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int,
    ) -> str:
        import torch

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

        prompt_text = self._apply_chat_template(messages)
        model_inputs = self.tokenizer(
            prompt_text,
            return_tensors="pt",
        )
        input_device = next(
            self.model.parameters()
        ).device
        model_inputs = {
            key: value.to(input_device)
            for key, value in model_inputs.items()
        }

        with torch.inference_mode():
            generated_ids = self.model.generate(
                **model_inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )

        new_tokens = generated_ids[
            0,
            model_inputs["input_ids"].shape[1] :,
        ]

        return self.tokenizer.decode(
            new_tokens,
            skip_special_tokens=True,
        ).strip()


def extract_json_object(
    raw_text: str,
) -> dict[str, Any]:
    cleaned = str(raw_text).strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

        if cleaned.casefold().startswith("json"):
            cleaned = cleaned[4:].strip()

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")

    if (
        first_brace == -1
        or last_brace == -1
        or last_brace < first_brace
    ):
        raise ValueError(
            "No JSON object was found in the model response."
        )

    parsed = json.loads(
        cleaned[first_brace : last_brace + 1]
    )

    if not isinstance(parsed, dict):
        raise ValueError(
            "The extracted response is not a JSON object."
        )

    return parsed
