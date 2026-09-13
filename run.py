"""Stable CLI dispatch. Importing this module never executes a pipeline."""
import sys
import os


def main(argv=None):
    for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[name]='4'
    os.environ['CUDA_VISIBLE_DEVICES']=''
    args=list(sys.argv[1:] if argv is None else argv)
    if '--document-review' in args:
        args.remove('--document-review')
        args=['--parent' if a=='--aorta-mask' else
              '--parent='+a.split('=',1)[1] if a.startswith('--aorta-mask=') else a for a in args]
        from src.rebuild.review_pipeline import main as entry
        print('Detector: document-review pipeline. CPU neural evidence: '+
              ('enabled' if '--neural' in args else 'disabled (use --neural for the evaluated configuration).'),file=sys.stderr)
    else:
        from src.rebuild.challenge_output import main as entry
        print('Detector: current CPU review pipeline with challenge-format JSON export.',file=sys.stderr)
    original=sys.argv
    try:
        sys.argv=[original[0],*args]
        return entry()
    finally:
        sys.argv=original


if __name__=='__main__':
    raise SystemExit(main())
