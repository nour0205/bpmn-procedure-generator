"""CLI for generating the procedure DOCX from a DocumentBundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .models import DocumentBundle
from .procedure_generator import (
    ProcedureDocumentGenerator,
    ProcedureGenerationError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a procedure DOCX from a DocumentBundle and a template."
        )
    )

    parser.add_argument(
        "bundle_path",
        type=Path,
        help="Path to document_bundle.json",
    )
    parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to the procedure DOCX template",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for the generated procedure DOCX",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        raw_bundle = json.loads(
            args.bundle_path.read_text(encoding="utf-8")
        )
        bundle = DocumentBundle.model_validate(raw_bundle)

        output = ProcedureDocumentGenerator().generate(
            bundle=bundle,
            template_path=args.template,
            output_path=args.output,
        )

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"Error: cannot access file: {exc}", file=sys.stderr)
        return 1
    except (
        json.JSONDecodeError,
        ValidationError,
        ProcedureGenerationError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
