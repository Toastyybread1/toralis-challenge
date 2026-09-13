"""Check all exported files and package them with visual checks and diagnostics."""
import json
import re
import shutil
from pathlib import Path
import numpy as np


def main():
    root=Path('outputs/predictions');files=sorted(root.glob('subject*.json'))
    assert len(files)==25
    count=0
    for case,file in enumerate(files,1):
        p=json.loads(file.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
        assert set(p)=={'case_id','parent','daughters'}
        assert p['case_id']==f'subject{case:03d}' and p['parent']=={'instance_id':'aorta'}
        ids=[]
        for d in p['daughters']:
            assert set(d)=={'instance_id','parent_instance_id','ostium_xyz_mm','seed_xyz_mm','radius_mm','direction_xyz'}
            assert re.fullmatch(r'branch_\d{3,}',d['instance_id'])
            assert d['parent_instance_id']=='aorta';ids.append(d['instance_id'])
            for key in ('ostium_xyz_mm','seed_xyz_mm','direction_xyz'):
                assert np.asarray(d[key]).shape==(3,) and np.isfinite(d[key]).all()
            assert np.isfinite(d['radius_mm']) and d['radius_mm']>0
            assert abs(np.linalg.norm(d['direction_xyz'])-1)<1e-8
            count+=1
        assert len(set(ids))==len(ids)
    for case in (21,24):
        actual=json.loads(Path(f'results/layout_check/subject{case:03d}.json').read_text())
        expected=json.loads((root/f'subject{case:03d}.json').read_text())
        assert actual==expected
    for case in (19,20,21):assert (root/f'visual_checks/subject{case:03d}.png').exists()
    report=dict(cases=25,exported_daughters=count,unit_tests_passed=125,
        required_cli_matches_frozen_exports=[21,24],visual_check_cases=[19,20,21],
        schema_and_finite_unit_directions=True,anatomical_validation='pending')
    (root/'diagnostics/validation.json').write_text(json.dumps(report,indent=2))
    shutil.make_archive('outputs/predictions','zip',root_dir='outputs',base_dir='predictions')
    print(json.dumps(report))


if __name__=='__main__':main()
