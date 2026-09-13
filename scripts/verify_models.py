"""Verify only packaged inference checkpoints; no labels, training, or inference."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT))
    import torch
    from src.rebuild.learned_segmentation import SmallUNet
    manifest = json.loads((ROOT / 'config/models-manifest.json').read_text())
    checkpoints = 0
    for item in manifest['files']:
        path = ROOT / item['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError(f'Missing or modified model artifact: {path}')
        if path.suffix != '.pt':
            continue
        saved = torch.load(path, map_location='cpu', weights_only=True)
        fold = int(path.parent.name.rsplit('_', 1)[1])
        if saved['held_out_case'] != fold or set(saved['training_cases']) != set(range(19, 24)) - {fold}:
            raise RuntimeError(f'Invalid held-out provenance: {path}')
        SmallUNet().load_state_dict(saved['state_dict'], strict=True)
        checkpoints += 1
    if checkpoints != 10:
        raise RuntimeError('Expected ten supplied checkpoints')
    print(f'Verified {checkpoints} CPU checkpoints and manifests; torch={torch.__version__}')


if __name__ == '__main__':
    main()
