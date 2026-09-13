# BranchForge — three-minute pitch

**Timing:** 18-second opening + 72-second algorithm + 72-second live demo + 18-second close. Here, “1.2 minutes” means 72 seconds. Read the quoted text; bracketed cues are actions, not narration. Rehearse to the section boundaries and use spare seconds for clicks.

## 0:00–0:18 · The problem

> Finding where smaller arteries leave the aorta is a starting point for vessel analysis. Doing that manually means inspecting a complex three-dimensional scan. BranchForge proposes those openings and short traces, then lets a researcher check the evidence visually.

## 0:18–1:30 · The algorithm

> We start with a contrast CT and a mask identifying only the aorta. SimpleITK preserves physical coordinates, so measurements mean millimetres, not arbitrary pixels.
>
> First, we compare brightness inside and outside the aorta to estimate what blood looks like in this scan. That adapts to contrast differences. We grow connected, blood-like regions near the wall, with distance and spill limits to constrain leakage into surrounding tissue.
>
> Next, wall-contact sampling, a skeleton graph and local searches propose curved branch paths. We cross-check them using perpendicular CT slices, small three-dimensional neural networks running on CPU, and graph checks for direct connection. Multiple checks help reject false branches; grouping openings avoids counting one common trunk twice.
>
> Finally, eligible openings get a seed five millimetres along the trace, a local radius and an outward direction. Those measurements can initialize downstream vessel tracking. We do not assume a fixed branch count, and we preserve uncertainty instead of presenting every proposal as confirmed anatomy.

## 1:30–2:42 · Live demo

**1:30–1:43 — Load the prepared CT/mask pair and start detection.** Select **Subject 021 — held-out models**, then **Run detection**. If the study is already loaded, point to its inputs rather than reloading it.

> Here are the CT and aorta mask. I select this development subject’s held-out models and run detection. Processing stays on this laptop; no GPU is required.

**1:43–2:05 — Rotate the model, show linked slices and toggle a display layer while detection runs.**

> I used 3D Slicer during my hospital internship. Its extension system let us redesign the interface while reusing its imaging and segmentation capabilities. Linked slices let us check whether a prediction agrees with the CT—not just whether the model looks convincing.

**2:05–2:19 — Select a detected branch, show Details, then JSON.**

> Selecting a branch shows its opening, seed, radius and estimated trace. The readable report explains the measurements; the original JSON is underneath for other software.

**2:19–2:31 — Save with “Export edited .nii”; point out JSON and screenshot exports.** Have the filename ready; save dialogs and verification need a few seconds.

> We can export JSON, a screenshot, or an edited NIfTI labelmap: aorta plus traces, not complete vessel walls. The original CT stays untouched.

**2:31–2:42 — Show the preconfigured AR tab and phone.** Use only approved de-identified demo data.

> This QR opens the anatomy at anatomical scale on a compatible phone, making spatial relationships easier to explain. iPhone AR needs reopening for updates.

## 2:42–3:00 · Results and next step

> On five development scans, the final export matched seventeen of nineteen draft origins, with one false positive: ninety-two percent F1, rounded. These cases informed development, so independent expert validation is next. This is a research prototype, not a clinical tool.

## Before presenting

- Preload subject 021, choose its held-out models, and rehearse once on the actual laptop. One measured GUI detection took about 34 seconds; other runs were slower. Do not promise a fixed runtime.
- Keep a second window with a completed run. If detection is still running at **2:05**, say **“While that finishes, here is a previously completed run of the same case”** and switch. Keep its real traces, not only a standalone JSON. Never imply the saved result just finished live.
- Configure AR and test the actual phone before the pitch. If AR is unavailable, show the phone’s 3D viewer and describe AR as a supported-device option; do not pretend it was tested. Sharing is optional, online and off by default.
- Use a fresh export filename and an already-open destination folder. NIfTI values are **0 background / 1 current parent segmentation / 2 estimated centerlines outside the parent**. JSON keeps individual branch IDs; NIfTI label 2 combines the traces.
- Accuracy figure: **94.4% precision / 89.5% recall / 91.9% F1**, with 3 mm one-to-one origin matching. It does not measure full-vessel segmentation accuracy, clinical safety, or performance on all 25 scans. A model’s held-out training fold does not make repeatedly tuned development cases an independent test set.
