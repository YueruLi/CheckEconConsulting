"""Load config, fetch every source, filter, and merge with previously seen items."""

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import sources

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state.json"


def compile_pattern(pattern):
    # YAML folded strings put spaces around line breaks; they are not part of the regex.
    return re.compile(re.sub(r"\s*\|\s*", "|", pattern.strip()), re.I) if pattern else None


def load_config(path=ROOT / "firms.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def matches(title, src, defaults):
    kind = src.get("kind", "job")
    include = compile_pattern(src.get("include") or defaults.get("event_include" if kind == "event" else "include"))
    exclude = compile_pattern(src["exclude"] if "exclude" in src else defaults.get("exclude") if kind == "job" else None)
    require = compile_pattern(src.get("require"))
    return (
        (include is None or include.search(title))
        and not (exclude and exclude.search(title))
        and (require is None or require.search(title))
    )


def load_state(path=STATE_PATH):
    if path.exists():
        return json.loads(path.read_text())
    return {"items": {}, "runs": []}


def save_state(state, path=STATE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def refresh(config, state, fetch=sources.fetch, now=None):
    """Fetch all sources and update `state` in place. Returns (new_items, source_reports)."""
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    defaults = config.get("defaults", {})
    items = state["items"]
    new, reports = [], []

    for firm in config["firms"]:
        for src in firm["sources"]:
            label = src.get("board") or src.get("company") or src.get("host") or src.get("url")
            report = {"firm": firm["name"], "type": src["type"], "source": label}
            try:
                raw = fetch(src)
            except Exception as e:  # one broken site shouldn't stop the others
                report["error"] = f"{type(e).__name__}: {e}"
                traceback.print_exc()
                reports.append(report)
                continue

            kept = [r for r in raw if matches(r["title"], src, defaults)]
            report.update(fetched=len(raw), kept=len(kept))
            reports.append(report)

            current = set()
            for r in kept:
                current.add(r["id"])
                item = items.get(r["id"])
                if item is None:
                    item = {**r, "firm": firm["name"], "kind": src.get("kind", "job"), "first_seen": now}
                    items[r["id"]] = item
                    new.append(item)
                else:
                    item.update({k: v for k, v in r.items() if v})
                item.update(last_seen=now, active=True, source=label)

            # Anything from this source that wasn't seen this time has been taken down.
            for item in items.values():
                if item.get("source") == label and item["firm"] == firm["name"] and item["id"] not in current:
                    item["active"] = False

    state["runs"] = ([{"at": now, "new": len(new), "sources": reports}] + state.get("runs", []))[:50]
    return new, reports
