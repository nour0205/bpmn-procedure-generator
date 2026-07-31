"""Kaggle CLI adapter for dataset versioning and notebook execution."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .io import copy_file, read_json, write_json
from .models import RunManifest
from .paths import AutomationPaths


class KaggleAutomationError(RuntimeError):
    """Raised when a Kaggle CLI stage fails."""


@dataclass(frozen=True, slots=True)
class KaggleSettings:
    username: str
    dataset_slug: str = "bpmn-generation-inputs"
    kernel_slug: str = "qwen-bpmn-combined-worker"
    dataset_title: str = "BPMN Generation Inputs"
    kernel_title: str = "Qwen BPMN Combined Worker"
    poll_seconds: int = 20
    timeout_seconds: int = 7200

    @property
    def dataset_ref(self) -> str:
        return f"{self.username}/{self.dataset_slug}"

    @property
    def kernel_ref(self) -> str:
        return f"{self.username}/{self.kernel_slug}"


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return "\n".join(
            part for part in (self.stdout, self.stderr) if part
        ).strip()


class KaggleCliClient:
    """Execute the stable Kaggle CLI commands used by the pipeline."""

    def __init__(self, command_prefix: list[str] | None = None) -> None:
        self.command_prefix = command_prefix or self._discover_command()

    @staticmethod
    def _discover_command() -> list[str]:
        executable = shutil.which("kaggle")
        if executable:
            return [executable]

        if importlib.util.find_spec("kaggle") is not None:
            return [sys.executable, "-m", "kaggle"]

        raise KaggleAutomationError(
            "Kaggle CLI is not installed. Run: "
            "python -m pip install --upgrade kaggle"
        )

    def run(
        self,
        *arguments: str,
        cwd: Path | None = None,
        check: bool = True,
    ) -> CommandResult:
        args = [*self.command_prefix, *arguments]
        command_environment = os.environ.copy()
        command_environment.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            }
        )

        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=command_environment,
            check=False,
        )
        result = CommandResult(
            args=tuple(args),
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )

        if check and completed.returncode != 0:
            raise KaggleAutomationError(
                "Kaggle command failed:\n"
                + " ".join(args)
                + "\n"
                + result.combined_output
            )

        return result


class KaggleGenerationService:
    """Stage, submit, monitor and download one remote generation run."""

    def __init__(
        self,
        *,
        paths: AutomationPaths,
        settings: KaggleSettings,
        notebook_path: str | Path,
        client: KaggleCliClient | None = None,
    ) -> None:
        self.paths = paths
        self.settings = settings
        self.notebook_path = Path(notebook_path)
        if not self.notebook_path.is_absolute():
            self.notebook_path = (
                paths.project_root / self.notebook_path
            )
        self.notebook_path = self.notebook_path.resolve()
        self.client = client or KaggleCliClient()

    def _load_manifest(self) -> RunManifest:
        return RunManifest.model_validate(
            read_json(self.paths.manifest_path)
        )

    def stage(self) -> RunManifest:
        """Build dataset and kernel directories consumed by Kaggle CLI."""

        manifest = self._load_manifest()

        if not self.notebook_path.exists():
            raise FileNotFoundError(
                f"Combined notebook not found: {self.notebook_path}"
            )

        self.paths.reset_directory(self.paths.dataset_stage_dir)
        self.paths.reset_directory(self.paths.kernel_stage_dir)

        for source in sorted(self.paths.input_dir.iterdir()):
            if source.is_file():
                copy_file(
                    source,
                    self.paths.dataset_stage_dir / source.name,
                )

        write_json(
            self.paths.dataset_stage_dir / "dataset-metadata.json",
            {
                "title": self.settings.dataset_title,
                "id": self.settings.dataset_ref,
                "licenses": [{"name": "CC0-1.0"}],
            },
        )

        staged_notebook = (
            self.paths.kernel_stage_dir
            / manifest.notebook_filename
        )
        copy_file(self.notebook_path, staged_notebook)

        write_json(
            self.paths.kernel_stage_dir / "kernel-metadata.json",
            {
                "id": self.settings.kernel_ref,
                "title": self.settings.kernel_title,
                "code_file": staged_notebook.name,
                "language": "python",
                "kernel_type": "notebook",
                "is_private": True,
                "enable_gpu": True,
                "enable_internet": True,
                "dataset_sources": [self.settings.dataset_ref],
                "competition_sources": [],
                "kernel_sources": [],
            },
        )

        write_json(
            self.paths.kaggle_dir / "remote_config.json",
            {
                "run_id": manifest.run_id,
                "dataset_ref": self.settings.dataset_ref,
                "kernel_ref": self.settings.kernel_ref,
                "notebook": str(self.notebook_path),
            },
        )

        return manifest

    def _dataset_exists(self) -> bool:
        result = self.client.run(
            "datasets",
            "files",
            self.settings.dataset_ref,
            check=False,
        )
        return result.returncode == 0

    def publish_inputs(self, manifest: RunManifest) -> None:
        """Create the private input dataset or publish a new version."""

        if self._dataset_exists():
            self.client.run(
                "datasets",
                "version",
                "-p",
                str(self.paths.dataset_stage_dir),
                "-m",
                f"Automated run {manifest.run_id}",
                "-r",
                "zip",
            )
        else:
            self.client.run(
                "datasets",
                "create",
                "-p",
                str(self.paths.dataset_stage_dir),
                "-r",
                "zip",
            )

    def push_kernel(self) -> None:
        """Push metadata/notebook and start a new Kaggle execution."""

        self.client.run(
            "kernels",
            "push",
            "-p",
            str(self.paths.kernel_stage_dir),
        )

    @staticmethod
    def parse_kernel_status(output: str) -> str:
        normalized = " ".join(output.casefold().split())

        for status in ("error", "failed", "cancelled"):
            if status in normalized:
                return status
        if "complete" in normalized:
            return "complete"
        if "running" in normalized:
            return "running"
        if "queued" in normalized or "pending" in normalized:
            return "queued"
        return "unknown"

    def wait_for_completion(self) -> None:
        deadline = time.monotonic() + self.settings.timeout_seconds
        last_output = ""

        while time.monotonic() < deadline:
            result = self.client.run(
                "kernels",
                "status",
                self.settings.kernel_ref,
                check=False,
            )
            last_output = result.combined_output

            if result.returncode != 0:
                time.sleep(self.settings.poll_seconds)
                continue

            status = self.parse_kernel_status(last_output)
            print(f"Kaggle status: {status}")

            if status == "complete":
                return

            if status in {"error", "failed", "cancelled"}:
                raise KaggleAutomationError(
                    "Kaggle execution did not complete successfully:\n"
                    + last_output
                )

            time.sleep(self.settings.poll_seconds)

        raise KaggleAutomationError(
            "Timed out while waiting for Kaggle execution. "
            f"Last status output:\n{last_output}"
        )

    def download_outputs(self) -> None:
        self.paths.reset_directory(self.paths.download_dir)
        self.client.run(
            "kernels",
            "output",
            self.settings.kernel_ref,
            "-p",
            str(self.paths.download_dir),
            "--force",
        )

        result_path = self.paths.download_dir / "run_result.json"
        if not result_path.exists():
            raise KaggleAutomationError(
                "Kaggle completed, but run_result.json was not downloaded."
            )

    def execute(self, *, dry_run: bool = False) -> RunManifest:
        manifest = self.stage()

        if dry_run:
            print("Dry run: Kaggle staging completed.")
            print(f"Dataset stage: {self.paths.dataset_stage_dir}")
            print(f"Kernel stage: {self.paths.kernel_stage_dir}")
            return manifest

        self.publish_inputs(manifest)
        self.push_kernel()
        time.sleep(min(5, self.settings.poll_seconds))
        self.wait_for_completion()
        self.download_outputs()
        return manifest


def username_from_environment(explicit: str | None = None) -> str:
    username = (explicit or os.environ.get("KAGGLE_USERNAME") or "").strip()
    if not username:
        raise KaggleAutomationError(
            "Kaggle username is required. Pass --kaggle-username "
            "or set KAGGLE_USERNAME."
        )
    return username
