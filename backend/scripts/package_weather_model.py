"""Provision a trusted local package; run from backend with PYTHONPATH=src."""
import argparse
import json
from pathlib import Path

from tfield.weather_runtime import model_root, package_models


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--model-id', type=int, required=True)
    parser.add_argument('--schema', choices=['two', 'full'], required=True)
    parser.add_argument('--bounds', type=Path, help='Optional JSON mapping external feature names to [min,max]')
    args = parser.parse_args()
    result = package_models(model_root(), args.current, args.history, args.artifact,
                            args.model_id, args.schema,
                            json.loads(args.bounds.read_text('utf-8')) if args.bounds else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
