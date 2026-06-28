# -*- coding: utf-8 -*-
import re, html, markdown

SRC = r"C:\bluelotus3\research\Claude_Code_Software_Engineering_Thesis.md"
TPL = "bgtm-thesis.html"
OUT = "agentic-turn-thesis.html"

AUTHOR = "Emeritus Professor Dr. Claude Code"
TITLE = "The Agentic Turn"
SUBTITLE = "Claude Code and the Reconfiguration of Software-Engineering Labour, 2020–2030"

with open(SRC, "r", encoding="utf-8") as f:
    md = f.read()

# Normalize line endings
md = md.replace("\r\n", "\n")
lines = md.split("\n")

# --- Split front matter from body at "# Chapter 1" ---
body_start = None
for i, ln in enumerate(lines):
    if re.match(r"^#\s+Chapter\s+1\b", ln):
        body_start = i
        break
assert body_start is not None, "Chapter 1 heading not found"

front = lines[:body_start]
body_lines = lines[body_start:]

# --- Extract abstract paragraphs and keywords from front matter ---
abstract_paras = []
keywords_line = ""
in_abstract = False
for ln in front:
    s = ln.strip()
    if re.match(r"^#{1,3}\s+Abstract\b", s, re.I):
        in_abstract = True
        continue
    if in_abstract:
        if s.startswith("#"):
            in_abstract = False
        elif re.match(r"^\*\*?Keywords", s, re.I) or s.lower().startswith("keywords"):
            keywords_line = s
            in_abstract = False
        elif s:
            abstract_paras.append(s)
# Also catch a keywords line outside abstract
if not keywords_line:
    for ln in front:
        if re.search(r"keywords", ln, re.I):
            keywords_line = ln.strip()
            break

body_md = "\n".join(body_lines)

# --- Protect math BEFORE markdown ---
math_store = []
def stash(m):
    math_store.append(m.group(0))
    return "\x00MATH%d\x00" % (len(math_store) - 1)

# display math $$...$$ first (DOTALL)
body_md = re.sub(r"\$\$.*?\$\$", stash, body_md, flags=re.S)
# inline math $...$ (no newline, non-greedy)
body_md = re.sub(r"\$[^$\n]+?\$", stash, body_md)

# --- Markdown conversion ---
body_html = markdown.markdown(
    body_md,
    extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
)

# --- Restore math ---
def restore(m):
    return math_store[int(m.group(1))]
body_html = re.sub(r"\x00MATH(\d+)\x00", restore, body_html)

# --- Build abstract html ---
def md_inline(t):
    # minimal inline: bold, italic, code
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t

abstract_html = "\n".join("<p>%s</p>" % md_inline(p) for p in abstract_paras)

# --- Keywords ---
kw_html = ""
if keywords_line:
    kwtext = re.sub(r"^\**\s*keywords\s*[:\-]?\s*", "", keywords_line, flags=re.I)
    kwtext = kwtext.replace("**", "")
    tags = [k.strip(" .") for k in re.split(r"[;,]", kwtext) if k.strip(" .")]
    if tags:
        kw_html = ('<div class="keywords">'
                   + "".join('<span class="kw-tag">%s</span>' % html.escape(t) for t in tags)
                   + "</div>")

# --- Read template and slice ---
with open(TPL, "r", encoding="utf-8") as f:
    tpl = f.read()

# head: everything up to and including </head>
head_end = tpl.index("</head>")
head = tpl[:head_end]
# rewrite title + meta description
head = re.sub(r"<title>.*?</title>", "<title>%s — %s</title>" % (TITLE, AUTHOR), head, flags=re.S)
head = re.sub(r'(<meta name="description" content=")[^"]*(")',
              lambda m: m.group(1) + "The Agentic Turn: Claude Code and the Reconfiguration of Software-Engineering Labour, 2020-2030. A doctoral dissertation by " + AUTHOR + "." + m.group(2),
              head)

