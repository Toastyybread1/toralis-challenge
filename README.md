# Branchseed

CPU detection of direct aortic daughter vessels from CT and an aorta-only mask.

## Start here

- **View with teammates:** double-click `Show-Team-Review.cmd`.
- **Prediction JSONs:** `outputs/predictions/subject001.json` through `subject025.json`.
- **Portable files:** `outputs/team_review.zip` and `outputs/predictions.zip`.

## Setup and run

Use Python 3.13, run from this directory, and retain the supplied `models/` folder.

```powershell
python -m pip install -r config/requirements-submission.txt
python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json
```

Inference uses CPU. For local development cases 19–23, add `--held-out-case 21`
(using the corresponding case number). See [the run guide](docs/CHALLENGE_RUN.md).

## Layout

| Folder | Contents |
|---|---|
| `src/` | Detector implementation and shared geometry/loading code |
| `models/` | Required neural weights and provenance |
| `data/` | Original CT and parent masks |
| `references/` | Organizer development references, used after inference |
| `results/` | Saved review results and regression baseline |
| `outputs/` | Submission JSONs, visual checks and portable team presentation |
| `tests/` | Active regression suite |
| `tools/` | Export and presentation builders |
| `config/` | Dependency lists |
| `docs/` | Run guide, methodology and source documents |

Test: `python -m unittest discover -s tests -p "test_*.py"`.
Rebuild presentation: `python -m tools.build_team_review`.
Regenerate JSONs: `python -m tools.export_challenge_predictions`.

## Current accuracy

The challenge export has **17/19 draft matches, 1 unmatched prediction and 2 misses**
at a 3 mm development tolerance. The broader review set has 18/19 matches, two
unmatched counted groups and one deferred candidate. These are different selections;
neither is expert anatomical sign-off or hidden-test accuracy.

Historical work and the original case-24 diagnostic are preserved outside this
project in `../_branchseed_history_20260913/`. The active case-24 loader is in
`src/utils.py`; its display evidence is in `results/case24_display_restored/`.
