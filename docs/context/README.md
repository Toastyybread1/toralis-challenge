# Context sources and pre-redesign baseline

Start with [the root CLAUDE.md](../../CLAUDE.md). It contains the UI redesign assignment, the complete technical challenge requirements in readable form, sponsor background, project architecture and operating instructions.

## Original source documents

| File | Provenance | Purpose |
| --- | --- | --- |
| [branchseed-challenge.pdf](branchseed-challenge.pdf) | Exact copy of the user's `C:\Users\sulai\Downloads\Branchseed challenge.pdf`, six pages | Detailed Branchseed assignment; includes original illustrations and rubric |
| [toralis-whitepaper.md](toralis-whitepaper.md) | Exact copy of the whitepaper text the user pasted in the prior conversation | Sponsor-provided company/research context; claims are not our project results |
| [devpost-snapshot.txt](devpost-snapshot.txt) | Exact copy of the Devpost page text the user pasted | Event snapshot, submission checklist, schedule and general judging; not live-verified |

These files were copied without content changes, and source/destination SHA-256 hashes were checked. The copied PDF is 7,027,576 bytes. No original source was deleted or altered.

The documents describe challenge requirements and company background. The user's actual request to Claude is to **redesign the existing Slicer extension UI**, with the detection pipeline owned by teammates. Do not treat the whitepaper as a requirement to build the sponsor's full platform.

## Historical implementation evidence

| File | Meaning |
| --- | --- |
| [current-ui.png](current-ui.png) | Final verified real-study startup screenshot from September 12, 2026, about 2:00 PM Eastern. `subject001` is loaded; no prediction is present. |
| [synthetic-ui-earlier.png](synthetic-ui-earlier.png) | Earlier build screenshot showing fictional anatomy and four reference branches. It predates the final workflow-tab and compact-header refinements. |
| [baseline-slicer-smoke-report.json](baseline-slicer-smoke-report.json) | Successful full GUI/integration smoke report from about 1:54 PM Eastern, before the final screen-fit edits. Tests use fixtures, not a real detector. |
| [baseline-launch-report.json](baseline-launch-report.json) | Successful final startup check from about 2:00 PM Eastern, after the screen-fit adjustment. |

## Redesigned interface, September 12, 2026, about 4:50 PM Eastern

| File | Meaning |
| --- | --- |
| [redesign-ready.png](redesign-ready.png) | Real `subject001` loaded, no prediction: Detect page, empty results state, live slice headers. |
| [redesign-synthetic.png](redesign-synthetic.png) | Synthetic example with `branch_003` selected: labelled warning, branch table, dimmed non-selected overlays. |
| [redesign-details.png](redesign-details.png) | Details view: origin/seed cards, direction compass and gauge, radius at seed. |

Captured by `slicer-extension/tests/visual_tour.py` at 1440 x 852 logical pixels with 200% scaling (2880 x 1660 physical). The full smoke suite passed on the same build.

The reports and screenshots are historical snapshots to orient the redesign agent. They do not prove that later changes pass tests and do not measure branch-detection accuracy. Keep generated new test artifacts in `slicer-extension/artifacts/qa`, which is ignored by Git.

## Source disagreements and unresolved details

- Devpost gives both 2-4 and 1-4 team-size descriptions.
- Devpost names different Toralis first-prize keyboards in different sections and gives inconsistent descriptions of school-point accounting.
- The PDF asks for a five-minute demonstration; Devpost asks for a separate video of up to three minutes.
- The PDF's minimum eligible branch-origin size and final runtime limit await final dataset/organizer confirmation.
- The small development reference subset has not been identified in the current project files.
- The whitepaper's medical study percentage and commercial figures are source claims, not independently verified facts or project metrics.

Preserve these qualifications when pitching or redesigning. Refer to updated organizer guidance when available.
