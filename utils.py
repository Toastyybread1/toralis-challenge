"""Compatibility imports for Nika's preprocessing scripts.

The implementation lives in src.preprocessing so inspection and detection use
the same validation, geometry handling, and interpolation rules.
"""

from src.preprocessing import read_nifti_pair

__all__ = ["read_nifti_pair"]
