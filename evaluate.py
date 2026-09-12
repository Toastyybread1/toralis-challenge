"""Run a dataset serially in fresh CPU-limited processes, optionally against references."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from src.evaluation import compare_predictions
from src.output import validate_prediction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", default="outputs/development", type=Path)
    parser.add_argument("--reference-dir", type=Path,
                        help="Optional <case_id>.json files in competition schema")
    parser.add_argument("--match-mm", type=float, default=5)
    parser.add_argument("--visualize-cases", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    folders = sorted(p for p in args.dataset.iterdir() if p.is_dir())
    if not folders:
        parser.error("Dataset contains no case directories")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, folder in enumerate(folders):
        output = args.output_dir / folder.name
        ct = sorted(folder.glob("orig*.nii*"))
        mask = sorted(folder.glob("mask*.nii*"))
        row = {"case_id": folder.name}
        if len(ct) != 1 or len(mask) != 1:
            row.update(status="failed", error="Expected one orig*.nii[.gz] and one mask*.nii[.gz]")
            results.append(row)
            continue
        command = [sys.executable, str(Path(__file__).with_name("run.py")),
                   "--image", str(ct[0]), "--aorta-mask", str(mask[0]),
                   "--output", str(output / "prediction.json"), "--case-id", folder.name,
                   "--diagnostics", str(output / "diagnostics.json")]
        if i < args.visualize_cases:
            command += ["--debug-dir", str(output)]
        start = time.perf_counter()
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
            if process.returncode:
                raise RuntimeError(process.stderr.strip())
            prediction = json.loads((output / "prediction.json").read_text())
            validate_prediction(prediction)
            diagnostic = json.loads((output / "diagnostics.json").read_text())
            row.update(status="ok", detected_count=len(prediction["daughters"]),
                       wall_seconds=time.perf_counter() - start, pipeline_seconds=diagnostic["seconds"]["total"],
                       peak_rss_mb=diagnostic["peak_rss_mb"], reference_comparison=None)
            if args.reference_dir:
                reference = args.reference_dir / f"{folder.name}.json"
                if reference.is_file():
                    row["reference_comparison"] = compare_predictions(prediction, json.loads(reference.read_text()), args.match_mm)
            print(f"{folder.name}: {row['detected_count']} branches, {row['pipeline_seconds']:.2f}s", flush=True)
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
            row.update(status="failed", error=str(error))
            print(f"{folder.name}: FAILED: {error}", flush=True)
        results.append(row)
        (args.output_dir / "evaluation.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    (args.output_dir / "evaluation.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    return int(any(row["status"] != "ok" for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
