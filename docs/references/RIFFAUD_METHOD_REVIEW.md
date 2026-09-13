# Riffaud 2022 full-paper review and graph traversal

Source: C:/Users/nikag/Downloads/s11517-022-02603-2.pdf, DOI 10.1007/s11517-022-02603-2. Relevant pages read in full: PDF pages 2–4 and 11 (printed 2640–2642 and 2649); page 3 definitions and Figure 3 also visually inspected.

## What the paper actually provides

Section 2.1 states that Nurea/PRAEVAorta provides both segmentations and vascular trees. The segmentation includes lumen and thrombus. The supplied graph is connected, acyclic and undirected, with nodes along central lines. The article's matching method operates on this tree; it does not provide an independently reproducible CT-to-tree extraction algorithm in those methods.

Definition 2 measures distance as summed Euclidean edge lengths. Definition 3 identifies endpoints by degree one and bifurcations by degree at least three. Section 2.3 Definition 8 follows a primary branch from its starting junction to the first bifurcation or leaf. These are directly useful to our proximal stopping problem.

The local direction definition on printed page 2642 uses a principal axis of origin-relative node coordinates within 3r along the primary branch. Anatomical matching and extra-renal decision rules are separate stages. The study restricts inputs to segmentations containing the aortic bifurcation. Its anatomical naming rules and long-branch warnings (3r or r+20 mm) must not be transplanted into the organizer's all-daughters, 5–10 mm task.

## Implemented bounded step

vascular_tree.py validates an input tree and follows a selected outgoing daughter edge. It ignores the starting origin's own junction degree, stops at the first downstream node of degree >=3, and interpolates a 5 mm seed along physical arc length. It stops at 10 mm if no earlier junction occurs. Early bifurcations have no invented downstream seed; short leaves remain incomplete. Cyclic/disconnected graphs, duplicate edges and zero-length edges are rejected rather than silently repaired into a supposed anatomical tree.

Tree degree is a topological bifurcation candidate, not proof of contrast-filled anatomical branching. A spur caused by a segmentation bump also has degree three. No spur pruning threshold was invented or presented as coming from this paper. Outgoing node IDs and split coordinates are retained for later lumen-support checks.

The 5 mm and 10 mm rules are organizer adaptations, not Riffaud parameters. The module expects physical LPS coordinates and a verified origin at the parent boundary; it does not infer that boundary itself.

## Validation and integration status

All 48 tests pass. Seven new tests cover curved arc-length seed placement, first split before a downstream choice, early splitting, parent-origin junction exclusion, incomplete leaves, invalid graph topology and rigid-coordinate invariance.

This module is not yet used by submission.py. Existing predictions and the cross-section bifurcation heuristic are unchanged. No organizer-case bifurcation improvement is claimed. Existing saved tracing paths cannot provide the missing outgoing topology: deriving a graph from a single path would always miss unexplored branches.

## Required next step

Build a reviewed prototype that extracts a connected centreline graph from the grown daughter lumen, with origin anchoring, preservation of distinct arms, handling of adjacent skeleton junction voxels, and explicit cycle/spur uncertainty. The paper does not supply that extractor. Test it on straight/curved tubes, Y shapes, short spurs, adjacent unconnected vessels and leaky masks before integrating. Then compare graph split locations with organizer notes on the five cases, keeping growth parameters fixed.

The original recursive idea is useful: treat the daughter segment as a local parent. But repeated dilation alone cannot distinguish continued lumen from two outgoing arms; the graph must be supported by the segmented volume. Per-daughter segmentation and graph extraction remain prerequisites.


## Extraction prototype update

A Lee-thinning extractor is now implemented and tested separately in centreline_extraction.py. See centreline_results/REPORT.md for limits, 56 passing tests and the five-case audit. It has not been promoted to the submission bifurcation decision: origin anchoring and uncertain topology remain unresolved.
