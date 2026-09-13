"""Export frozen automatic groups; references are read only after export."""
import json
from pathlib import Path
from src.rebuild.challenge_output import write_case
from src.rebuild.report_review_pipeline import pooled
from src.evaluate_predictions import compare


def main():
    source=Path('results/aortic_tree_verified');output=Path('outputs/predictions');rows=[]
    for folder in sorted(source.glob('subject*')):
        if not folder.is_dir():continue
        case=int(folder.name[-3:]);result=json.loads((folder/'predictions.json').read_text())
        pred,audit=write_case(result,folder.name,output/(folder.name+'.json'))
        row={'case':case,'daughters':len(pred['daughters']),'review_groups':len(result['review_groups']),
             'excluded':sum(v['exclusion_reason'] is not None for v in audit['candidates'])}
        if 19<=case<=23:
            reference=json.loads(Path(f'references/border_results/case_{case}/inputs/annotations.json').read_text())
            row['agreement_3mm']=compare(pred,reference,3.)
        rows.append(row)
    report={'cases':rows,'development_agreement_3mm':pooled(rows,'agreement_3mm')}
    (output/'diagnostics/export_summary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
