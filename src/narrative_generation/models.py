"""Pydantic models for generated model responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RewrittenFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(min_length=1)
    sentence: str = Field(min_length=1)


class GeneratedUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentences: list[RewrittenFact] = Field(min_length=1)

    @field_validator("sentences")
    @classmethod
    def validate_unique_fact_ids(
        cls,
        sentences: list[RewrittenFact],
    ) -> list[RewrittenFact]:
        fact_ids = [item.fact_id for item in sentences]

        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("Generated fact_id values must be unique.")

        return sentences
