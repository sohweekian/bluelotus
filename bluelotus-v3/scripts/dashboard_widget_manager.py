from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = ROOT / "config" / "dashboard_widgets.yaml"


def registry_path() -> Path:
    configured = os.getenv("DASHBOARD_WIDGET_REGISTRY_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_REGISTRY


def load_registry(path: Path | None = None) -> Dict[str, Any]:
    selected = path or registry_path()
    with selected.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    validate_registry(data)
    return data


def validate_registry(registry: Dict[str, Any]) -> None:
    if not isinstance(registry, dict):
        raise ValueError("dashboard widget registry must be a mapping")
    if "widgets" not in registry or not isinstance(registry["widgets"], list):
        raise ValueError("dashboard widget registry missing widgets list")
    zone = registry.get("zone", {})
    for key in ("start_marker", "end_marker"):
        if not zone.get(key):
            raise ValueError(f"dashboard widget registry missing zone.{key}")
    marker_ids = [str(w.get("marker_id", "")) for w in registry["widgets"]]
    section_ids = [str(w.get("section_id", "")) for w in registry["widgets"]]
    for label, values in (("marker_id", marker_ids), ("section_id", section_ids)):
        non_empty = [v for v in values if v]
        if len(non_empty) != len(set(non_empty)):
            raise ValueError(f"duplicate dashboard widget {label}")
    required = {
        "widget_id",
        "section_id",
        "display_title",
        "enabled",
        "display_order",
        "marker_id",
        "json_endpoint",
        "local_json_path",
        "card_type",
        "renderer_script",
        "placement_zone",
        "refresh_interval_ms",
        "required_safety_footer",
        "fail_if_missing_json",
        "preserve_on_publish",
        "created_by",
        "schema_version",
    }
    for widget in registry["widgets"]:
        missing = sorted(required - set(widget))
        if missing:
            raise ValueError(f"dashboard widget missing required fields: {missing}")


def enabled_widgets(registry: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    data = registry or load_registry()
    return sorted(
        [w for w in data.get("widgets", []) if w.get("enabled") is True],
        key=lambda item: int(item.get("display_order", 0)),
    )


def zone_markers(registry: Dict[str, Any]) -> Tuple[str, str]:
    zone = registry["zone"]
    return str(zone["start_marker"]), str(zone["end_marker"])


def ensure_nojekyll(root: Path = ROOT) -> Path:
    path = root / ".nojekyll"
    if not path.exists():
        path.write_text("static dashboard\n", encoding="utf-8")
    return path


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def render_widget_card(widget: Dict[str, Any], registry: Dict[str, Any]) -> str:
    common = registry.get("common", {})
    base_url = str(common.get("base_url", "")).rstrip("/")
    status_colors = widget.get("status_colors", {})
    signal_colors = common.get("signal_colors", {})
    fallback_color = str(common.get("fallback_status_color", "#94a3b8"))
    marker_id = str(widget["marker_id"])
    title = str(widget["display_title"])
    endpoint = str(widget["json_endpoint"]).lstrip("/")
    refresh_ms = int(widget["refresh_interval_ms"])
    safety_footer = str(widget["required_safety_footer"])
    score_label = (
        "RISK SCORE (higher = more dangerous)"
        if "risk" in str(widget.get("card_type", "")).lower()
        else "THESIS SCORE"
    )
    border_color = fallback_color
    if status_colors:
        border_color = next(iter(status_colors.values()))

    return f"""
<div id="{_esc(marker_id)}" data-dashboard-widget="{_esc(widget['widget_id'])}" style="margin-bottom:16px">
  <div style="background:rgba(13,16,32,.60);border:1px solid {border_color}22;border-radius:12px;
    padding:14px 24px;color:#555;font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.12em">
    {_esc(title)} - loading...</div>
</div>
<script>
(function(){{
  var BASE={_json(base_url)};
  var ENDPOINT={_json(endpoint)};
  var REFRESH_MS={refresh_ms};
  var MARKER_ID={_json(marker_id)};
  var TITLE={_json(title)};
  var SAFETY_FOOTER={_json(safety_footer)};
  var STATUS_COLORS={_json(status_colors)};
  var SIGNAL_COLORS={_json(signal_colors)};
  var FALLBACK_COLOR={_json(fallback_color)};
  var SCORE_LABEL={_json(score_label)};
  var _lastData=null;
  function esc(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}}
  function colorFor(map,key){{return map[String(key||"").toUpperCase()]||FALLBACK_COLOR;}}
  function badge(label,col){{
    return '<span style="background:'+col+'22;color:'+col+';border-radius:4px;padding:2px 7px;font-size:10px;font-weight:700">'+esc(label)+'</span>';
  }}
  function chgStr(v){{
    if(v===null||v===undefined)return '<span style="color:#444">--</span>';
    var f=parseFloat(v);
    var col=f>0?"#4ade80":f<0?"#ff5566":"#94a3b8";
    return '<span style="color:'+col+'">'+(f>=0?"+":"")+f.toFixed(2)+"%</span>";
  }}
  function scoreColor(score,status){{return colorFor(STATUS_COLORS,status)||FALLBACK_COLOR;}}
  function render(d){{
    _lastData=d||{{}};
    var status=(d.status||"UNKNOWN").toUpperCase();
    var score=parseFloat(d.score)||0;
    var scoreMax=d.score_max||100;
    var scorePct=Math.min(100,Math.round((score/scoreMax)*100));
    var sc=scoreColor(score,status);
    var marketOpen=d.market_open===true;
    var marketStatus=d.market_status||"";
    var freshness=d.data_freshness_label||"";
    var marketTime=d.market_time_et||"";
    var lastSession=d.last_market_session||"";
    var addAllowed=d.add_allowed===true;
    var cioAction=d.cio_action||"CIO_REVIEW_REQUIRED";
    var byBasket={{}};
    (d.ticker_evidence||[]).forEach(function(t){{var g=t.group||"OTHER"; if(!byBasket[g])byBasket[g]=[]; byBasket[g].push(t);}});
    var html='<div style="background:rgba(13,16,32,.94);border:1px solid '+sc+'33;border-radius:12px;padding:18px 22px">'
      +(!marketOpen&&marketStatus?'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding:7px 12px;background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.18);border-radius:6px">'
        +'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#fbbf24;font-weight:700;letter-spacing:.12em">&#9679; MARKET CLOSED</span>'
        +'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.08em">'+esc(freshness)+(lastSession?' &middot; last session '+esc(lastSession):'')+'</span>'
        +(marketTime?'<span style="margin-left:auto;font-family:JetBrains Mono,monospace;font-size:9px;color:#444">'+esc(marketTime)+'</span>':'')+'</div>':'')
      +'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px"><div>'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:'+sc+';margin-bottom:4px">'+esc(TITLE)+'</div>'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:11px;color:#555">'+esc(d.last_updated_sgt||d.last_updated_utc||"")+'</div></div>'+badge(status,sc)+'</div>'
      +'<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em">'+esc(SCORE_LABEL)+'</span>'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:13px;font-weight:700;color:'+sc+'">'+score.toFixed(0)+' / '+scoreMax+'</span></div>'
      +'<div style="height:5px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden"><div style="height:100%;width:'+scorePct+'%;background:'+sc+';border-radius:3px;transition:width .6s ease"></div></div></div>'
      +'<div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;padding:8px 12px;background:rgba(255,255,255,.03);border-radius:8px">'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em">CIO ACTION</span>'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:13px;font-weight:700;color:#e2e8f0">'+esc(cioAction)+'</span>'
      +'<span style="margin-left:auto;font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em">ADD</span>'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:12px;font-weight:700;color:'+(addAllowed?"#4ade80":"#ff5566")+'">'+(addAllowed?"ALLOWED":"BLOCKED")+'</span></div>'
      +(d.summary?'<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#94a3b8;margin-bottom:12px">'+esc(d.summary)+'</div>':'');
    (d.primary_signals||[]).forEach(function(b){{
      var bId=b.basket||"";
      var sig=(b.signal||"UNKNOWN").toUpperCase();
      var bc=colorFor(SIGNAL_COLORS,sig);
      var rows=byBasket[bId]||[];
      html+='<div style="margin-bottom:12px;border:1px solid rgba(255,255,255,.05);border-radius:8px;overflow:hidden">'
        +'<div style="display:flex;align-items:center;gap:10px;padding:7px 12px;background:rgba(255,255,255,.03)">'
        +'<span style="font-family:JetBrains Mono,monospace;font-size:10px;color:#e2e8f0;font-weight:600;flex:1">'+esc(b.label||bId)+'</span>'
        +'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#444">wt '+esc(b.scoring_weight||0)+'</span>'+badge(sig,bc)+'</div>'
        +'<table style="width:100%;border-collapse:collapse">';
      rows.forEach(function(t){{
        var ts=(t.signal||"UNKNOWN").toUpperCase();
        var tc=colorFor(SIGNAL_COLORS,ts);
        var price=t.price?'$'+parseFloat(t.price).toFixed(2):'--';
        html+='<tr style="border-top:1px solid rgba(255,255,255,.04)">'
          +'<td style="padding:5px 12px;font-family:JetBrains Mono,monospace;font-size:11px;font-weight:700;color:#e2e8f0;width:86px">'+esc(t.display_symbol||t.ticker||t.yf_symbol||"")+'</td>'
          +'<td style="padding:5px 8px;font-family:JetBrains Mono,monospace;font-size:10px;color:#94a3b8;width:86px">'+price+'</td>'
          +'<td style="padding:5px 8px;font-family:JetBrains Mono,monospace;font-size:11px;font-weight:600">'+chgStr(t.day_change_pct)+'</td>'
          +'<td style="padding:5px 12px;text-align:right">'+badge(ts,tc)+'</td></tr>';
      }});
      if(!rows.length)html+='<tr><td colspan="4" style="padding:6px 12px;font-family:JetBrains Mono,monospace;font-size:10px;color:#444">no price data</td></tr>';
      html+='</table></div>';
    }});
    if(d.headline_evidence&&d.headline_evidence.length){{
      html+='<div style="margin-bottom:12px;padding:8px 12px;border:1px solid '+sc+'22;border-radius:8px"><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:'+sc+';letter-spacing:.1em;margin-bottom:4px">HEADLINE EVIDENCE</div>';
      d.headline_evidence.slice(0,3).forEach(function(h){{html+='<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#94a3b8;padding:2px 0">&#9642; '+esc(h.headline||h.title||"")+'</div>'; }});
      html+='</div>';
    }}
    if(d.escalation_evidence&&d.escalation_evidence.length){{
      html+='<div style="margin-bottom:12px;padding:8px 12px;border:1px solid rgba(255,85,102,.24);border-radius:8px"><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#ff5566;letter-spacing:.1em;margin-bottom:4px">ESCALATION EVIDENCE</div>';
      d.escalation_evidence.slice(0,3).forEach(function(h){{html+='<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#fca5a5;padding:2px 0">&#9642; '+esc(h.headline||h.title||"")+'</div>'; }});
      html+='</div>';
    }}
    if(d.false_positive_flags&&d.false_positive_flags.length){{
      html+='<div style="margin-bottom:12px;padding:8px 12px;border:1px solid rgba(251,191,36,.22);border-radius:8px"><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#fbbf24;letter-spacing:.1em;margin-bottom:4px">FALSE-POSITIVE FLAGS</div>';
      d.false_positive_flags.forEach(function(f){{html+='<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#fde68a;padding:2px 0">&#9642; '+esc(f.message||f.rule||"")+'</div>'; }});
      html+='</div>';
    }}
    if(d.external_evidence&&d.external_evidence.length){{
      html+='<div style="margin-bottom:12px;padding:8px 12px;border:1px solid rgba(148,163,184,.18);border-radius:8px"><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#94a3b8;letter-spacing:.1em;margin-bottom:4px">EXTERNAL EVIDENCE</div>';
      d.external_evidence.forEach(function(e){{
        var ec=e.blocks_add?"#ff5566":(e.available===false?"#64748b":"#60a5fa");
        html+='<div style="display:flex;gap:8px;align-items:center;font-family:JetBrains Mono,monospace;font-size:9px;color:#94a3b8;padding:2px 0"><span style="flex:1">'+esc(e.label||e.source||"")+'</span><span style="color:'+ec+';font-weight:700">'+esc(e.status||"UNKNOWN")+'</span></div>';
      }});
      html+='</div>';
    }}
    html+='<div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,.04);font-size:9px;color:#333;letter-spacing:.07em;font-family:JetBrains Mono,monospace">'+esc(SAFETY_FOOTER)+'</div></div>';
    document.getElementById(MARKER_ID).innerHTML=html;
  }}
  function load(){{
    fetch(BASE+"/"+ENDPOINT+"?t="+Date.now()).then(function(r){{return r.ok?r.json():Promise.reject(r.status);}}).then(render).catch(function(){{
      if(!_lastData)document.getElementById(MARKER_ID).innerHTML='<div style="background:rgba(13,16,32,.60);border:1px solid '+FALLBACK_COLOR+'22;border-radius:12px;padding:14px 24px;color:#555;font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.1em">'+esc(TITLE)+' - widget not yet running</div>';
    }});
  }}
  load();
  setInterval(load,REFRESH_MS);
}})();
</script>"""


def render_widget_zone(registry: Dict[str, Any] | None = None) -> str:
    data = registry or load_registry()
    start, end = zone_markers(data)
    body = "\n".join(render_widget_card(widget, data) for widget in enabled_widgets(data))
    return f"\n<!-- {start} -->\n{body}\n<!-- {end} -->\n"


def verify_html(html_text: str, registry: Dict[str, Any] | None = None) -> List[str]:
    data = registry or load_registry()
    start, end = zone_markers(data)
    errors: List[str] = []
    if f"<!-- {start} -->" not in html_text:
        errors.append(f"missing {start}")
    if f"<!-- {end} -->" not in html_text:
        errors.append(f"missing {end}")
    footer_idx = html_text.find("System Health")
    start_idx = html_text.find(f"<!-- {start} -->")
    end_idx = html_text.find(f"<!-- {end} -->")
    if footer_idx == -1:
        errors.append("missing System Health footer")
    if start_idx != -1 and footer_idx != -1 and start_idx > footer_idx:
        errors.append("widget zone appears after System Health")
    if start_idx != -1 and end_idx != -1 and start_idx > end_idx:
        errors.append("widget zone markers are nested incorrectly")
    for widget in enabled_widgets(data):
        marker = str(widget["marker_id"])
        count = html_text.count(marker)
        if count == 0:
            errors.append(f"missing enabled widget marker: {marker}")
        if count > 10:
            errors.append(f"unexpected duplicate marker references: {marker} count={count}")
    for widget in [w for w in data.get("widgets", []) if w.get("enabled") is not True]:
        marker = str(widget["marker_id"])
        if marker and marker in html_text:
            errors.append(f"disabled widget marker present: {marker}")
    return errors


def replace_or_insert_zone(html_text: str, registry: Dict[str, Any] | None = None, restore: bool = False) -> str:
    data = registry or load_registry()
    start, end = zone_markers(data)
    start_token = f"<!-- {start} -->"
    end_token = f"<!-- {end} -->"
    zone = render_widget_zone(data)
    start_idx = html_text.find(start_token)
    end_idx = html_text.find(end_token)
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        end_idx += len(end_token)
        return html_text[:start_idx] + zone + html_text[end_idx:]
    if not restore:
        raise ValueError("widget zone missing; rerun with recovery mode")
    anchor = "System Health"
    anchor_idx = html_text.find(anchor)
    if anchor_idx == -1:
        raise ValueError("System Health footer missing; cannot insert widget zone")
    div_idx = html_text.rfind("<div", 0, anchor_idx)
    insert_idx = div_idx if div_idx != -1 else anchor_idx
    return html_text[:insert_idx] + zone + html_text[insert_idx:]


def assert_publishable(html_text: str, registry: Dict[str, Any] | None = None) -> None:
    data = registry or load_registry()
    errors = verify_html(html_text, data)
    env_flag = os.getenv("FAIL_PUBLISH_IF_ENABLED_WIDGET_MISSING", "true").strip().lower()
    fail_closed = env_flag not in {"0", "false", "no", "off"}
    fail_closed = bool(data.get("zone", {}).get("fail_publish_if_enabled_widget_missing", fail_closed)) and fail_closed
    if errors and fail_closed:
        raise RuntimeError("dashboard widget verification failed: " + "; ".join(errors))
