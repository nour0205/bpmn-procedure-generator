
"""Build and export the shared document bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from document.bundle_builder import (
    DocumentBundleBuildError,
    DocumentBundleBuilder,
)
from document.loader import (
    GeneratedProcedureLoadError,
    load_generated_procedure,
)
from pipeline.service import (
    PipelineError,
    ProcedureGenerationPipeline,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Merge deterministic BPMN data with generated descriptions."
        )
    )

    parser.add_argument(
        "bpmn",
        type=Path,
        help="Path to the BPMN file.",
    )

    parser.add_argument(
        "generated",
        type=Path,
        help="Path to generated_procedure.json.",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Path to document_bundle.json.",
    )

    parser.add_argument(
        "--process-id",
        help="Optional BPMN process ID.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)

    try:
        result = ProcedureGenerationPipeline().run(
            bpmn_path=args.bpmn,
            process_id=args.process_id,
        )

        generated = load_generated_procedure(
            args.generated
        )

        bundle = DocumentBundleBuilder().build(
            procedure=result.procedure_model,
            generated=generated,
        )

    except (
        FileNotFoundError,
        PipelineError,
        GeneratedProcedureLoadError,
        DocumentBundleBuildError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            bundle.model_dump(
                mode="json",
                exclude_none=True,
                exclude_computed_fields=True,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
