"""Refresh all sources and rebuild the site.

    python -m econjobs              # fetch, update data/state.json, write docs/
    python -m econjobs --render     # rebuild docs/ from saved state without fetching
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from . import core, render

DOCS = core.ROOT / "docs"
KEEP_INACTIVE_DAYS = 180


def prune(state, now):
    cutoff = (now - timedelta(days=KEEP_INACTIVE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["items"] = {k: v for k, v in state["items"].items() if v.get("active") or v["last_seen"] >= cutoff}


def write_site(state, site_url):
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(render.render_html(state))
    (DOCS / "feed.xml").write_text(render.render_rss(state, site_url))
    (DOCS / "jobs.json").write_text(render.render_json(state))
    (DOCS / ".nojekyll").touch()


def summary_markdown(new):
    lines = [f"{len(new)} new posting(s) found:\n"]
    for i in sorted(new, key=lambda i: (i["firm"], i["kind"], i["title"])):
        tag = " _(event)_" if i["kind"] == "event" else ""
        loc = f" · {i['location']}" if i.get("location") else ""
        lines.append(f"- **{i['firm']}**: [{i['title']}]({i['url']}){tag}{loc}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="econjobs")
    ap.add_argument("--render", action="store_true", help="only rebuild docs/ from saved state")
    ap.add_argument("--site-url", default="", help="public URL of the dashboard, used in the RSS feed")
    ap.add_argument("--new-summary", help="write a Markdown list of new items to this file (if any)")
    args = ap.parse_args(argv)

    state = core.load_state()
    if not args.render:
        first_run = not state["items"]
        now = datetime.now(timezone.utc)
        new, reports = core.refresh(core.load_config(), state, now=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        prune(state, now)
        core.save_state(state)

        for r in reports:
            status = r.get("error") or f"{r['kept']}/{r['fetched']} kept"
            print(f"{r['firm']:<28} {r['type']:<10} {status}")
        print(f"\n{len(new)} new item(s)")
        for i in new:
            print(f"  + [{i['firm']}] {i['title']}")

        # The first run finds everything; only later runs are worth a notification.
        if args.new_summary and new and not first_run:
            with open(args.new_summary, "w") as f:
                f.write(summary_markdown(new))

    write_site(state, args.site_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
