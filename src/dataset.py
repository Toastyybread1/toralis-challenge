"""Shared case discovery for preprocessing checks and prediction evaluation."""

from pathlib import Path


def case_directories(dataset):
    root = Path(dataset)
    if not root.is_dir():
        raise ValueError(f"Dataset directory does not exist: {root}")
    folders = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not folders:
        raise ValueError("Dataset contains no case directories")
    return folders


def find_case_files(folder):
    folder = Path(folder)
    files = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.name.lower().endswith((".nii", ".nii.gz")))
    image = [p for p in files if p.name.lower().startswith("orig")]
    mask = [p for p in files if p.name.lower().startswith("mask")]
    if len(image) != 1 or len(mask) != 1:
        raise ValueError(f"Expected one orig*.nii[.gz] and one mask*.nii[.gz]; "
                         f"found {len(image)} CT files and {len(mask)} masks")
    return image[0], mask[0]
