"""Inspect CT/mask loading, aorta cropping, and optional orthogonal resampling."""

from src.runtime import limit_cpu_threads
limit_cpu_threads()

import argparse
import json
from pathlib import Path
import sys

import SimpleITK as sitk

from src.preprocessing import basic_statistics, crop_case, load_case, resample_case
from src.visualization import show_case


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--aorta-mask", required=True, type=Path)
    parser.add_argument("--output-dir", default="outputs/inspection", type=Path)
    parser.add_argument("--crop-margin-mm", type=float, default=20.0)
    parser.add_argument("--resample", action="store_true",
                        help="Also save an orthogonal CT/mask crop and a mask-volume comparison")
    parser.add_argument("--show", action="store_true", help="Open figures interactively")
    args = parser.parse_args(argv)
    products = [args.output_dir / name for name in ("original.png", "cropped.png", "statistics.json")]
    if args.resample:
        products += [args.output_dir / name for name in
                     ("orthogonal.png", "ct_orthogonal.nii.gz", "mask_orthogonal.nii.gz")]
    if {p.resolve() for p in products} & {args.image.resolve(), args.aorta_mask.resolve()}:
        parser.error("Inspection outputs must not overwrite the input files")
    if not args.show:
        import matplotlib
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        case = load_case(args.image, args.aorta_mask)
        cropped = crop_case(case, args.crop_margin_mm)
        report = {"original": basic_statistics(case), "cropped": basic_statistics(cropped)}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        figures = [show_case(case, args.output_dir / "original.png"),
                   show_case(cropped, args.output_dir / "cropped.png")]
        if args.resample:
            corrected = resample_case(cropped)
            report["orthogonal"] = basic_statistics(corrected)
            before = report["cropped"]["aorta_volume_mm3"]
            after = report["orthogonal"]["aorta_volume_mm3"]
            report["mask_volume_change_percent"] = 100 * (after - before) / before
            report["max_axis_correction_degrees"] = float(
                corrected.image.GetMetaData("toralis_max_axis_correction_degrees"))
            sitk.WriteImage(corrected.image, str(args.output_dir / "ct_orthogonal.nii.gz"))
            sitk.WriteImage(corrected.aorta_mask, str(args.output_dir / "mask_orthogonal.nii.gz"))
            figures.append(show_case(corrected, args.output_dir / "orthogonal.png"))
        (args.output_dir / "statistics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps(report, indent=2, allow_nan=False))
        print(f"Inspection saved to {args.output_dir}")
        if args.show:
            plt.show()
        for figure in figures:
            plt.close(figure)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
