"""Run each stage independently and expose diagnostics for inspection."""

import time

from .detection import detect_candidates
from .preprocessing import load_case, prepare_case
from .tracing import analyze_candidates
from .types import Config


def run_pipeline(image_path, mask_path, config=None):
    config = config or Config()
    start = time.perf_counter()
    case = load_case(image_path, mask_path)
    geometry_source = (case.image.GetMetaData("toralis_geometry_source")
                       if case.image.HasMetaDataKey("toralis_geometry_source") else "SimpleITK NIfTI reader")
    loaded = time.perf_counter()
    roi = prepare_case(case, config)
    # Release full-volume arrays before allocating vesselness/Hessian intermediates.
    del case
    prepared = time.perf_counter()
    candidates, context = detect_candidates(roi, config)
    context.diagnostics["geometry_source"] = geometry_source
    detected = time.perf_counter()
    branches = analyze_candidates(candidates, roi, context, config)
    finished = time.perf_counter()
    context.diagnostics["seconds"] = {
        "load": loaded - start, "preprocess": prepared - loaded,
        "detection": detected - prepared, "tracing": finished - detected,
        "total": finished - start,
    }
    return branches, roi, context
