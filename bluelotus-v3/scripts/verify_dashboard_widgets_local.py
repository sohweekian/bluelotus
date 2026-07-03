#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dashboard_widget_manager import ROOT, enabled_widgets, load_registry, verify_html


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local dashboard widget HTML")
    parser.add_argument("--html", help="Path to local generated index.html")
    args = parser.parse_args()
    registry = load_registry()
    html_path = Path(args.html) if args.html else ROOT / "data" / "debug_index_from_github.html"
    if not html_path.exists():
        print(f"FAIL local HTML missing: {html_path}")
        return 1
    html_text = html_path.read_text(encoding="utf-8")
    errors = verify_html(html_text, registry)
    for widget in enabled_widgets(registry):
        local_json = ROOT / str(widget["local_json_path"])
        if not local_json.exists():
            errors.append(f"missing local JSON: {local_json}")
        else:
            try:
                data = json.loads(local_json.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"invalid local JSON {local_json}: {exc}")
                continue
            for field in ("execution_authority", "order_routing_enabled", "llm_order_generation"):
                if field not in data:
                    errors.append(f"{local_json.name} missing safety field {field}")
            if "orders_generated" not in data:
                errors.append(f"{local_json.name} missing safety field orders_generated")
    marker_counts = {
        str(widget["marker_id"]): html_text.count(str(widget["marker_id"]))
        for widget in enabled_widgets(registry)
    }
    if errors:
        print("FAIL local dashboard widget verification")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS local dashboard widget verification")
    for marker, count in marker_counts.items():
        print(f"  {marker}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
