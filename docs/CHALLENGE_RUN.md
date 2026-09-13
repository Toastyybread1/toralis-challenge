# Required challenge interface

Main release: Python 3.12 CPU-only has also reproduced the supplied subject-21
result. The ten required checkpoints and manifests are bundled on main; see
`config/models-manifest.json`. Recommended setup is `python scripts/setup_environment.py`,
which uses the CPU PyTorch index on Windows/Linux, not the CUDA training index.

Run from the repository root with Python 3.12/3.13 and the existing model-weight
directories `models/learned_results/` and `models/learned_2000_results/`.

Setup (before entering the offline evaluation environment):

```powershell
python -m pip install -r config/requirements-submission.txt
```

Run an unseen case:

```powershell
python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json
```

This now runs the current detector on CPU, with neural evidence enabled by
default where model spacing is supported, and exports the challenge schema.
`prediction_review/` preserves detailed evidence; `diagnostics/prediction.json`
records selection exclusions. The case ID defaults to the input directory name;
use `--case-id subject001` when the inputs are in a generically named directory.
Missing requested model weights fail the command rather than inventing an empty result.

For local development cases 19–23, use the frozen exported JSONs, or pass
`--held-out-case 21` (with the corresponding case) to exclude its training fold.
Do not present a run using all development models on a training case as held-out accuracy.

The old `--document-review --neural` directory-output interface still works.
The required filename-output interface no longer dispatches to the older
classical submission baseline. The original detector remains available by
explicitly running `submission.py`, but its outputs are not current results.

Deliverables: `outputs/predictions/subject*.json`, `outputs/predictions/visual_checks/`, source
code, requirements files, required model weights and the team demonstration.
The existing `outputs/team_review.zip` is a review presentation, not the inference package.
See `outputs/predictions/README.md` for the exported set's accuracy and limitations.
