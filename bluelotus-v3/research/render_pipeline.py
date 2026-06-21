"""
Render BlueLotus V3 pipeline flowchart as PNG using matplotlib.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BG        = "#0a0a0f"
COLORS = {
    "start":   ("#4fc3f7", "#000000"),
    "layer1":  ("#1a2a4a", "#aad4f5"),
    "export":  ("#16213e", "#aad4f5"),
    "layer2":  ("#1e0a3c", "#cdb4f7"),
    "layer3":  ("#2a0a3c", "#e0aaff"),
    "layer4":  ("#3c0a14", "#ffaaaa"),
    "layer5":  ("#0a2a3c", "#aaddff"),
    "layer6":  ("#0a2a16", "#aaffcc"),
}
ARROW = "#4fc3f7"

# --- layout constants ---
W, H = 24, 60          # figure size in inches
COL = 0.5              # single column x-center (normalised 0-1)
NODE_W = 0.60
NODE_H = 0.012
GAP    = 0.004
SECTION_H = 0.008

fig, ax = plt.subplots(figsize=(W, H), facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

nodes = []  # (label, color_key, y_centre)

# Build node list top → bottom (y goes 1 → 0)
# We'll place them with equal spacing

sections = [
    # (section_label, color_key, [node labels])
    ("▶  PIPELINE START", "start", ["Pipeline Start · Every 39 Minutes"]),
    ("LAYER 1 — DATA INGESTION", "layer1", [
        "fetch_analyst_targets",
        "fetch_capital_flow",
        "fetch_fundamentals",
        "fetch_treasury_yields",
        "fetch_cross_market_confirmation",
        "fetch_portfolio_readonly",
        "fetch_execution_records",
        "fetch_corporate_actions",
        "ingest.py  ·  Signals · News · Macro",
        "fetch_tech_publications",
        "fetch_conference_calendar",
        "fetch_ceo_appearances",
        "fetch_ticker_earnings",
        "fetch_catalyst_calendar",
        "fetch_historical_prices  ·  180d lookback",
        "historical_backfill_scheduler",
    ]),
    ("EXPORT & ARCHIVE", "export", [
        "export_dataset_raw.json",
        "archive_dataset_snapshot",
        "run_freshness_recovery",
        "export_dataset_raw v2",
    ]),
    ("LAYER 2 — ANALYTICAL ENGINES", "layer2", [
        "historical_risk_model  ·  VaR · Beta · Vol",
        "seed_cio_decision_journal",
        "seed_thesis_lifecycle",
        "record_cio_cognition",
        "run_monitoring_alerts",
        "institutional_quant_pipeline  ·  IQ Readiness Score",
        "run_deterministic_operators  ·  Operator Layer",
        "bluelotus_superforecast_engine  ·  Brier Forecasts",
        "forecast_resolution_tracker",
        "forecast_method_comparison",
    ]),
    ("LAYER 3 — GOVERNANCE", "layer3", [
        "build_chief_strategist_governance_pack",
        "build_chief_strategist_master_prompt",
        "build_cio_context_capsule",
        "governance_gate.py  ·  Approval Gate",
        "scenario_overlay_engine  ·  Geopolitical Overlay",
        "regression_tests",
    ]),
    ("LAYER 4 — REPORT GENERATION", "layer4", [
        "research_report_generator.py",
        "Bluelotus_V3_Report  ·  TXT · XLSX · DOCX",
        "validate_cio_context_capsule",
        "run_chief_strategist_reply_audit",
        "run_report_regression_audit",
        "acms_cop_db_loader  ·  SQL Database",
    ]),
    ("LAYER 5 — NITE-PEI ENGINE", "layer5", [
        "run_v3_grand_cycle  ·  V3.1–V3.4 Agents · 9 Reports",
        "run_nite_pei_cycle  ·  Bayesian Thesis · CKRI · Kelly · Advisory",
    ]),
    ("LAYER 6 — PUBLISH", "layer6", [
        "bluelotus_publisher.py",
        "GitHub Pages  ·  index.html Dashboard",
        "chief-strategist.html",
        "v3_agents_latest.json",
        "dataset_public.json",
        "chief_strategist_v17.txt",
    ]),
]

# Count total rows
total_rows = sum(1 + len(ns) for _, _, ns in sections)   # 1 header per section
margin_top = 0.01
margin_bot = 0.01
usable = 1.0 - margin_top - margin_bot
row_h = usable / total_rows

def draw_box(ax, y_cen, label, color_key, is_header=False):
    bg, fg = COLORS[color_key]
    lw = 1.5 if not is_header else 0
    alpha = 1.0
    bw = NODE_W
    bh = row_h * 0.78

    x0 = COL - bw / 2
    rect = FancyBboxPatch(
        (x0, y_cen - bh / 2), bw, bh,
        boxstyle="round,pad=0.002",
        linewidth=lw,
        edgecolor=ARROW if not is_header else "none",
        facecolor=bg,
        alpha=alpha,
        zorder=2,
    )
    ax.add_patch(rect)

    fs = 7.5 if not is_header else 8.5
    fw = "bold" if is_header else "normal"
    ax.text(COL, y_cen, label,
            ha="center", va="center", color=fg,
            fontsize=fs, fontweight=fw, zorder=3,
            fontfamily="monospace")
    return y_cen

y = 1.0 - margin_top
prev_y = None
all_y = []   # centre y for arrow drawing

for sec_label, ck, node_labels in sections:
    # section header
    y -= row_h / 2
    is_start = (ck == "start")
    draw_box(ax, y, sec_label, ck, is_header=(not is_start))
    all_y.append(y)
    if prev_y is not None:
        ax.annotate("", xy=(COL, y + row_h * 0.39),
                    xytext=(COL, prev_y - row_h * 0.39),
                    arrowprops=dict(arrowstyle="-|>", color=ARROW, lw=1.5),
                    zorder=1)
    prev_y = y
    y -= row_h

    for label in node_labels:
        y -= row_h / 2
        draw_box(ax, y, label, ck, is_header=False)
        all_y.append(y)
        ax.annotate("", xy=(COL, y + row_h * 0.39),
                    xytext=(COL, prev_y - row_h * 0.39),
                    arrowprops=dict(arrowstyle="-|>", color=ARROW, lw=1.5),
                    zorder=1)
        prev_y = y
        y -= row_h

# Title
fig.text(0.5, 0.995, "BlueLotus V3 — Full Pipeline Workflow",
         ha="center", va="top", color="#4fc3f7",
         fontsize=22, fontweight="bold", fontfamily="sans-serif")
fig.text(0.5, 0.990, "Automated intelligence pipeline  ·  Every 39 minutes  ·  65 steps",
         ha="center", va="top", color="#888888", fontsize=12)

# Legend
legend_items = [
    mpatches.Patch(facecolor=COLORS["layer1"][0], edgecolor=ARROW, label="Layer 1 — Data Ingestion"),
    mpatches.Patch(facecolor=COLORS["export"][0], edgecolor=ARROW, label="Export & Archive"),
    mpatches.Patch(facecolor=COLORS["layer2"][0], edgecolor=ARROW, label="Layer 2 — Analytical Engines"),
    mpatches.Patch(facecolor=COLORS["layer3"][0], edgecolor=ARROW, label="Layer 3 — Governance"),
    mpatches.Patch(facecolor=COLORS["layer4"][0], edgecolor=ARROW, label="Layer 4 — Report Generation"),
    mpatches.Patch(facecolor=COLORS["layer5"][0], edgecolor=ARROW, label="Layer 5 — NITE-PEI Engine"),
    mpatches.Patch(facecolor=COLORS["layer6"][0], edgecolor=ARROW, label="Layer 6 — Publish"),
]
leg = ax.legend(handles=legend_items, loc="lower right",
                facecolor="#12121f", edgecolor=ARROW,
                labelcolor="white", fontsize=9, framealpha=0.9)

out = r"C:\bluelotus3\research\pipeline_diagram.png"
fig.savefig(out, dpi=150, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
print(f"Saved: {out}")
