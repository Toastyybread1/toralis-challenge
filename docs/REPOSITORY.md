# Repository organization

The top-level README is the current repository map. Source modules now live
under `src/`; internal review modules are under `src/rebuild/`. Imports use the
`src` package. The required `run.py` command is unchanged.

Historical work is in `../../_branchseed_history_20260913/`, outside this project.
Its `relocation.json` records moved entries; `source-before/` preserves pre-move
source. The prior archive retains its own per-file SHA-256 manifest. Nothing
was permanently deleted. Original images and review decisions were not edited.

The source layout changes provenance paths and hashes. Frozen results retain
their original provenance records; they are not rewritten to imply a rerun.
Current inference writes the new source paths in its own output records.

`src/submission.py` remains because the current pipeline uses its contact-start
initializer. `src/rebuild/origin_refinement.py` remains in source provenance.
They are implementation dependencies, not alternative launch instructions.

Active tests: `python -m unittest discover -s tests -p "test_*.py"`.
Batch inference: `python -m src.rebuild.run_review_pipeline --neural --output results/new_run`.
Build its review gallery: `python -m src.rebuild.build_review_workspace --results results/new_run`.
