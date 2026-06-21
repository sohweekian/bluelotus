#!/usr/bin/env python3
"""
inject_s6_card.py — Inject S6 AI Infrastructure widget card into GitHub Pages index.html
"""
import base64
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

# Load token from .env
env_path = BASE_DIR / ".env"
token = ""
for line in env_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("GITHUB_TOKEN="):
        token = line.split("=", 1)[1].strip()

if not token:
    print("FATAL: GITHUB_TOKEN not found in .env")
    sys.exit(1)

import urllib.request

def gh_get(path):
    url = f"https://api.github.com/repos/sohweekian/bluelotus/contents/{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def gh_put(path, content_bytes, sha, message):
    url = f"https://api.github.com/repos/sohweekian/bluelotus/contents/{path}"
    body = json.dumps({
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "sha": sha,
        "branch": "main",
    }).encode()
    req = urllib.request.Request(url, data=body, method="PUT", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())
    return resp["content"]["sha"]

# Fetch current index.html
print("Fetching index.html from GitHub Pages...")
resp = gh_get("index.html")
sha = resp["sha"]
html = base64.b64decode(resp["content"]).decode("utf-8")
print(f"  SHA={sha}  Size={len(html)} chars")

# --- Build S6 card HTML/JS ---
S6_CARD = """
<div id="ai-infra-live" style="margin-bottom:16px">
  <div style="background:rgba(13,16,32,.60);border:1px solid rgba(52,211,153,.12);border-radius:12px;
    padding:14px 24px;color:#444;font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.12em">
    S6 · AI INFRASTRUCTURE / POWER — loading…</div>
</div>
<script>
(function(){
  var BASE="https://sohweekian.github.io/bluelotus";
  var REFRESH_MS=600000;
  var _lastData=null;
  function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
  var SC={"CONFIRMING":"#4ade80","WATCH":"#fbbf24","MIXED":"#fb923c","WEAKENING":"#f97316",
    "CONTRADICTED":"#ff5566","UNKNOWN":"#94a3b8"};
  var SIG={"PASS":"#4ade80","WATCH":"#fbbf24","FAIL":"#ff5566","UNKNOWN":"#94a3b8"};
  function badge(label,col){
    return'<span style="background:'+col+'22;color:'+col+';border-radius:4px;padding:2px 7px;'
      +'font-size:10px;font-weight:700">'+esc(label)+'</span>';
  }
  function render(d){
    _lastData=d;
    var status=(d.status||"UNKNOWN").toUpperCase();
    var score=parseFloat(d.score)||0;
    var scoreMax=d.score_max||100;
    var conf=d.confidence||"UNKNOWN";
    var cioAction=d.cio_action||"CIO_REVIEW_REQUIRED";
    var addAllowed=d.add_allowed===true;
    var ts=d.last_updated_sgt||d.last_updated_utc||"";
    var sc=SC[status]||"#94a3b8";
    var scorePct=Math.min(100,Math.round((score/scoreMax)*100));
    var barColor=score>=75?"#4ade80":score>=55?"#fbbf24":score>=40?"#fb923c":"#ff5566";
    var html='<div style="background:rgba(13,16,32,.94);border:1px solid rgba(52,211,153,.18);border-radius:12px;padding:18px 22px">'
      +'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">'
      +'<div><div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;'
      +'text-transform:uppercase;color:#34d399;margin-bottom:4px">S6 · AI INFRASTRUCTURE / POWER BOTTLENECK</div>'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:11px;color:#555">'+esc(ts)+'</div>'
      +'</div>'+badge(status,sc)+'</div>'
      +'<div style="margin-bottom:14px">'
      +'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em">THESIS SCORE</span>'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:13px;font-weight:700;color:'+barColor+'">'+score.toFixed(0)+' / '+scoreMax+'</span>'
      +'</div>'
      +'<div style="height:6px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden">'
      +'<div style="height:100%;width:'+scorePct+'%;background:'+barColor+';border-radius:3px;transition:width .6s ease"></div>'
      +'</div></div>'
      +'<div style="display:flex;gap:8px;align-items:center;margin-bottom:14px;'
      +'padding:8px 12px;background:rgba(255,255,255,.03);border-radius:8px">'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em">CIO ACTION</span>'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:13px;font-weight:700;color:#e2e8f0">'+esc(cioAction)+'</span>'
      +'<span style="margin-left:auto;font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em">ADD</span>'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:12px;font-weight:700;color:'+(addAllowed?"#4ade80":"#ff5566")+'">'+(addAllowed?"ALLOWED":"BLOCKED")+'</span>'
      +'</div>'
      +'<div style="margin-bottom:14px">'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em;margin-bottom:6px">BASKET SIGNALS</div>'
      +'<div style="display:grid;grid-template-columns:1fr auto;gap:4px 12px">';
    (d.primary_signals||[]).forEach(function(b){
      var sig=(b.signal||"UNKNOWN").toUpperCase();
      var bc=SIG[sig]||"#94a3b8";
      html+='<span style="font-family:JetBrains Mono,monospace;font-size:10px;color:#94a3b8">'+esc(b.label||b.basket)+'</span>'+badge(sig,bc);
    });
    html+='</div></div>'
      +'<div style="margin-bottom:12px">'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em;margin-bottom:4px">TOP MOVERS</div>'
      +'<table style="width:100%;border-collapse:collapse;font-size:10px;font-family:JetBrains Mono,monospace">'
      +'<tr style="color:#444"><td style="padding:2px 6px">TICKER</td>'
      +'<td style="padding:2px 6px;text-align:right">PRICE</td>'
      +'<td style="padding:2px 6px;text-align:right">CHG%</td>'
      +'<td style="padding:2px 6px;text-align:right">vs SPY</td>'
      +'<td style="padding:2px 6px;text-align:center">SIG</td></tr>';
    (d.ticker_evidence||[]).slice(0,8).forEach(function(t){
      var sig=(t.signal||"UNKNOWN").toUpperCase();
      var tc=SIG[sig]||"#94a3b8";
      var chg=t.day_change_pct;
      var chgStr=chg!=null?(chg>=0?"+":"")+parseFloat(chg).toFixed(2)+"%":"--";
      var chgCol=chg>0?"#4ade80":chg<0?"#ff5566":"#94a3b8";
      var rspy=t.relative_to_spy;
      var rspyStr=rspy!=null?(rspy>=0?"+":"")+parseFloat(rspy).toFixed(2):"--";
      html+='<tr style="border-bottom:1px solid rgba(255,255,255,.03)">'
        +'<td style="padding:3px 6px;color:#e2e8f0;font-weight:700">'+esc(t.ticker)+'</td>'
        +'<td style="padding:3px 6px;text-align:right;color:#cbd5e1">$'+parseFloat(t.price||0).toFixed(2)+'</td>'
        +'<td style="padding:3px 6px;text-align:right;color:'+chgCol+'">'+chgStr+'</td>'
        +'<td style="padding:3px 6px;text-align:right;color:#94a3b8">'+rspyStr+'</td>'
        +'<td style="padding:3px 6px;text-align:center">'+badge(sig,tc)+'</td></tr>';
    });
    html+='</table></div>';
    if(d.headline_score>0&&d.headline_evidence&&d.headline_evidence.length>0){
      html+='<div style="margin-bottom:12px">'
        +'<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#555;letter-spacing:.1em;margin-bottom:4px">NEWS CATALYST</div>';
      d.headline_evidence.slice(0,3).forEach(function(h){
        html+='<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#94a3b8;padding:2px 0">▪ '+esc(h.headline||h.text||"")+'</div>';
      });
      html+='</div>';
    }
    html+='<div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,.04);'
      +'font-size:9px;color:#333;letter-spacing:.07em;font-family:JetBrains Mono,monospace">'
      +'EXECUTION: CIO_ONLY_MANUAL &nbsp;·&nbsp; ORDER_ROUTING: DISABLED &nbsp;·&nbsp; '
      +'THESIS: AI_INFRASTRUCTURE_POWER_THESIS v1.0</div></div>';
    document.getElementById("ai-infra-live").innerHTML=html;
  }
  function load(){
    fetch(BASE+"/data/thesis_widgets/ai_infrastructure_power_latest.json?t="+Date.now())
      .then(function(r){return r.ok?r.json():Promise.reject(r.status);})
      .then(render)
      .catch(function(){
        if(!_lastData){
          document.getElementById("ai-infra-live").innerHTML=
            '<div style="background:rgba(13,16,32,.60);border:1px solid rgba(52,211,153,.10);'
            +'border-radius:12px;padding:14px 24px;color:#555;font-family:JetBrains Mono,monospace;'
            +'font-size:10px;letter-spacing:.1em">S6 · AI INFRASTRUCTURE / POWER — widget not yet running '
            +'&nbsp;·&nbsp; <a href="javascript:location.reload()" style="color:#34d399;text-decoration:none">retry</a></div>';
        }
      });
  }
  load();
  setInterval(load, REFRESH_MS);
})();
</script>
"""

# Find the insertion anchor: just before System Health div
SYS_HEALTH_MARKER = '<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#555;padding:10px 0 4px;border-top:1px solid rgba(255,255,255,.05);'

if SYS_HEALTH_MARKER not in html:
    print("FATAL: Could not find System Health anchor in index.html")
    sys.exit(1)

# Check S6 not already injected
if "ai-infra-live" in html:
    print("S6 card already present in index.html — skipping injection")
    sys.exit(0)

# Inject S6 card before System Health div
new_html = html.replace(SYS_HEALTH_MARKER, S6_CARD + "\n" + SYS_HEALTH_MARKER, 1)
print(f"  Injected S6 card. New size = {len(new_html)} chars (+{len(new_html)-len(html)})")

# Push to GitHub
print("Pushing updated index.html to GitHub Pages...")
new_sha = gh_put("index.html", new_html.encode("utf-8"), sha, "feat: add S6 AI Infrastructure / Power Bottleneck thesis widget card")
print(f"  Pushed OK. New SHA = {new_sha}")
print("Dashboard live: https://sohweekian.github.io/bluelotus/")
