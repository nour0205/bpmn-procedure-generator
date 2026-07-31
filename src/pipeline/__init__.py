"""End-to-end BPMN generation and Kaggle automation package.

Legacy pipeline classes are loaded lazily so lightweight automation modules
can be imported without initializing the BPMN parser immediately.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "PipelineError",
    "ProcedureGenerationPipeline",
    "ProcedureGenerationResult",
]


def __getattr__(name: str):
    if name in __all__:
        service = import_module("pipeline.service")
        return getattr(service, name)
    raise AttributeError(name)
