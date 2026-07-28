"""CLI for generating the specification DOCX."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .models import DocumentBundle
from .narrative_loader import (
    NarrativeLoadError,
    load_generated_narrative,
)
from .specification_generator import (
    SpecificationDocumentGenerator,
    SpecificationGenerationError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a specification DOCX from a "
            "DocumentBundle and generated narrative."
        )
    )

    parser.add_argument(
        "bundle_path",
        type=Path,
        help="Path to document_bundle.json",
    )

    parser.add_argument(
        "narrative_path",
        type=Path,
        help="Path to generated_narrative.json",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for the specification DOCX",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        raw_bundle = json.loads(
            args.bundle_path.read_text(
                encoding="utf-8"
            )
        )

        bundle = DocumentBundle.model_validate(
            raw_bundle
        )

        narrative = load_generated_narrative(
            args.narrative_path
        )

        output = (
            SpecificationDocumentGenerator()
            .generate(
                bundle=bundle,
                narrative=narrative,
                output_path=args.output,
            )
        )

    except FileNotFoundError as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    except (
        json.JSONDecodeError,
        ValidationError,
        NarrativeLoadError,
        SpecificationGenerationError,
        ValueError,
    ) as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Written: {output}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )