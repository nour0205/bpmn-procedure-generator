"""One-command local preparation, Kaggle execution and finalization."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .finalize import finalize_run
from .kaggle_client import (
    KaggleGenerationService,
    KaggleSettings,
    username_from_environment,
)
from .paths import AutomationPaths
from .prepare import DEFAULT_MODEL_NAME, prepare_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete BPMN -> Kaggle -> Word pipeline."
        )
    )
    parser.add_argument("bpmn", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--mode",
        choices=("procedure", "narrative", "both"),
        default="both",
    )
    parser.add_argument("--process-id", default=None)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--kaggle-username", default=None)
    parser.add_argument(
        "--dataset-slug",
        default="bpmn-generation-inputs",
    )
    parser.add_argument(
        "--kernel-slug",
        default="qwen-bpmn-combined-worker",
    )
    parser.add_argument(
        "--notebook",
        type=Path,
        default=Path(
            "notebooks/qwen-bpmn-combined-worker.ipynb"
        ),
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("templates/procedure_template.docx"),
    )
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--timeout-minutes", type=int, default=120)
    parser.add_argument("--allow-fallback", action="store_true")
    parser.add_argument("--allow-manual-review", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        username = username_from_environment(args.kaggle_username)
        manifest = prepare_run(
            bpmn_path=args.bpmn,
            process_slug=args.slug,
            mode=args.mode,
            project_root=args.project_root,
            output_root=args.output_root,
            process_id=args.process_id,
            model_name=args.model_name,
            allow_dirty=args.allow_dirty,
        )
        print("Preparation: PASSED")
        print(f"Run ID: {manifest.run_id}")

        paths = AutomationPaths.build(
            project_root=args.project_root,
            output_root=args.output_root,
            process_slug=args.slug,
        )
        service = KaggleGenerationService(
            paths=paths,
            settings=KaggleSettings(
                username=username,
                dataset_slug=args.dataset_slug,
                kernel_slug=args.kernel_slug,
                poll_seconds=max(5, args.poll_seconds),
                timeout_seconds=max(60, args.timeout_minutes * 60),
            ),
            notebook_path=args.notebook,
        )
        service.execute()
        print("Kaggle execution: PASSED")

        report = finalize_run(
            process_slug=args.slug,
            project_root=args.project_root,
            output_root=args.output_root,
            template_path=args.template,
            process_id=args.process_id,
            allow_fallback=args.allow_fallback,
            allow_manual_review=args.allow_manual_review,
            generate_documents=True,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("Final status: FAILED", file=sys.stderr)
        return 1

    print(f"Procedure validation: {report.procedure_validation}")
    print(f"Narrative validation: {report.narrative_validation}")
    print(f"Word generation: {report.word_generation}")
    print("Final status: SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
