"""Isolated four-thread CPU runs, followed by draft-reference evaluation.

The parent process measures whole child wall time including Python startup,
imports, loading, inference and outputs. Windows peak working set is reported.
No reference is supplied to infer(); held-out case selects existing model folds.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def peak_memory_mb():
    if os.name!='nt':
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in (
            'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
            'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    c=Counters();c.cb=ctypes.sizeof(c)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb):return None
    return c.PeakWorkingSetSize/1024**2


def worker(case,output,neural,face_origins=False,local_flood=True,adaptive_rescue=True,aortic_tree_review=True):
    import numpy as np
    import SimpleITK as sitk
    from src.rebuild.review_pipeline import infer,save_result
    from src.evaluate_predictions import compare
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    source=Path('data/TORALIS CHALLENGE')/f'subject{case:03d}'
    start=time.perf_counter()
    result,data=infer(source/f'orig{case}.nii',source/f'mask{case}.nii',neural,case if 19<=case<=23 else None,
                      face_origins=face_origins,local_flood=local_flood,adaptive_rescue=adaptive_rescue,aortic_tree_review=aortic_tree_review)
    save_result(result,data,output)
    # Verify persisted grid and values, including the case-24 transformed parent.
    reopened=sitk.ReadImage(str(output/'parent.nii.gz'))
    checks={'parent_roundtrip':bool(np.array_equal(sitk.GetArrayFromImage(reopened)>0,data['parent'])),
            'growth_excludes_parent':not bool(np.any(data['added']&data['parent'])),
            'growth_in_valid_CT_support':not bool(np.any(data['added']&~data['valid_support'])),
            'geometry_preserved':all(np.allclose(getattr(reopened,k)(),getattr(data['roi'],k)()) for k in ('GetSize','GetSpacing','GetOrigin','GetDirection'))}
    row={'case':case,'seed_candidates':len(result['seed_candidates']),
         'review_groups':len(result['review_groups']),
         'deferred_groups':len(result.get('deferred_groups',[])),
         'length_complete_candidates':sum(p['tracking_status']=='length_complete' for p in result['seed_candidates']),
         'approved_daughters':0,'checks':checks,'loading':result['loading'],
         'neural_status':result['neural']['status'],'timing':result['timing'],
         'worker_seconds_including_save':time.perf_counter()-start,'peak_working_set_mb':peak_memory_mb()}
    # All model outputs are already written before draft references are read.
    if 19<=case<=23:
        reference=json.loads((Path('references/border_results')/f'case_{case}'/'inputs/annotations.json').read_text())
        row['draft_reference_agreement']={str(t):compare({'daughters':result['seed_candidates']},reference,t) for t in (2.,3.,5.)}
        row['complete_path_agreement_3mm']=compare({'daughters':[p for p in result['seed_candidates'] if p['tracking_status']=='length_complete']},reference,3.)
        row['review_group_agreement_3mm']=compare({'daughters':[g['representative'] for g in result['review_groups']]},reference,3.)
        row['pre_tree_group_agreement_3mm']=compare({'daughters':[g['representative'] for g in result['pre_tree_review_groups']]},reference,3.)
    (output/'metrics.json').write_text(json.dumps(row,indent=2,allow_nan=False))
    print(json.dumps(row),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',nargs='+',type=int,default=list(range(1,26)))
    parser.add_argument('--output',type=Path,default=Path('rebuild/document_pipeline_results'))
    parser.add_argument('--neural',action='store_true');parser.add_argument('--worker',type=int)
    parser.add_argument('--experimental-face-origins',action='store_true')
    parser.add_argument('--local-flood',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--adaptive-rescue',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--aortic-tree-review',action=argparse.BooleanOptionalAction,default=True)
    args=parser.parse_args()
    if args.worker is not None:
        args.output.mkdir(parents=True,exist_ok=True);worker(args.worker,args.output,args.neural,args.experimental_face_origins,args.local_flood,args.adaptive_rescue,args.aortic_tree_review);return
    args.output.mkdir(parents=True,exist_ok=True);rows=[]
    env={**os.environ,'OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4','CUDA_VISIBLE_DEVICES':''}
    for case in args.cases:
        out=args.output/f'subject{case:03d}';start=time.perf_counter()
        cmd=[sys.executable,'-m','src.rebuild.run_review_pipeline','--worker',str(case),'--output',str(out)]
        if args.neural:cmd.append('--neural')
        if args.experimental_face_origins:cmd.append('--experimental-face-origins')
        cmd.append('--local-flood' if args.local_flood else '--no-local-flood')
        cmd.append('--adaptive-rescue' if args.adaptive_rescue else '--no-adaptive-rescue')
        cmd.append('--aortic-tree-review' if args.aortic_tree_review else '--no-aortic-tree-review')
        try:
            proc=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=300)
            out.mkdir(parents=True,exist_ok=True);(out/'run.log').write_text(proc.stdout+proc.stderr)
            if proc.returncode:row={'case':case,'error':proc.stderr[-2000:]}
            else:row=json.loads((out/'metrics.json').read_text())
        except subprocess.TimeoutExpired:
            row={'case':case,'error':'300 second timeout; incomplete output must not be used'}
        row['whole_process_seconds']=time.perf_counter()-start
        row['within_60_seconds']=row['whole_process_seconds']<=60 and 'error' not in row
        rows.append(row);(args.output/'summary.json').write_text(json.dumps(rows,indent=2))
        print(json.dumps(row),flush=True)


if __name__=='__main__':main()
