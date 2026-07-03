from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
import ast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dashboard_widget_manager as widgets  # noqa: E402


def test_dashboard_widget_registry_exists_and_loads() -> None:
    registry = widgets.load_registry()
    assert registry["schema_version"] == "dashboard_widgets_v1.0"
    assert len(registry["widgets"]) >= 4


def test_s6_s7_s8_s9_registry_entries_present() -> None:
    registry = widgets.load_registry()
    ids = {item["widget_id"] for item in registry["widgets"]}
    assert {
        "ai_infra_power",
        "credit_refi_liquidity",
        "global_leverage_unwind",
        "oil_deescalation_peace_dividend",
    } <= ids


def test_enabled_widgets_have_required_marker_and_json() -> None:
    for widget in widgets.enabled_widgets():
        assert widget["marker_id"]
        assert widget["json_endpoint"]
        assert widget["local_json_path"]
        assert widget["preserve_on_publish"] is True


def test_duplicate_marker_ids_fail_registry_validation() -> None:
    registry = widgets.load_registry()
    broken = deepcopy(registry)
    broken["widgets"][1]["marker_id"] = broken["widgets"][0]["marker_id"]
    with pytest.raises(ValueError):
        widgets.validate_registry(broken)


def test_duplicate_section_ids_fail_registry_validation() -> None:
    registry = widgets.load_registry()
    broken = deepcopy(registry)
    broken["widgets"][1]["section_id"] = broken["widgets"][0]["section_id"]
    with pytest.raises(ValueError):
        widgets.validate_registry(broken)


def test_widget_zone_renders_all_enabled_markers_in_order() -> None:
    registry = widgets.load_registry()
    zone = widgets.render_widget_zone(registry)
    ordered = [item["marker_id"] for item in widgets.enabled_widgets(registry)]
    positions = [zone.index(marker) for marker in ordered]
    assert positions == sorted(positions)
    for marker in ordered:
        assert marker in zone
    assert [item["section_id"] for item in widgets.enabled_widgets(registry)] == ["S6", "S7", "S8", "S9"]


def test_widget_zone_contains_protected_markers() -> None:
    registry = widgets.load_registry()
    zone = widgets.render_widget_zone(registry)
    start, end = widgets.zone_markers(registry)
    assert f"<!-- {start} -->" in zone
    assert f"<!-- {end} -->" in zone


def test_verify_html_requires_s6_s7_s8_s9() -> None:
    registry = widgets.load_registry()
    html = "<main>" + widgets.render_widget_zone(registry) + "<div>System Health</div></main>"
    assert widgets.verify_html(html, registry) == []
    missing_s7 = html.replace("credit-refi-live", "credit-refi-missing")
    errors = widgets.verify_html(missing_s7, registry)
    assert any("credit-refi-live" in item for item in errors)
    missing_s9 = html.replace("oil-peace-dividend-live", "oil-peace-dividend-missing")
    errors = widgets.verify_html(missing_s9, registry)
    assert any("oil-peace-dividend-live" in item for item in errors)


def test_widget_zone_before_system_health() -> None:
    registry = widgets.load_registry()
    html = "<main>" + widgets.render_widget_zone(registry) + "<div>System Health</div></main>"
    assert widgets.verify_html(html, registry) == []
    wrong = "<main><div>System Health</div>" + widgets.render_widget_zone(registry) + "</main>"
    assert any("after System Health" in item for item in widgets.verify_html(wrong, registry))


def test_recovery_mode_inserts_missing_zone_before_system_health() -> None:
    registry = widgets.load_registry()
    html = "<main><section>Dashboard</section><div>System Health</div></main>"
    repaired = widgets.replace_or_insert_zone(html, registry, restore=True)
    assert widgets.verify_html(repaired, registry) == []
    assert repaired.index("THESIS_WIDGETS_START") < repaired.index("System Health")


def test_non_recovery_refuses_missing_zone() -> None:
    registry = widgets.load_registry()
    html = "<main><section>Dashboard</section><div>System Health</div></main>"
    with pytest.raises(ValueError):
        widgets.replace_or_insert_zone(html, registry, restore=False)


def test_assert_publishable_fails_when_enabled_marker_missing() -> None:
    registry = widgets.load_registry()
    html = "<main>" + widgets.render_widget_zone(registry) + "<div>System Health</div></main>"
    broken = html.replace("global-leverage-live", "global-leverage-missing")
    with pytest.raises(RuntimeError):
        widgets.assert_publishable(broken, registry)


def test_nojekyll_exists_or_is_created() -> None:
    path = widgets.ensure_nojekyll(ROOT)
    assert path.exists()


def test_publisher_is_wired_to_widget_guard() -> None:
    source = (ROOT / "mid" / "bluelotus_publisher.py").read_text(encoding="utf-8")
    assert "render_widget_zone" in source
    assert "assert_publishable" in source
    assert "ensure_nojekyll" in source


def test_manager_has_no_broker_or_llm_dependency() -> None:
    source = (ROOT / "scripts" / "dashboard_widget_manager.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = ["openai", "anthropic", "ollama", "qwen", "moomoo", "futu", "place_order", "execute_order"]
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            if module != "__future__":
                imports.append(module)
    for token in forbidden:
        assert all(token not in item for item in imports)
        assert token not in source.lower().replace("__future__", "")


def test_manager_has_no_protected_v2_path_reference() -> None:
    source = (ROOT / "scripts" / "dashboard_widget_manager.py").read_text(encoding="utf-8").lower()
    assert "c:\\bluelotus2" not in source
