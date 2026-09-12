"""Pure-Python detector discovery and argument construction, shared with tests."""
from pathlib import Path
import os


def detector_paths(repo, saved_python="", saved_script=""):
    repo = Path(repo)
    local_python = repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    local_script = repo / "run.py"
    # Keep explicit valid choices; recover automatically from stale saved paths.
    executable = saved_python if Path(saved_python).is_file() else str(local_python) if local_python.is_file() else ""
    script = saved_script if Path(saved_script).is_file() else str(local_script) if local_script.is_file() else ""
    return executable, script


def detection_arguments(script, image, mask, output, case_id):
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("A nonempty loaded case ID is required.")
    return [str(Path(script).resolve()), "--image", str(Path(image).resolve()),
            "--aorta-mask", str(Path(mask).resolve()), "--output", str(Path(output).resolve()),
            "--case-id", case_id]
