"""Write the static dashboard (docs/index.html), an RSS feed, and a JSON dump."""

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape
from xml.sax.saxutils import escape as xml_escape

NEW_DAYS = 7


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def active_items(state):
    items = [i for i in state["items"].values() if i.get("active")]
    return sorted(items, key=lambda i: (i["first_seen"], i["firm"], i["title"]), reverse=True)


def render_html(state, feed_url="feed.xml"):
    runs = state.get("runs", [])
    last = runs[0] if runs else {"at": "never", "sources": []}
    now = _parse(last["at"]) if runs else datetime.now(timezone.utc)
    items = active_items(state)
    firms = sorted({i["firm"] for i in items} | {s["firm"] for s in last["sources"]})

    rows = []
    for i in items:
        is_new = now - _parse(i["first_seen"]) <= timedelta(days=NEW_DAYS)
        badges = []
        if is_new:
            badges.append('<span class="badge new">New</span>')
        if i["kind"] == "event":
            badges.append('<span class="badge event">Event</span>')
        elif "mba" in i["title"].lower():
            badges.append('<span class="badge mba">MBA</span>')
        meta = " · ".join(escape(x) for x in (i.get("location"), i.get("posted")) if x)
        rows.append(
            f'<li class="item" data-firm="{escape(i["firm"])}" data-kind="{i["kind"]}" data-new="{int(is_new)}">'
            f'<div class="main"><a href="{escape(i["url"] or "#")}" target="_blank" rel="noopener">{escape(i["title"])}</a>'
            f'{"".join(badges)}</div>'
            f'<div class="sub"><span class="firm">{escape(i["firm"])}</span>'
            f'{" · " + meta if meta else ""}'
            f'<span class="seen" title="First seen {i["first_seen"]}">seen {i["first_seen"][:10]}</span></div></li>'
        )

    problems = [s for s in last["sources"] if s.get("error")]
    status = "".join(
        f'<li><b>{escape(s["firm"])}</b> ({escape(s["type"])}): {escape(s["error"][:200])}</li>' for s in problems
    )
    firm_opts = "".join(f'<option value="{escape(f)}">{escape(f)}</option>' for f in firms)
    n_new = sum(1 for r in rows if 'data-new="1"' in r)

    return TEMPLATE.format(
        updated=escape(last["at"].replace("T", " ").replace("Z", " UTC")),
        count=len(items),
        n_new=n_new,
        rows="\n".join(rows) or '<li class="empty">Nothing yet. Run a refresh.</li>',
        firm_opts=firm_opts,
        status=f'<details class="problems"><summary>{len(problems)} source(s) failed on the last refresh</summary><ul>{status}</ul></details>'
        if problems
        else "",
        feed_url=feed_url,
    )


def render_rss(state, site_url=""):
    items = sorted(state["items"].values(), key=lambda i: i["first_seen"], reverse=True)[:100]
    entries = []
    for i in items:
        title = f"[{i['firm']}] {i['title']}" + (" (event)" if i["kind"] == "event" else "")
        desc = " · ".join(x for x in (i.get("location"), i.get("posted")) if x)
        entries.append(
            "<item>"
            f"<title>{xml_escape(title)}</title>"
            f"<link>{xml_escape(i['url'] or site_url)}</link>"
            f"<guid isPermaLink=\"false\">{xml_escape(i['id'])}</guid>"
            f"<pubDate>{format_datetime(_parse(i['first_seen']))}</pubDate>"
            f"<description>{xml_escape(desc)}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        "<title>Econ consulting MBA openings &amp; events</title>"
        f"<link>{xml_escape(site_url)}</link>"
        "<description>New MBA associate openings and recruiting events at economic consulting firms.</description>"
        + "".join(entries)
        + "</channel></rss>\n"
    )


def render_json(state):
    return json.dumps(active_items(state), indent=1) + "\n"


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Econ Consulting MBA Openings</title>
<link rel="alternate" type="application/rss+xml" title="RSS" href="{feed_url}">
<style>
:root {{
  --bg: #f7f7f5; --card: #ffffff; --text: #1d1d1b; --muted: #6b6b66; --line: #e4e3de;
  --accent: #1f5fbf; --new: #1b7f3b; --mba: #7a4bb5; --event: #b5651d; --warn: #a33;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #141413; --card: #1d1d1b; --text: #ecebe6; --muted: #9c9b95; --line: #33332f;
    --accent: #7eaaf0; --new: #5cc27b; --mba: #b893e6; --event: #e0a15f; --warn: #f08a8a;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
.lede {{ color: var(--muted); margin: 0 0 16px; }}
.lede a {{ color: var(--accent); }}
.controls {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
.controls input, .controls select {{ font: inherit; padding: 6px 10px; border: 1px solid var(--line);
  border-radius: 6px; background: var(--card); color: var(--text); }}
.controls input[type=search] {{ flex: 1 1 200px; }}
.controls label {{ display: flex; align-items: center; gap: 4px; color: var(--muted); }}
ul.list {{ list-style: none; margin: 0; padding: 0; background: var(--card);
  border: 1px solid var(--line); border-radius: 8px; }}
.item {{ padding: 10px 14px; border-top: 1px solid var(--line); }}
.item:first-child {{ border-top: 0; }}
.main a {{ color: var(--text); font-weight: 600; text-decoration: none; }}
.main a:hover {{ color: var(--accent); text-decoration: underline; }}
.sub {{ color: var(--muted); font-size: 13px; margin-top: 2px; }}
.firm {{ color: var(--text); }}
.seen {{ float: right; }}
.badge {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em;
  margin-left: 8px; padding: 1px 6px; border-radius: 4px; border: 1px solid currentColor; }}
.new {{ color: var(--new); }} .mba {{ color: var(--mba); }} .event {{ color: var(--event); }}
.empty {{ padding: 20px; color: var(--muted); text-align: center; }}
.problems {{ margin: 0 0 12px; color: var(--warn); font-size: 13px; }}
@media (max-width: 520px) {{ .seen {{ float: none; display: block; }} }}
</style>
</head>
<body>
<main>
<h1>Econ Consulting MBA Openings</h1>
<p class="lede">{count} open roles and events, {n_new} new this week. Updated {updated}. <a href="{feed_url}">RSS</a></p>
{status}
<div class="controls">
  <input type="search" id="q" placeholder="Filter by title or location">
  <select id="firm"><option value="">All firms</option>{firm_opts}</select>
  <select id="kind"><option value="">Jobs &amp; events</option><option value="job">Jobs</option><option value="event">Events</option></select>
  <label><input type="checkbox" id="onlynew"> New only</label>
</div>
<ul class="list" id="list">
{rows}
</ul>
</main>
<script>
const $ = id => document.getElementById(id);
function apply() {{
  const q = $("q").value.toLowerCase(), firm = $("firm").value, kind = $("kind").value, onlyNew = $("onlynew").checked;
  for (const li of document.querySelectorAll(".item")) {{
    const ok = (!q || li.textContent.toLowerCase().includes(q)) && (!firm || li.dataset.firm === firm)
      && (!kind || li.dataset.kind === kind) && (!onlyNew || li.dataset.new === "1");
    li.hidden = !ok;
  }}
}}
for (const id of ["q", "firm", "kind", "onlynew"]) $(id).addEventListener("input", apply);
</script>
</body>
</html>
"""