# MathJax + supplementary CSS injected before </head>
mathjax = """
<script>
window.MathJax = {
  tex: { inlineMath: [['$','$']], displayMath: [['$$','$$']] },
  options: { skipHtmlTags: ['script','noscript','style','textarea','pre','code'] }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js" async></script>
<style id="thesis-supplement">
.content h1{font-size:1.9rem;color:var(--accent-cyan,#4fc3f7);margin:2.4rem 0 1rem;border-bottom:1px solid rgba(79,195,247,.25);padding-bottom:.4rem;}
.content h2{font-size:1.45rem;color:#e6f4ff;margin:2rem 0 .8rem;}
.content h3{font-size:1.15rem;color:#cfe8f7;margin:1.5rem 0 .6rem;}
.content p{line-height:1.75;margin:0 0 1.1rem;color:#c7d3e0;}
.content ul,.content ol{margin:0 0 1.2rem 1.4rem;line-height:1.7;color:#c7d3e0;}
.content li{margin:.3rem 0;}
.content blockquote{border-left:3px solid var(--accent-cyan,#4fc3f7);margin:1.2rem 0;padding:.4rem 1.2rem;color:#9fb3c8;background:rgba(79,195,247,.05);}
.content a{color:var(--accent-cyan,#4fc3f7);}
.content hr{border:none;border-top:1px solid rgba(255,255,255,.1);margin:2rem 0;}
.content mjx-container{overflow-x:auto;overflow-y:hidden;max-width:100%;}
</style>
"""

# body region: from <body...> to <footer (we rebuild hero/content) ; reuse nav + footer
body_open_m = re.search(r"<body[^>]*>", tpl)
body_open = body_open_m.group(0)

# nav: from after <body> to the hero section start. Reuse nav block (css + nav + js)
hero_idx = tpl.index('<section class="hero"')
nav_block = tpl[body_open_m.end():hero_idx]
# remove active class from nav links (Dashboard active on template)
nav_block = nav_block.replace(' class="active"', '')
# insert new dropdown entry before bgtm-thesis.html entry
new_entry = ('<a href="https://sohweekian.github.io/bluelotus/agentic-turn-thesis.html"><span class="tribute-dot" style="background:#c084fc;"></span>'
             '<span>The Agentic Turn<span class="subline">Jun 2026 — Claude Code &amp; SE labour</span></span></a>\n          ')
m = re.search(r'<a href="[^"]*bgtm-thesis\.html"', nav_block)
if m:
    nav_block = nav_block[:m.start()] + new_entry + nav_block[m.start():]

# footer: from <footer to </footer>
foot_start = tpl.index("<footer")
foot_end = tpl.index("</footer>") + len("</footer>")
footer = tpl[foot_start:foot_end]
# rewrite footer byline + subtitle lines
footer = re.sub(r"Author:.*?(?=</)", "Author: " + AUTHOR + " &middot; Commissioned by Soh Wee Kian, CIO &middot; BlueLotus Fund", footer, count=1, flags=re.S)
footer = re.sub(r"BGTM-V1.*?(?=</)", "The Agentic Turn &middot; Doctoral Dissertation &middot; 28 June 2026 &middot; Singapore", footer, count=1, flags=re.S)

# tail after </footer>
tail = tpl[foot_end:]

# --- Build hero ---
hero = """<section class="hero">
  <div class="pill">🎓 Doctoral Dissertation · BlueLotus Fund · 28 June 2026</div>
  <h1>
    The <span class="highlight">Agentic Turn</span>
  </h1>
  <p class="subtitle">%s</p>
  <div class="meta-row">
    <span>✍️ Author: %s</span>
    <span>·</span>
    <span>📅 28 June 2026 · Singapore</span>
    <span>·</span>
    <span>📖 ~17,400 words</span>
    <span>·</span>
    <span>🏛️ BlueLotus Fund SLICDO</span>
  </div>
</section>
""" % (html.escape(SUBTITLE), html.escape(AUTHOR))

# --- Assemble content ---
content = ('<div class="content">\n'
           + kw_html + "\n"
           + '<div class="abstract-box"><h2>Abstract</h2>\n' + abstract_html + "\n</div>\n"
           + body_html + "\n</div>\n")

out = head + mathjax + "</head>\n" + body_open + "\n" + nav_block + hero + content + footer + tail

with open(OUT, "w", encoding="utf-8") as f:
    f.write(out)

# --- quick validation ---
chap = len(re.findall(r"Chapter\s+\d+", body_html))
print("OK wrote", OUT)
print("chapters refs in body:", chap)
print("math spans:", len(math_store))
print("abstract paras:", len(abstract_paras))
print("keywords tags:", kw_html.count("kw-tag"))
print("raw md leak ##:", body_html.count("\n## "))
