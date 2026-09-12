"""CPU-only physical-space orthogonal views: python -m src.visualization."""

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import SimpleITK as sitk

from .preprocessing import basic_statistics, load_case, mask_center_physical


def show_case(case, output_path=None, *, center_lps_mm=None,
              window_center=200.0, window_width=700.0, show=False):
    """Plot true LPS planes, including for oblique inputs, with red mask overlays.

    Resampling is for display only. CT uses linear interpolation and mask uses
    nearest neighbor. The default crosshair is the mask's physical centroid.
    Returns a Matplotlib figure; callers own closing it.
    """
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    if not np.isfinite([window_center, window_width]).all() or window_width <= 0:
        raise ValueError("Window center must be finite and width positive")
    center = np.asarray(mask_center_physical(case) if center_lps_mm is None else center_lps_mm)
    if center.shape != (3,) or not np.isfinite(center).all():
        raise ValueError("Expected three finite LPS coordinates")
    corners = np.array([
        case.image.TransformContinuousIndexToPhysicalPoint(tuple(float(v) for v in corner))
        for corner in itertools.product(*[(-0.5, s - 0.5) for s in case.image.GetSize()])
    ])
    lower, upper = corners.min(axis=0), corners.max(axis=0)
    if np.any(center < lower) or np.any(center > upper):
        raise ValueError("View center is outside the physical image bounds")
    pixel_mm = max(0.5, min(case.image.GetSpacing()))
    figure, axes = plt.subplots(1, 3, figsize=(15, 6), layout="constrained")
    labels = ["L (mm)", "P (mm)", "S (mm)"]
    # Columns define in-plane horizontal, vertical, and normal axes in LPS.
    planes = [("Axial", 0, 1, 2), ("Coronal", 0, 2, 1), ("Sagittal", 1, 2, 0)]
    for ax, (name, horizontal, vertical, normal) in zip(axes, planes):
        basis = np.eye(3)[:, [horizontal, vertical, normal]]
        origin = center.astype(float).copy()
        origin[horizontal] = lower[horizontal] + pixel_mm / 2
        origin[vertical] = lower[vertical] + pixel_mm / 2
        size = [int(np.ceil((upper[a] - lower[a]) / pixel_mm)) for a in (horizontal, vertical)]
        reference = sitk.Image(size + [1], sitk.sitkFloat32)
        reference.SetOrigin(origin.tolist())
        reference.SetSpacing([pixel_mm, pixel_mm, pixel_mm])
        reference.SetDirection(basis.ravel().tolist())
        ct_slice = sitk.GetArrayFromImage(sitk.Resample(
            case.image, reference, sitk.Transform(), sitk.sitkLinear,
            window_center - window_width / 2, sitk.sitkFloat32))[0]
        mask_slice = sitk.GetArrayFromImage(sitk.Resample(
            case.aorta_mask, reference, sitk.Transform(), sitk.sitkNearestNeighbor,
            0, sitk.sitkUInt8))[0]
        extent = [lower[horizontal], lower[horizontal] + size[0] * pixel_mm,
                  lower[vertical], lower[vertical] + size[1] * pixel_mm]
        ax.imshow(ct_slice, cmap="gray", origin="lower", extent=extent,
                  vmin=window_center - window_width / 2,
                  vmax=window_center + window_width / 2, interpolation="nearest")
        ax.imshow(np.ma.masked_equal(mask_slice, 0), cmap=ListedColormap(["red"]),
                  vmin=0, vmax=1, alpha=0.4, origin="lower", extent=extent,
                  interpolation="nearest")
        ax.set(title=f"{name}: {'LPS'[normal]} = {center[normal]:.1f} mm",
               xlabel=labels[horizontal], ylabel=labels[vertical], aspect="equal")
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=150)
    if show:
        plt.show()
    return figure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--aorta-mask", required=True)
    parser.add_argument("--output-dir", default="outputs/phase1")
    parser.add_argument("--window-center", type=float, default=200)
    parser.add_argument("--window-width", type=float, default=700)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    if not args.show:
        import matplotlib
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    case = load_case(args.image, args.aorta_mask)
    report = basic_statistics(case)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    figure = show_case(case, output / "overlays.png", window_center=args.window_center,
                       window_width=args.window_width, show=args.show)
    plt.close(figure)
    (output / "statistics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"Overlays: {output / 'overlays.png'}")


def show_detection(roi, context, branches, output_dir):
    """Save physical LPS slab views; all path markers are projections within the slab."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for array in (roi.aorta, roi.shell, context.vesselness, context.lumen):
        image = sitk.GetImageFromArray(array.astype(np.float32))
        image.CopyInformation(roi.image)
        images.append(image)

    def plane(volume, center, h, v, n, slab=True):
        step = roi.spacing_mm
        half = 20.0
        width = int(np.ceil(2 * half / step)) + 1
        depth = int(np.ceil(12 / step)) + 1 if slab else 1
        origin = np.array(center, dtype=float)
        origin[h] -= half
        origin[v] -= half
        origin[n] -= (depth - 1) * step / 2
        basis = np.eye(3)[:, [h, v, n]]
        ref = sitk.Image([width, width, depth], sitk.sitkFloat32)
        ref.SetOrigin(origin.tolist())
        ref.SetDirection(basis.ravel().tolist())
        ref.SetSpacing([step] * 3)
        resampled = sitk.GetArrayFromImage(sitk.Resample(volume, ref, sitk.Transform(),
                          sitk.sitkNearestNeighbor, -1024 if volume is roi.image else 0, sitk.sitkFloat32))
        extent = [origin[h] - step / 2, origin[h] + (width - 0.5) * step,
                  origin[v] - step / 2, origin[v] + (width - 0.5) * step]
        return resampled.max(axis=0), extent

    centers = [b.ostium_xyz_mm for b in branches]
    if not centers:
        from .types import physical
        centers = [physical(roi.image, np.argwhere(roi.aorta).mean(axis=0))]
    overview, overview_axes = plt.subplots(len(centers), 3, squeeze=False,
                                           figsize=(12, 3.8 * len(centers)), layout="constrained")
    for row, center in enumerate(centers):
        for ax, (name, h, v, n) in zip(overview_axes[row],
                [("Axial", 0, 1, 2), ("Coronal", 0, 2, 1), ("Sagittal", 1, 2, 0)]):
            ct, extent = plane(roi.image, center, h, v, n)
            mask, _ = plane(images[0], center, h, v, n)
            ax.imshow(ct, cmap="gray", vmin=-150, vmax=550, origin="lower", extent=extent)
            ax.imshow(np.ma.masked_equal(mask, 0), cmap=ListedColormap(["red"]),
                      alpha=0.3, origin="lower", extent=extent, vmin=0, vmax=1)
            if branches:
                branch = branches[row]
                path = branch.path_xyz_mm
                shown = np.abs(path[:, n] - center[n]) <= 6
                ax.plot(np.where(shown, path[:, h], np.nan), np.where(shown, path[:, v], np.nan),
                        color="cyan", linewidth=1.2)
                ax.scatter(*center[[h, v]], color="yellow", s=28, marker="x")
                seed = branch.seed_xyz_mm
                ax.scatter(*seed[[h, v]], color="cyan", s=15)
                ax.annotate("", xy=seed[[h, v]], xytext=center[[h, v]],
                            arrowprops={"arrowstyle": "->", "color": "yellow"})
            label = f"branch_{row + 1:03d}" if branches else "No detections"
            ax.set(title=f"{label} | {name}", xlabel=f"{'LPS'[h]} (mm)",
                   ylabel=f"{'LPS'[v]} (mm)", aspect="equal")
    overview.suptitle("12 mm slab MIP: red=aorta, yellow=ostium/direction, cyan=path/5 mm seed", fontsize=11)
    overview.savefig(output_dir / "detections.png", dpi=130)
    plt.close(overview)

    figure, axes = plt.subplots(1, 4, figsize=(14, 4), layout="constrained")
    center = centers[len(centers) // 2]
    ct, extent = plane(roi.image, center, 0, 1, 2, slab=False)
    for ax, volume, name in zip(axes, images, ("Aorta", "Search shell", "Vesselness", "Candidate lumen")):
        array, _ = plane(volume, center, 0, 1, 2, slab=False)
        ax.imshow(ct, cmap="gray", vmin=-150, vmax=550, origin="lower", extent=extent)
        ax.imshow(np.ma.masked_less_equal(array, 0), cmap="autumn", alpha=0.5,
                  origin="lower", extent=extent, vmin=0, vmax=1)
        ax.set(title=name, xlabel="L (mm)", ylabel="P (mm)")
    figure.savefig(output_dir / "stages.png", dpi=130)
    plt.close(figure)


if __name__ == "__main__":
    main()
