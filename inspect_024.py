"""Compatibility entry point for Nika's geometry inspection.

Supply --image, --aorta-mask, --output-dir, and --resample to inspect and export
an orthogonal crop of any case, including subject024.
"""

from inspect_case import main


if __name__ == "__main__":
    raise SystemExit(main())
