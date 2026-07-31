# Automated BPMN → Kaggle → Word pipeline

This package removes the manual upload/download steps while keeping procedure
and narrative generation independent. The combined Kaggle worker loads Qwen
once and follows the `generation_mode` in `run_manifest.json`:

- `procedure`
- `narrative`
- `both`

## Files added

```text
src/pipeline/
├── models.py
├── paths.py
├── io.py
├── prepare.py
├── kaggle_client.py
├── kaggle_run.py
├── finalize.py
└── full_run.py

notebooks/qwen-bpmn-combined-worker.ipynb
kaggle/dataset-metadata.template.json
kaggle/kernel-metadata.template.json
tests/test_pipeline_automation.py
requirements-automation.txt
```

## 1. Install the Kaggle CLI

```powershell
python -m pip install --upgrade -r requirements-automation.txt
kaggle --version
```

Authenticate the installed Kaggle CLI using the authentication method shown by
that CLI version. Keep credentials outside Git. The automation accepts the
Kaggle username through `--kaggle-username` or `KAGGLE_USERNAME`.

For example in the current PowerShell session:

```powershell
$env:KAGGLE_USERNAME="your-kaggle-username"
```

The GitHub repository must be public, or the Kaggle account must contain a
secret named `GITHUB_TOKEN`. `HF_TOKEN` is optional while the selected model is
public.

## 2. Test deterministic preparation

```powershell
$env:PYTHONPATH="$PWD\src"

python -m pipeline.prepare `
  "bpmn_files\Suivi des commandes.bpmn" `
  --slug "suivi_commandes" `
  --mode both
```

This writes:

```text
output/suivi_commandes/
├── parser/
│   ├── bpmn_model.json
│   ├── procedure_model.json
│   ├── operation_contexts.json
│   ├── narrative_context.json
│   └── narrative_plan.json
└── run/
    ├── input/
    │   ├── operation_contexts.json
    │   ├── narrative_plan.json
    │   └── run_manifest.json
    └── run_manifest.json
```

For `--mode procedure`, the narrative files are not required or uploaded.

## 3. Test Kaggle staging without submitting

```powershell
python -m pipeline.kaggle_run `
  --slug "suivi_commandes" `
  --kaggle-username "$env:KAGGLE_USERNAME" `
  --dry-run
```

Inspect:

```text
output/suivi_commandes/run/kaggle/dataset/
output/suivi_commandes/run/kaggle/kernel/
```

## 4. Execute Kaggle automatically

```powershell
python -m pipeline.kaggle_run `
  --slug "suivi_commandes" `
  --kaggle-username "$env:KAGGLE_USERNAME"
```

The first run creates a private input dataset and the private GPU kernel. Later
runs publish a new dataset version, push the worker, poll its status and place
outputs under:

```text
output/suivi_commandes/run/download/
```

## 5. Validate and generate documents

```powershell
python -m pipeline.finalize `
  --slug "suivi_commandes" `
  --template "templates\procedure_template.docx"
```

Strict finalization rejects:

- stale `run_id` or mismatched `process_id`;
- missing/unknown/duplicated operations;
- placeholders or missing notes;
- fallbacks;
- outputs requiring manual review.

Use `--allow-fallback` or `--allow-manual-review` only for an intentional review
run. Word documents are generated only in `both` mode.

## 6. One-command execution

```powershell
python -m pipeline.full_run `
  "bpmn_files\Suivi des commandes.bpmn" `
  --slug "suivi_commandes" `
  --mode both `
  --kaggle-username "$env:KAGGLE_USERNAME"
```

Expected stages:

```text
Preparation: PASSED
Kaggle execution: PASSED
Procedure validation: passed
Narrative validation: passed
Word generation: passed
Final status: SUCCESS
```

## Important operational behavior

Procedure and narrative do not consume each other's outputs. In `both` mode,
the worker catches generation errors independently and writes both statuses to
`run_result.json`. Local finalization accepts only the components requested by
the manifest.

The local Kaggle adapter uses the standard CLI operations for dataset
create/version, kernel push/status and kernel output. A real Kaggle-account run
is still required because this package was built without access to the user's
credentials or GPU account.
