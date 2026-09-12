"""TEST FIXTURE ONLY: simulates successful execution with invalid JSON output."""
import argparse
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--image")
parser.add_argument("--aorta-mask")
parser.add_argument("--output")
parser.add_argument("--case-id")
args = parser.parse_args()
Path(args.output).write_text('{"case_id":"wrong_case","parent":{"instance_id":"aorta"},"daughters":[]}')
