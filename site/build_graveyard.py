#!/usr/bin/env python3
"""graveyard.html generator — JSON se static page (JS optional-enhancement only).
Chalao: python3 build_graveyard.py   (site/ folder me)"""
import json
import html as H

ALL = json.load(open("graveyard.json"))

# Only entries that were actually TESTED AND KILLED count as rejections. Two of
# these filters were kept, one was never tested, one was a bug we fixed — they
# stay on the page (they are part of the record) but they are NOT rejections and
# must never inflate the headline number. Drift caught 2 Aug 2026.
data = [d for d in ALL if d.get("s", "rejected") == "rejected"]
other = [d for d in ALL if d.get("s", "rejected") != "rejected"]
LABEL = {"kept": "kept — it survived the test",
         "abandoned": "never tested — abandoned",
         "fixed": "a defect we fixed, not a hypothesis"}

cats = []
for d in data:
    if d["c"] not in cats:
        cats.append(d["c"])
counts = {c: sum(1 for d in data if d["c"] == c) for c in cats}
order = sorted(cats, key=lambda c: -counts[c])

# ── SVG bar chart: rejections by category (single hue, direct labels, no legend)
BAR_H, GAP, LAB_W, W = 26, 10, 250, 860
CH = len(order) * (BAR_H + GAP) + 10
mx = max(counts.values())
rows = []
for i, c in enumerate(order):
    y = i * (BAR_H + GAP) + 5
    bw = max(8, int((W - LAB_W - 70) * counts[c] / mx))
    rows.append(
        f'<text x="{LAB_W-10}" y="{y+BAR_H/2+4}" text-anchor="end">{H.escape(c)}</text>'
        f'<rect class="bar" x="{LAB_W}" y="{y}" width="{bw}" height="{BAR_H}" rx="4">'
        f'<title>{H.escape(c)}: {counts[c]} rejections</title></rect>'
        f'<text class="val" x="{LAB_W+bw+10}" y="{y+BAR_H/2+4}">{counts[c]}</text>')
chart = (f'<div class="chart"><svg viewBox="0 0 {W} {CH}" role="img" '
         f'aria-label="Rejections by category">{"".join(rows)}</svg>'
         f'<div class="cap">documented rejections by category · n = {len(data)}</div></div>')

# ── entries grouped by category, statically rendered
blocks = []
for c in order:
    es = [d for d in data if d["c"] == c]
    items = "".join(
        f'<div class="g-entry" data-cat="{H.escape(c)}">'
        f'<div class="t"><span class="tomb">✝</span>{H.escape(d["n"])}</div>'
        f'<div class="w">{H.escape(d["w"])}</div>'
        f'<div class="k"><b>Kill shot</b>{H.escape(d["k"])}</div>'
        f'<div class="l"><b>Lesson</b>{H.escape(d["l"])}</div></div>'
        for d in es)
    blocks.append(f'<div class="cat-block" data-cat="{H.escape(c)}">'
                  f'<div class="cat-head"><h2>{H.escape(c)}</h2>'
                  f'<span class="cnt">{len(es)} entries</span></div>{items}</div>')

chips = '<button class="on" data-f="All">All ({})</button>'.format(len(data)) + "".join(
    f'<button data-f="{H.escape(c)}">{H.escape(c)} ({counts[c]})</button>' for c in order)

# ── the honest appendix: things on this page that are NOT rejections
notrej = "".join(
    f'<div class="g-entry">'
    f'<div class="t"><span class="tomb">·</span>{H.escape(d["n"])} '
    f'<em class="dim">— {H.escape(LABEL[d["s"]])}</em></div>'
    f'<div class="w">{H.escape(d["w"])}</div>'
    f'<div class="k"><b>Outcome</b>{H.escape(d["k"])}</div>'
    f'<div class="l"><b>Lesson</b>{H.escape(d["l"])}</div></div>'
    for d in other)
notrej_block = (
    f'<div class="cat-block"><div class="cat-head">'
    f'<h2>Not rejections</h2><span class="cnt">{len(other)} entries</span></div>'
    f'<p class="lead">These were logged alongside the graveyard but they are not '
    f'rejections, so they are excluded from the {len(data)} above: two filters that '
    f'passed and are still in the strategy, one idea never tested, and one defect we '
    f'found and fixed. Keeping them visible is the point — the count stays honest '
    f'only if the exclusions are published too.</p>{notrej}</div>')

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Graveyard — {len(data)} documented rejections</title>
<meta name="description" content="Every hypothesis we tested and killed: what it was, the kill-shot, and the lesson. The rejection log is the moat.">
<link rel="stylesheet" href="style.css">
</head>
<body><div class="wrap">
<nav>
  <a class="brand" href="index.html"><span class="tomb">✝</span>the honest <b>quant lab</b></a>
  <a href="index.html">Method</a>
  <a href="graveyard.html" class="on">Graveyard</a>
  <a href="experiment.html">Live experiment</a>
  <a href="story-phantom-exit.html">Stories</a>
  <a href="about.html">About</a>
</nav>
<header class="hero">
<div class="kicker">rejection ledger · updated 2 Aug 2026</div>
<h1>The Graveyard <span class="dim">— {len(data)} documented rejections</span></h1>
<p class="lead">Every entry has three parts: what the idea was, the specific test
that killed it, and what it taught us. Most deaths share a cause —
<span class="mono">edge &lt; friction</span>, a 2-year sample lying, or overfit.
Deployed parameters are redacted; everything else is as it happened.</p>
</header>

{chart}

<div class="filterbar" id="filters">{chips}</div>

{"".join(blocks)}

{notrej_block}

<div class="foot">Research log only — not investment advice. ·
<a href="index.html">method</a> · <a href="experiment.html">live experiment</a></div>
</div>
<script>
document.getElementById('filters').addEventListener('click',e=>{{
  if(e.target.tagName!=='BUTTON')return;
  const f=e.target.dataset.f;
  document.querySelectorAll('#filters button').forEach(b=>b.classList.toggle('on',b===e.target));
  document.querySelectorAll('.cat-block').forEach(b=>{{
    b.style.display=(f==='All'||b.dataset.cat===f)?'':'none';}});
  window.scrollTo({{top:document.getElementById('filters').offsetTop-10,behavior:'smooth'}});
}});
</script>
</body></html>"""
open("graveyard.html", "w").write(page)
print(f"graveyard.html: {len(data)} rejections + {len(other)} non-rejections, {len(order)} categories")
