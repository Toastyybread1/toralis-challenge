"""Check CT/mask loading and physical cropping across a dataset (no detection)."""

from src.runtime import limit_cpu_threads
limit_cpu_threads()

import argparse
import json
from pathlib import Path
import sys
import time

from src.dataset import case_directories, find_case_files
from src.preprocessing import crop_case, load_case


def test_subject(subject_dir, margin_mm=20.0):
    try:
        image_path, mask_path = find_case_files(subject_dir)
        case = load_case(image_path, mask_path)
        cropped = crop_case(case, margin_mm)
        return True, {
            "original_shape": list(case.ct_zyx.shape),
            "crop_shape": list(cropped.ct_zyx.shape),
            "spacing": list(case.image.GetSpacing()),
            "aorta_voxels": int(case.mask_zyx.sum()),
            "geometry_source": (case.image.GetMetaData("toralis_geometry_source")
                                if case.image.HasMetaDataKey("toralis_geometry_source")
                                else "SimpleITK NIfTI reader"),
        }
    except (ValueError, RuntimeError, OSError) as error:
        return False, str(error)


# This is a batch-check helper, not a pytest test requiring a subject_dir fixture.
test_subject.__test__ = False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--crop-margin-mm", type=float, default=20.0)
    parser.add_argument("--output", type=Path, help="Optional preprocessing report JSON")
    args = parser.parse_args(argv)
    try:
        subjects = case_directories(args.dataset)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    if args.output and args.output.suffix.lower() != ".json":
        parser.error("--output must be a JSON file")
    results = []
    for subject in subjects:
        started = time.perf_counter()
        success, result = test_subject(subject, args.crop_margin_mm)
        row = {"case_id": subject.name, "status": "ok" if success else "failed",
               "seconds": time.perf_counter() - started}
        row.update(result if success else {"error": result})
        results.append(row)
        detail = f"shape={result['original_shape']}, crop={result['crop_shape']}" if success else result
        print(f"[{'PASS' if success else 'FAIL'}] {subject.name}: {detail}", flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    passed = sum(row["status"] == "ok" for row in results)
    print(f"Passed: {passed}/{len(results)}")
    return int(passed != len(results))


if __name__ == "__main__":
    raise SystemExit(main())
