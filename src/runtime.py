"""CPU limits shared by command-line entry points; import before NumPy/ITK."""

import os
import platform


def limit_cpu_threads():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"):
        os.environ[name] = "4"


def peak_rss_mb():
    """Peak resident memory on macOS/Linux; unavailable platforms report null."""
    try:
        import resource
    except ImportError:
        return None
    divisor = 1e6 if platform.system() == "Darwin" else 1000
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor
