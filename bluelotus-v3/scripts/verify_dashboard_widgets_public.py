#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request

from dashboard_widget_manager import enabled_widgets, load_registry, verify_html


def fetch_text(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "BlueLotus-Dashboard-Widget-Verifier/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8")


def main() -> int:
    registry = load_registry()
    zone = registry.get("zone", {})
    common = registry.get("common", {})
    homepage = str(zone.get("public_homepage_url") or common.get("base_url") or "").rstrip("/") + "/"
    errors: list[str] = []
    try:
        status, html = fetch_text(homepage)
        if status != 200:
            errors.append(f"homepage returned HTTP {status}")
    except Exception as exc:
        print("FAIL public dashboard widget verification")
        print(f"  - homepage fetch failed: {exc}")
        return 1
    errors.extend(verify_html(html, registry))
    base = str(common.get("base_url", "")).rstrip("/")
    for widget in enabled_widgets(registry):
        endpoint = str(widget["json_endpoint"]).lstrip("/")
        url = f"{base}/{endpoint}"
        try:
            status, body = fetch_text(url)
            if status != 200:
                errors.append(f"{endpoint} returned HTTP {status}")
                continue
            data = json.loads(body)
        except Exception as exc:
            errors.append(f"{endpoint} fetch/parse failed: {exc}")
            continue
        for field in ("execution_authority", "order_routing_enabled", "llm_order_generation"):
            if field not in data:
                errors.append(f"{endpoint} missing safety field {field}")
        if "orders_generated" not in data:
            errors.append(f"{endpoint} missing safety field orders_generated")
    if "System Health" not in html:
        errors.append("System Health footer missing")
    if errors:
        print("FAIL public dashboard widget verification")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS public dashboard widget verification")
    for widget in enabled_widgets(registry):
        print(f"  {widget['section_id']} {widget['marker_id']} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
