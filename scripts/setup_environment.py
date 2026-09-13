"""Create an isolated detector environment. Does not alter Slicer's Python."""
from pathlib import Path
import os
import subprocess
import sys
import venv


def main():
    if sys.version_info[:2] not in ((3, 12), (3, 13)):
        raise SystemExit("Use Python 3.12 or 3.13 to run this setup command.")
    root = Path(__file__).resolve().parents[1]
    directory = root / ".venv"
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(directory)
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "requirements.txt")], check=True)
    torch_args = ["torch==2.11.0"] if sys.platform == "darwin" else [
        "torch==2.11.0+cpu", "--index-url", "https://download.pytorch.org/whl/cpu"]
    subprocess.run([str(python), "-m", "pip", "install", *torch_args], check=True)
    subprocess.run([str(python), str(root / "scripts" / "verify_models.py")], check=True)
    subprocess.run([str(python), "-c", "import SimpleITK, numpy, scipy, skimage, nibabel, matplotlib, torch; print('Detector dependencies OK; torch', torch.__version__)"], check=True)
    print("Ready. Launch slicer-extension/Launch-BranchForge.ps1 on Windows.")
    print("Pipeline Python:", python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
