#!/usr/bin/env python3
"""
Patch a sanitized BlueLotus V2 payload for macOS packaging.

The Windows production tree is left untouched. This script only modifies the
copied payload inside the macOS installer build folder.
"""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT_REPLACEMENT = "Path(__file__).resolve().parents[1]"


def patch_text(path: Path, text: str) -> tuple[str, bool]:
    original = text
    text = text.replace(
        'DEFAULT_DATASET = Path(r"C:\\bluelotus2\\data\\frontend\\dataset_raw.json")',
        'DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "data" / "frontend" / "dataset_raw.json"',
    )
    text = text.replace('Path(r"C:\\bluelotus2")', ROOT_REPLACEMENT)
    text = text.replace("Path(r'C:\\bluelotus2')", ROOT_REPLACEMENT)
    text = text.replace('Path("C:\\\\bluelotus2")', ROOT_REPLACEMENT)
    text = text.replace("Path('C:\\\\bluelotus2')", ROOT_REPLACEMENT)
    text = text.replace('return Path(r"C:\\bluelotus2")', f"return {ROOT_REPLACEMENT}")
    text = text.replace("return Path(r'C:\\bluelotus2')", f"return {ROOT_REPLACEMENT}")
    text = text.replace('else r"C:\\bluelotus2"', "else os.path.dirname(SCRIPT_DIR)")

    if path.name == "generate_improvements_report.py":
        text = text.replace('Path(r"C:\\bluelotus2\\research")', "Path(__file__).resolve().parent")
        text = text.replace("Path(r'C:\\bluelotus2\\research')", "Path(__file__).resolve().parent")
    if path.name == "news_channel_feed_generator.py":
        text = text.replace(
            'WINDOWS_INPUT = r"C:\\bluelotus2\\data\\frontend\\dataset_raw.json"',
            'PROJECT_ROOT = Path(__file__).resolve().parents[1]\nWINDOWS_INPUT = str(PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json")',
        )
        text = text.replace(
            'WINDOWS_OUTPUT = r"C:\\bluelotus2\\news\\news_channel_feed.txt"',
            'WINDOWS_OUTPUT = str(PROJECT_ROOT / "news" / "news_channel_feed.txt")',
        )
        text = text.replace('if os.path.exists(r"C:\\bluelotus2"):', 'if os.path.exists(str(PROJECT_ROOT)):')

    return text, text != original


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload_root", help="Path to copied payload/bluelotus2")
    args = ap.parse_args()
    root = Path(args.payload_root)
    if not root.exists():
        print(f"[FAIL] payload root missing: {root}")
        return 2

    patched = 0
    for path in list((root / "mid").glob("*.py")) + list((root / "research").glob("*.py")) + list((root / "news").glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        new_text, changed = patch_text(path, text)
        if changed:
            path.write_text(new_text, encoding="utf-8")
            patched += 1

    print(f"[OK] macOS payload path patches applied: {patched} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
