"""Prepare readable display filenames without modifying supplied medical files."""
from pathlib import Path
import shutil
import uuid


def display_input_path(path, cache_directory):
    source = Path(path)
    with source.open('rb') as stream:
        compressed = stream.read(2) == b'\x1f\x8b'
    if compressed and not source.name.lower().endswith('.gz'):
        target = Path(cache_directory) / (uuid.uuid4().hex + '.nii.gz')
        shutil.copyfile(source, target)
        return str(target)
    return str(source)
