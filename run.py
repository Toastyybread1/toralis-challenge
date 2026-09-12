"""Competition entry point. All inference is local and CPU-only."""

from src.runtime import limit_cpu_threads, peak_rss_mb
limit_cpu_threads()

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import platform
import time

import SimpleITK as sitk

from src.output import prediction_dict, write_prediction_json
from src.pipeline import run_pipeline
from src.types import Config


def main():
    start = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--aorta-mask", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--case-id", help="Defaults to CT parent folder name")
    parser.add_argument("--debug-dir", help="Optional diagnostics and overlay output")
    parser.add_argument("--diagnostics", help="Optional runtime/configuration JSON path")
    parser.add_argument("--min-radius-mm", type=float, default=0.8,
                        help="Provisional engineering cutoff; replace with final organizer size rule")
    parser.add_argument("--working-spacing-mm", type=float, default=0.8)
    args = parser.parse_args()
    if Path(args.output).resolve() in (Path(args.image).resolve(), Path(args.aorta_mask).resolve()):
        parser.error("Output must not overwrite an input")
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    try:
        config = Config(min_radius_mm=args.min_radius_mm, working_spacing_mm=args.working_spacing_mm)
        branches, roi, context = run_pipeline(args.image, args.aorta_mask, config)
        data = prediction_dict(args.case_id or Path(args.image).resolve().parent.name, branches)
        write_prediction_json(args.output, data)
        context.diagnostics["config"] = asdict(config)
        context.diagnostics["peak_rss_mb"] = peak_rss_mb()
        context.diagnostics["versions"] = {"python": platform.python_version(), "SimpleITK": sitk.Version_VersionString()}
        if args.debug_dir:
            from src.visualization import show_detection
            directory = Path(args.debug_dir)
            directory.mkdir(parents=True, exist_ok=True)
            show_detection(roi, context, branches, directory)
        context.diagnostics["seconds"]["including_output_and_debug"] = time.perf_counter() - start
        diagnostic_path = args.diagnostics or (str(Path(args.debug_dir) / "diagnostics.json") if args.debug_dir else None)
        if diagnostic_path:
            path = Path(diagnostic_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(context.diagnostics, indent=2, allow_nan=False) + "\n")
        print(f"{data['case_id']}: {len(branches)} branches; "
              f"pipeline {context.diagnostics['seconds']['total']:.2f} s; {args.output}")
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
