"""Join optional review sidecars by IDs, never list order; keep export unchanged."""
import json
import math
from pathlib import Path
from .contract import vector


def load_path_evidence(prediction_file, prediction):
    file = Path(prediction_file)
    audit_file = file.parent / 'diagnostics' / file.name
    review_file = file.parent / (file.stem + '_review') / 'predictions.json'
    if not audit_file.exists() and not review_file.exists():
        return {}, 'No review sidecars: markers only; no centerline reconstruction.'
    if not audit_file.is_file() or not review_file.is_file():
        raise ValueError('Incomplete review sidecars: keep the diagnostics and review folder with the JSON.')
    audit = json.loads(audit_file.read_text(encoding='utf-8-sig'))
    review = json.loads(review_file.read_text(encoding='utf-8-sig'))
    mappings = {}
    for item in audit['candidates']:
        if item.get('exclusion_reason') is None and 'instance_id' in item:
            if item['instance_id'] in mappings:
                raise ValueError('Duplicate exported ID in diagnostics')
            mappings[item['instance_id']] = item['source_candidate']
    reps = {}
    for group in review['review_groups']:
        rep = group['representative']
        if rep['instance_id'] in reps:
            raise ValueError('Duplicate source candidate in review')
        reps[rep['instance_id']] = rep
    paths = {}
    for branch in prediction['daughters']:
        name = branch['instance_id']
        if name not in mappings or mappings[name] not in reps:
            raise ValueError(f'Missing actual path for {name}')
        rep = reps[mappings[name]]
        for key in ('ostium_xyz_mm', 'seed_xyz_mm', 'direction_xyz'):
            if math.dist(vector(rep[key], key), branch[key]) > 1e-4:
                raise ValueError(f'Stale review sidecars: {name} {key} disagrees')
        if abs(float(rep['radius_mm']) - branch['radius_mm']) > 1e-4:
            raise ValueError(f'Stale review radius for {name}')
        points = [vector(p, 'path_xyz_mm') for p in rep['path_xyz_mm']]
        if len(points) < 2 or math.dist(points[0], branch['ostium_xyz_mm']) > 1e-4:
            raise ValueError(f'Invalid path start for {name}')
        arc = [0.0]
        for a, b in zip(points, points[1:]):
            arc.append(arc[-1] + math.dist(a, b))
        if arc[-1] < 5 - 1e-5 or arc[-1] > 10.1:
            raise ValueError(f'Invalid proximal path length for {name}')
        for i in range(1, len(points)):
            if arc[i] >= 5 - 1e-5 and arc[i] > arc[i-1]:
                t = min(1., (5 - arc[i-1]) / (arc[i] - arc[i-1]))
                seed = [a + t*(b-a) for a, b in zip(points[i-1], points[i])]
                if math.dist(seed, branch['seed_xyz_mm']) > .1:
                    raise ValueError(f'Path seed disagrees for {name}')
                break
        paths[name] = dict(source_candidate=mappings[name], path_xyz_mm=points,
                           path_length_mm=arc[-1], tracking_status=rep.get('tracking_status'),
                           stop_reason=rep.get('stop_reason'))
    status = review.get('neural', {}).get('status', 'unknown')
    return paths, f'Neural evidence: {status}. Traces are estimates, not segmented vessel walls.'
