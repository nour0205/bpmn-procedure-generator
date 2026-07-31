"""Centralized filesystem layout for automated generation runs."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class AutomationPaths:
    """All local paths used by one process run."""

    project_root: Path
    output_root: Path
    process_slug: str

    @classmethod
    def build(
        cls,
        *,
        project_root: str | Path,
        output_root: str | Path,
        process_slug: str,
    ) -> "AutomationPaths":
        slug = process_slug.strip()
        if not _SLUG_PATTERN.fullmatch(slug):
            raise ValueError(
                "process_slug may contain only lowercase letters, "
                "numbers, underscores and hyphens."
            )

        root = Path(project_root).resolve()
        output = Path(output_root)
        if not output.is_absolute():
            output = root / output

        return cls(
            project_root=root,
            output_root=output.resolve(),
            process_slug=slug,
        )

    @property
    def process_root(self) -> Path:
        return self.output_root / self.process_slug

    @property
    def parser_dir(self) -> Path:
        return self.process_root / "parser"

    @property
    def llm_dir(self) -> Path:
        return self.process_root / "llm"

    @property
    def documents_dir(self) -> Path:
        return self.process_root / "documents"

    @property
    def run_dir(self) -> Path:
        return self.process_root / "run"

    @property
    def input_dir(self) -> Path:
        return self.run_dir / "input"

    @property
    def download_dir(self) -> Path:
        return self.run_dir / "download"

    @property
    def kaggle_dir(self) -> Path:
        return self.run_dir / "kaggle"

    @property
    def dataset_stage_dir(self) -> Path:
        return self.kaggle_dir / "dataset"

    @property
    def kernel_stage_dir(self) -> Path:
        return self.kaggle_dir / "kernel"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "run_manifest.json"

    @property
    def input_manifest_path(self) -> Path:
        return self.input_dir / "run_manifest.json"

    def ensure_base_directories(self) -> None:
        for directory in (
            self.parser_dir,
            self.llm_dir,
            self.documents_dir,
            self.run_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def reset_directory(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
