"""Generate the complete Word deliverables in one validated command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from document.bundle_builder import (
    DocumentBundleBuildError,
    DocumentBundleBuilder,
)
from document.loader import (
    GeneratedProcedureLoadError,
    load_generated_procedure,
)
from document.narrative_loader import (
    NarrativeLoadError,
    load_generated_narrative,
)
from document.procedure_generator import (
    ProcedureDocumentGenerator,
    ProcedureGenerationError,
)
from document.specification_generator import (
    SpecificationDocumentGenerator,
    SpecificationGenerationError,
)
from pipeline.service import PipelineError, ProcedureGenerationPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate BPMN/LLM outputs and generate the procedure and "
            "specification Word documents."
        )
    )

    parser.add_argument("bpmn", type=Path, help="Path to the BPMN file")
    parser.add_argument(
        "generated_procedure",
        type=Path,
        help="Path to generated_procedure.json",
    )
    parser.add_argument(
        "generated_narrative",
        type=Path,
        help="Path to generated_narrative.json",
    )
    parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to the procedure DOCX template",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory receiving the bundle and both DOCX files",
    )
    parser.add_argument(
        "--process-id",
        default=None,
        help="Optional BPMN process ID",
    )
    parser.add_argument(
        "--procedure-name",
        default="procedure.docx",
        help="Procedure output filename",
    )
    parser.add_argument(
        "--specification-name",
        default="specification.docx",
        help="Specification output filename",
    )

    return parser


def apply_narrative_process_title(
    *,
    bundle,
    generated_narrative,
):
    """
    Use the narrative process title consistently in both Word documents.
    """

    process_title = str(
        generated_narrative.process_title
    ).strip()

    if not process_title:
        raise ValueError(
            "The generated narrative has an empty process title."
        )

    metadata = bundle.metadata
    metadata_fields = type(metadata).model_fields

    if "title" not in metadata_fields:
        available_fields = ", ".join(
            metadata_fields
        )

        raise ValueError(
            "The bundle metadata has no title field. "
            f"Available fields: {available_fields}"
        )

    updated_metadata = metadata.model_copy(
        update={
            "title": process_title,
        }
    )

    return bundle.model_copy(
        update={
            "metadata": updated_metadata,
        }
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        pipeline_result = ProcedureGenerationPipeline().run(
            bpmn_path=args.bpmn,
            process_id=args.process_id,
        )
        generated_procedure = load_generated_procedure(
            args.generated_procedure
        )
        generated_narrative = load_generated_narrative(
            args.generated_narrative
        )

        bundle = DocumentBundleBuilder().build(
            procedure=pipeline_result.procedure_model,
            generated=generated_procedure,
        )

        if bundle.metadata.process_id != generated_narrative.process_id:
            raise ValueError(
                "The generated procedure and narrative use different "
                "process IDs."
            )

        bundle = apply_narrative_process_title(
            bundle=bundle,
            generated_narrative=generated_narrative,
        )

        args.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        bundle_path = args.output_dir / "document_bundle.json"
        procedure_path = args.output_dir / args.procedure_name
        specification_path = args.output_dir / args.specification_name

        bundle_path.write_text(
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

        ProcedureDocumentGenerator().generate(
            bundle=bundle,
            template_path=args.template,
            output_path=procedure_path,
        )
        SpecificationDocumentGenerator().generate(
            bundle=bundle,
            narrative=generated_narrative,
            output_path=specification_path,
        )

    except (
        FileNotFoundError,
        PermissionError,
        PipelineError,
        GeneratedProcedureLoadError,
        NarrativeLoadError,
        DocumentBundleBuildError,
        ProcedureGenerationError,
        SpecificationGenerationError,
        ValidationError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Written: {bundle_path}")
    print(f"Written: {procedure_path}")
    print(f"Written: {specification_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
