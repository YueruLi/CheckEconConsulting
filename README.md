# CheckEconConsulting

A small app that keeps a live list of **MBA-level openings and recruiting events** at economic
consulting firms. It refreshes every 6 hours on GitHub Actions and publishes a dashboard to
GitHub Pages, with an RSS feed and a GitHub issue whenever something new shows up.

## What it tracks

| Firm | Openings | Events |
| --- | --- | --- |
| Analysis Group | iCIMS associate portal | Recruiting Events calendar, Associate EngAGement Series |
| Cornerstone Research | iCIMS graduate portal (MBA/associate roles) | **Associate recruiting events on [cornerstone.com/careers/associate](https://www.cornerstone.com/careers/associate/)** |
| The Brattle Group | Greenhouse | – |
| Charles River Associates | Greenhouse (main + MBA boards) | – |
| Keystone Strategy | Greenhouse | – |
| NERA Economic Consulting | Marsh Workday site, filtered to NERA | – |
| Bates White | Current openings page | – |
| Compass Lexecon | Careers page | – |

Jobs are filtered by title to roles MBA candidates are hired into (Associate, Summer Associate,
Consultant, anything saying MBA) and exclude undergrad, senior, and support roles. Tune the
regexes in [`firms.yaml`](firms.yaml).

Event calendars use the `events` source type. It finds the page's events section and turns each
dated entry into an item, labelled with the heading above it (usually the school), e.g.
_"Harvard Business School: October 2, 2026 | Coffee Chats | Virtual"_. If Cornerstone edits or
adds an event, it shows up as new.

## Setup (once)

1. Merge this branch into the default branch. Scheduled workflows only run from there.
2. **Settings → Pages**: deploy from branch, choose the default branch and `/docs`.
3. **Actions → Refresh listings → Run workflow** to do the first fetch.

The dashboard is then at `https://<user>.github.io/<repo>/`, with the feed at `…/feed.xml`.

The first run records everything as a baseline without opening an issue. After that, each run
that finds something new opens an issue listing it. GitHub emails you about new issues on your
own repo, so that doubles as an email alert.

## Run locally

```sh
pip install -r requirements.txt
python -m econjobs          # fetch everything, update data/state.json, rebuild docs/
open docs/index.html
pytest -q
```

To test a single source: `python -m econjobs.sources greenhouse thebrattlegroup`, or
`python -m econjobs.sources events https://www.cornerstone.com/careers/associate/`.

## Adding a firm

Add an entry to `firms.yaml`. Supported source types are `greenhouse`, `lever`, `icims`,
`workday`, `events` (dated event calendars), and `page` (any page; its links are filtered by
keyword). Firms such as Edgeworth, BRG, Secretariat, or Berkeley Research Group can be added
with `page` sources pointing at their careers pages.

When a source breaks (a site redesign, or a firm switching job-board systems), the dashboard
shows a "source(s) failed" note and keeps that source's last-known listings.
