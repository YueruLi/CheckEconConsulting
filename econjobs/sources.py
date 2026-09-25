"""Fetchers for each job-board type. Each returns a list of raw items:

    {"id", "title", "url", "location", "posted"}

Parsing is kept separate from fetching so it can be tested against saved responses.
"""

import hashlib
import json
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 30

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


# --- Greenhouse -----------------------------------------------------------------------


def fetch_greenhouse(src):
    board = src["board"]
    resp = session.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", timeout=TIMEOUT)
    if resp.status_code == 404:  # unlisted or renamed board
        return []
    resp.raise_for_status()
    return parse_greenhouse(resp.json())


def parse_greenhouse(data):
    return [
        {
            "id": f"gh-{job['id']}",
            "title": _clean(job.get("title")),
            "url": job.get("absolute_url"),
            "location": _clean((job.get("location") or {}).get("name")),
            "posted": (job.get("first_published") or job.get("updated_at") or "")[:10],
        }
        for job in data.get("jobs", [])
    ]


# --- Lever ----------------------------------------------------------------------------


def fetch_lever(src):
    resp = session.get(f"https://api.lever.co/v0/postings/{src['company']}?mode=json", timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_lever(resp.json())


def parse_lever(data):
    items = []
    for job in data:
        created = job.get("createdAt")
        items.append(
            {
                "id": f"lever-{job['id']}",
                "title": _clean(job.get("text")),
                "url": job.get("hostedUrl"),
                "location": _clean((job.get("categories") or {}).get("location")),
                "posted": _ms_to_date(created) if created else "",
            }
        )
    return items


def _ms_to_date(ms):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# --- iCIMS ----------------------------------------------------------------------------

ICIMS_JOB_HREF = re.compile(r"/jobs/(\d+)/[^/?#]+/job")


def fetch_icims(src):
    host = src["host"]
    items, seen = [], set()
    for page in range(10):
        resp = session.get(
            f"https://{host}/jobs/search",
            params={"ss": 1, "in_iframe": 1, "pr": page},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        new = [i for i in parse_icims(resp.text, f"https://{host}/") if i["id"] not in seen]
        if not new:
            break
        seen.update(i["id"] for i in new)
        items.extend(new)
    return items


def parse_icims(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc
    items = {}
    for a in soup.find_all("a", href=True):
        m = ICIMS_JOB_HREF.search(a["href"])
        if not m:
            continue
        job_id = m.group(1)
        heading = a.find(["h1", "h2", "h3", "h4"])
        title = _clean(heading.get_text(" ")) if heading else ""
        if not title:
            for label in a.select(".sr-only, .field-label"):
                label.extract()
            title = _clean(a.get_text(" "))
        if not title:
            # Anchors wrapping only an icon carry the title as "1234 - Title".
            title = re.sub(r"^\s*\d+\s*-\s*", "", a.get("title", ""))
        if not title or job_id in items and items[job_id]["title"]:
            continue
        url = urljoin(base_url, a["href"]).split("?")[0]
        items[job_id] = {
            "id": f"icims-{host}-{job_id}",
            "title": _clean(title),
            "url": url,
            "location": _icims_location(a),
            "posted": "",
        }
    return list(items.values())


def _icims_location(anchor):
    # Each result is a row container; its location sits in a field labelled "Location".
    row = anchor.find_parent(lambda t: t.name in ("li", "tr") or "row" in (t.get("class") or []))
    for _ in range(3):
        if row is None:
            return ""
        label = row.find(string=re.compile(r"^\s*(Job )?Locations?\s*$", re.I))
        if label:
            field = label.find_parent(["dt", "span", "div"])
            value = field.find_next_sibling() if field else None
            if value is not None:
                return _clean(value.get_text(" "))
        row = row.find_parent(lambda t: "row" in (t.get("class") or []) or t.name == "li")
    return ""


# --- Workday --------------------------------------------------------------------------

WORKDAY_URL = re.compile(r"https://(?P<host>(?P<tenant>[^.]+)\.[^/]+)/(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[^/?#]+)")


def fetch_workday(src):
    m = WORKDAY_URL.match(src["url"])
    if not m:
        raise ValueError(f"Unrecognised Workday URL: {src['url']}")
    host, tenant, site = m.group("host"), m.group("tenant"), m.group("site")
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    items, offset = [], 0
    while offset < 500:
        resp = session.post(
            api,
            json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": src.get("search", "")},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = parse_workday(data, f"https://{host}/en-US/{site}")
        items.extend(batch)
        offset += 20
        if not batch or offset >= data.get("total", 0):
            break
    return items


def parse_workday(data, site_url):
    return [
        {
            "id": f"wd-{job.get('bulletFields', [job['externalPath']])[0]}",
            "title": _clean(job.get("title")),
            "url": site_url + job["externalPath"],
            "location": _clean(job.get("locationsText")),
            "posted": _clean(job.get("postedOn")),
        }
        for job in data.get("jobPostings", [])
        if job.get("externalPath")
    ]


# --- Generic page ---------------------------------------------------------------------


def fetch_page(src):
    resp = session.get(src["url"], timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_page(resp.text, resp.url)


def parse_page(html, page_url):
    """Every distinct link on the page, plus headings of dated blocks (typical event listings).

    Filtering by keyword happens later, so this returns everything with visible text.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        text = _clean(a.get_text(" ")) or _clean(a.get("title") or a.get("aria-label"))
        href = a["href"]
        if not text or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(page_url, href)
        key = (text.lower(), url)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "id": "page-" + hashlib.sha1(f"{text}|{url}".encode()).hexdigest()[:16],
                "title": text,
                "url": url,
                "location": "",
                "posted": "",
            }
        )
    return items


# --- Event calendar pages -------------------------------------------------------------

MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE = re.compile(
    rf"\b{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?\b"  # October 2 / Oct. 2nd
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}"  # 2 October
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"  # 10/2 or 10/02/2026
    r"|\b\d{4}-\d{2}-\d{2}\b",
    re.I,
)
BLOCKS = ["li", "tr", "p", "dd", "article", "div"]
HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6", "summary", "dt", "button"]


def fetch_events(src):
    resp = session.get(src["url"], timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_events(resp.text, resp.url, src.get("section", r"event"))


def parse_events(html, page_url, section=r"event"):
    """Dated entries on an event-calendar page, each labelled with the heading above it.

    Calendars are usually grouped by school (an accordion or list of headings) with one
    entry per event that holds a date, e.g. "October 2, 2026 | Coffee Chat | Virtual".
    Only the part of the page after the first heading matching `section` is scanned, when
    such a heading exists. Pages with no dated entries fall back to plain link extraction.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    start = None
    if section:
        pat = re.compile(section, re.I)
        start = next((h for h in soup.find_all(HEADINGS[:6]) if pat.search(h.get_text())), None)
    scope = set(id(t) for t in start.find_all_next()) if start else None

    def in_scope(tag):
        return scope is None or id(tag) in scope

    def dated(tag):
        if tag.name not in BLOCKS or not in_scope(tag):
            return False
        text = _clean(tag.get_text(" "))
        return bool(text) and len(text) < 400 and bool(DATE.search(text))

    # Innermost dated blocks only: a <div> wrapping many dated <li>s is not itself an event.
    candidates = [t for t in soup.find_all(dated)]
    ids = set(id(t) for t in candidates)
    leaves = [t for t in candidates if not any(id(d) in ids for d in t.find_all(BLOCKS))]

    items, seen = [], set()
    for tag in leaves:
        if tag.name == "tr":
            text = " · ".join(_clean(c.get_text(" ")) for c in tag.find_all(["td", "th"]) if _clean(c.get_text(" ")))
        else:
            text = _clean(tag.get_text(" "))
        heading = tag.find_previous(HEADINGS)
        group = _clean(heading.get_text(" ")) if heading is not None and in_scope(heading) else ""
        if group and group.lower() not in text.lower() and not DATE.search(group):
            text = f"{group}: {text}"
        if text in seen:
            continue
        seen.add(text)
        link = tag.find("a", href=True)
        items.append(
            {
                "id": "event-" + hashlib.sha1(f"{page_url}|{text}".encode()).hexdigest()[:16],
                "title": text,
                "url": urljoin(page_url, link["href"]) if link else page_url,
                "location": "",
                "posted": "",
            }
        )
    if items:
        return items
    # Layout not recognised: fall back to links that look like event sign-ups.
    eventish = re.compile(r"event|session|webinar|chat|workshop|register|rsvp|sign ?up", re.I)
    return [i for i in parse_page(html, page_url) if eventish.search(i["title"])]


FETCHERS = {
    "events": fetch_events,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "icims": fetch_icims,
    "workday": fetch_workday,
    "page": fetch_page,
}


def fetch(src):
    return FETCHERS[src["type"]](src)


if __name__ == "__main__":  # quick manual check: python -m econjobs.sources greenhouse thebrattlegroup
    import sys

    kind, value = sys.argv[1], sys.argv[2]
    key = {"greenhouse": "board", "lever": "company", "icims": "host"}.get(kind, "url")
    print(json.dumps(fetch({"type": kind, key: value}), indent=2))
