"""Validate downloaded Kaggle outputs and generate local deliverables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .io import copy_file, read_json, write_json
from .models import (
    FinalizationReport,
    RunManifest,
    WorkerRunResult,
)
from .paths import AutomationPaths


class FinalizationError(RuntimeError):
    """Raised when a downloaded run is stale, invalid or incomplete."""


def _require_empty(report: dict[str, Any], key: str) -> None:
    value = report.get(key)
    if value not in (None, []):
        raise FinalizationError(f"{key} must be empty; got {value!r}.")


def _require_zero(report: dict[str, Any], key: str) -> None:
    value = report.get(key, 0)
    if value != 0:
        raise FinalizationError(f"{key} must be 0; got {value!r}.")


def validate_worker_identity(
    manifest: RunManifest,
    result: WorkerRunResult,
) -> None:
    mismatches: list[str] = []

    for field in (
        "run_id",
        "generation_mode",
        "process_slug",
        "process_id",
        "process_title",
        "model_name",
    ):
        expected = getattr(manifest, field)
        actual = getattr(result, field)
        if expected != actual:
            mismatches.append(
                f"{field}: expected {expected!r}, got {actual!r}"
            )

    if manifest.git_commit and result.git_commit:
        if manifest.git_commit != result.git_commit:
            mismatches.append(
                "git_commit: expected "
                f"{manifest.git_commit!r}, got {result.git_commit!r}"
            )

    if mismatches:
        raise FinalizationError(
            "Downloaded output does not belong to the prepared run:\n- "
            + "\n- ".join(mismatches)
        )


def _validate_requested_statuses(
    manifest: RunManifest,
    result: WorkerRunResult,
) -> None:
    if manifest.generation_mode in {"procedure", "both"}:
        if result.procedure.status != "success":
            raise FinalizationError(
                "Procedure generation failed: "
                + str(result.procedure.error_message)
            )

    if manifest.generation_mode in {"narrative", "both"}:
        if result.narrative.status != "success":
            raise FinalizationError(
                "Narrative generation failed: "
                + str(result.narrative.error_message)
            )


def _validate_procedure_report(
    report: dict[str, Any],
    *,
    allow_fallback: bool,
    allow_manual_review: bool,
) -> None:
    _require_empty(report, "missing_operation_numbers")
    _require_empty(report, "unknown_operation_numbers")
    _require_zero(report, "placeholder_count")
    _require_zero(report, "missing_note_count")

    if not allow_fallback:
        _require_empty(report, "fallback_operations")

    if not allow_manual_review:
        _require_empty(report, "operations_requiring_validation")
        if report.get("manual_review_required") is not False:
            raise FinalizationError(
                "Procedure report requires manual review."
            )


def _validate_narrative_report(
    report: dict[str, Any],
    *,
    allow_fallback: bool,
    allow_manual_review: bool,
) -> None:
    coverage = report.get("coverage_summary")
    if not isinstance(coverage, dict):
        raise FinalizationError(
            "Narrative report has no valid coverage_summary."
        )

    _require_empty(coverage, "missing_operation_numbers")
    _require_empty(coverage, "duplicated_operation_numbers")
    _require_zero(report, "placeholder_count")

    if not allow_fallback:
        _require_empty(report, "fallback_units")

    if not allow_manual_review:
        if report.get("manual_review_required") is not False:
            raise FinalizationError(
                "Narrative report requires manual review."
            )


def finalize_run(
    *,
    process_slug: str,
    project_root: str | Path = ".",
    output_root: str | Path = "output",
    template_path: str | Path = "templates/procedure_template.docx",
    process_id: str | None = None,
    allow_fallback: bool = False,
    allow_manual_review: bool = False,
    generate_documents: bool = True,
) -> FinalizationReport:
    paths = AutomationPaths.build(
        project_root=project_root,
        output_root=output_root,
        process_slug=process_slug,
    )

    manifest = RunManifest.model_validate(
        read_json(paths.manifest_path)
    )
    worker_result = WorkerRunResult.model_validate(
        read_json(paths.download_dir / "run_result.json")
    )

    validate_worker_identity(manifest, worker_result)
    _validate_requested_statuses(manifest, worker_result)

    copied_files: list[str] = []
    generated_documents: list[str] = []
    procedure_validation = "skipped"
    narrative_validation = "skipped"

    generated_procedure_path = (
        paths.download_dir / "generated_procedure.json"
    )
    generated_narrative_path = (
        paths.download_dir / "generated_narrative.json"
    )

    if manifest.generation_mode in {"procedure", "both"}:
        from document.loader import load_generated_procedure

        procedure_report_path = (
            paths.download_dir / "procedure_validation_report.json"
        )
        procedure_report = read_json(procedure_report_path)
        _validate_procedure_report(
            procedure_report,
            allow_fallback=allow_fallback,
            allow_manual_review=allow_manual_review,
        )
        generated_procedure = load_generated_procedure(
            generated_procedure_path
        )
        if generated_procedure.process_id != manifest.process_id:
            raise FinalizationError(
                "Generated procedure process_id does not match manifest."
            )
        procedure_validation = "passed"

    if manifest.generation_mode in {"narrative", "both"}:
        from document.narrative_loader import load_generated_narrative

        narrative_report_path = (
            paths.download_dir / "narrative_validation_report.json"
        )
        narrative_report = read_json(narrative_report_path)
        _validate_narrative_report(
            narrative_report,
            allow_fallback=allow_fallback,
            allow_manual_review=allow_manual_review,
        )
        generated_narrative = load_generated_narrative(
            generated_narrative_path
        )
        if generated_narrative.process_id != manifest.process_id:
            raise FinalizationError(
                "Generated narrative process_id does not match manifest."
            )
        narrative_validation = "passed"

    paths.llm_dir.mkdir(parents=True, exist_ok=True)
    for filename in manifest.expected_outputs:
        source = paths.download_dir / filename
        if source.exists():
            target = paths.llm_dir / filename
            copy_file(source, target)
            copied_files.append(str(target))

    word_generation = "skipped"
    if generate_documents and manifest.generation_mode == "both":
        from document.word_cli import main as word_main

        template = Path(template_path)
        if not template.is_absolute():
            template = paths.project_root / template

        bpmn = Path(manifest.bpmn_path)
        if not bpmn.exists():
            fallback_bpmn = paths.project_root / "bpmn_files" / manifest.bpmn_filename
            if fallback_bpmn.exists():
                bpmn = fallback_bpmn

        args = [
            str(bpmn),
            str(paths.llm_dir / "generated_procedure.json"),
            str(paths.llm_dir / "generated_narrative.json"),
            "--template",
            str(template),
            "--output-dir",
            str(paths.documents_dir),
        ]
        effective_process_id = process_id or manifest.process_id
        if effective_process_id:
            args.extend(["--process-id", effective_process_id])

        exit_code = word_main(args)
        if exit_code != 0:
            raise FinalizationError(
                "Word generation failed. See the error printed above."
            )

        for name in (
            "document_bundle.json",
            "procedure.docx",
            "specification.docx",
        ):
            path = paths.documents_dir / name
            if not path.exists():
                raise FinalizationError(
                    f"Expected document was not generated: {path}"
                )
            generated_documents.append(str(path))

        word_generation = "passed"

    report = FinalizationReport(
        run_id=manifest.run_id,
        process_slug=manifest.process_slug,
        process_id=manifest.process_id,
        process_title=manifest.process_title,
        generation_mode=manifest.generation_mode,
        procedure_validation=procedure_validation,
        narrative_validation=narrative_validation,
        word_generation=word_generation,
        copied_files=copied_files,
        generated_documents=generated_documents,
        final_status="success",
    )

    write_json(
        paths.run_dir / "finalization_report.json",
        report.model_dump(mode="json"),
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate downloaded Kaggle outputs, copy accepted files "
            "and generate Word deliverables."
        )
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("templates/procedure_template.docx"),
    )
    parser.add_argument("--process-id", default=None)
    parser.add_argument("--allow-fallback", action="store_true")
    parser.add_argument("--allow-manual-review", action="store_true")
    parser.add_argument("--skip-documents", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        report = finalize_run(
            process_slug=args.slug,
            project_root=args.project_root,
            output_root=args.output_root,
            template_path=args.template,
            process_id=args.process_id,
            allow_fallback=args.allow_fallback,
            allow_manual_review=args.allow_manual_review,
            generate_documents=not args.skip_documents,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Process: {report.process_title}")
    print(f"Run ID: {report.run_id}")
    print(f"Procedure validation: {report.procedure_validation}")
    print(f"Narrative validation: {report.narrative_validation}")
    print(f"Word generation: {report.word_generation}")
    print("Final status: SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
