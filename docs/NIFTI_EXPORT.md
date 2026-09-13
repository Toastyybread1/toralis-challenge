# Export the edited result

After detection, click **Export edited .nii** below **Export prediction JSON**.
Choose a new `.nii` or `.nii.gz` filename. Open it as a **labelmap/segmentation**
beside the original CT, not as a replacement CT.

| Value | Meaning |
|---|---|
| 0 | Background |
| 1 | Current parent-aorta segmentation, including its voxel edits |
| 2 | Estimated centerlines outside the parent; all branches share this value |

The parent takes priority where a trace overlaps it. Individual branch IDs,
seeds, directions and radius estimates remain in the separate prediction JSON.
Paths are thin voxelized centerlines, not radius-filled tubes or complete
daughter-vessel segmentations. Display visibility, opacity, arrows and camera
position do not affect these labels.

Export preserves the loaded CT grid and verifies voxel values and physical
geometry by reloading a temporary NIfTI before writing the destination. Original
CT/mask paths cannot be overwritten. No extra Python package or cloud upload is
needed. Source images may contain sensitive information; handle exported masks
under the same data-sharing restrictions.

Run detection to obtain actual paths. A JSON-only import, a synthetic example,
or missing path evidence cannot enable this export. Additional segmentation
segments, external transforms or edits extending beyond the CT grid must be
resolved first; export rejects them rather than guessing an alignment.
If the parent mask is edited after detection, rerun detection with a separately
saved edited input mask to update the predictions: exporting does not rerun it.

## Verification

Native Slicer 5.12.4, local subject 021: four actual detector traces; both `.nii`
and `.nii.gz` round trips passed. A deliberate parent-segmentation edit survived,
all remaining parent voxels were preserved, both files contained 36 outside-parent
trace voxels, source hashes stayed unchanged, and JSON-only export was blocked.
This checks the export mechanism, not anatomical accuracy.

Pure-array tests cover LPS-to-RAS conversion, rotated/anisotropic geometry,
continuous voxel paths, crossing traces, invalid coordinates and input protection.
The reproducible native check is `slicer-extension/tests/nifti_export_smoke.py`;
it needs the local demo inputs and saved pipeline sidecars and must run in a new
Slicer process. Reports and screenshots stay in ignored `slicer-extension/artifacts/`.
