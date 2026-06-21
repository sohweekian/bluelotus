#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from cio_context_capsule.builder import DEFAULT_DATASET, build_cio_context_capsule
from cio_context_capsule.validator import validate_cio_context_capsule


PROJECT_ROOT = Path(r"C:\bluelotus3")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure CIO Context Capsule is present before report rendering and validate rendered artifacts when available."
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--partial-ok", action="store_true")
    args = parser.parse_args(argv)
    dataset_path = Path(args.dataset)
    if not args.validate_only:
        manifest = build_cio_context_capsule(dataset_path=dataset_path)
        print(json.dumps({"build": manifest}, indent=2, ensure_ascii=False))
    result = validate_cio_context_capsule(dataset_path=dataset_path, partial_ok=args.partial_ok)
    print(json.dumps({"validation": result}, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in ("PASS", "WARNING") else 1


if __name__ == "__main__":
    raise SystemExit(main())
