"""TEST FIXTURE ONLY: validates GUI process wiring; does not detect branches."""
import argparse
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser()
parser.add_argument("--image", required=True)
parser.add_argument("--aorta-mask", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--case-id")
args = parser.parse_args()
assert Path(args.image).is_file() and Path(args.aorta_mask).is_file()
time.sleep(.5)
Path(args.output).write_text(json.dumps({"case_id": args.case_id or Path(args.image).parent.name, "parent": {"instance_id": "aorta"}, "daughters": []}))
print("TEST FIXTURE ONLY: completed with empty results")
