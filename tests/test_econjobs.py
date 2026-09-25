from econjobs import core, render, sources

DEFAULTS = core.load_config()["defaults"]


# --- parsers --------------------------------------------------------------------------


def test_greenhouse():
    data = {
        "jobs": [
            {
                "id": 42,
                "title": "Associate, MBA - Corporate Finance",
                "absolute_url": "https://job-boards.greenhouse.io/thebrattlegroup/jobs/42",
                "location": {"name": "Washington, DC"},
                "first_published": "2026-09-01T10:00:00-04:00",
            }
        ]
    }
    [job] = sources.parse_greenhouse(data)
    assert job == {
        "id": "gh-42",
        "title": "Associate, MBA - Corporate Finance",
        "url": "https://job-boards.greenhouse.io/thebrattlegroup/jobs/42",
        "location": "Washington, DC",
        "posted": "2026-09-01",
    }


ICIMS_HTML = """
<div class="container-fluid iCIMS_JobsTable">
  <div class="row">
    <div class="col-xs-12 title">
      <a href="https://grad-chire.icims.com/jobs/4101/associate---mba/job?in_iframe=1" class="iCIMS_Anchor"
         title="4101 - Associate - MBA"><span class="sr-only field-label">Title</span><h3>Associate - MBA</h3></a>
    </div>
    <div class="col-xs-12 additionalFields">
      <dl><div class="iCIMS_JobHeaderTag"><dt class="iCIMS_JobHeaderField">Location</dt>
      <dd class="iCIMS_JobHeaderData"><span>US-NY-New York</span></dd></div></dl>
    </div>
  </div>
  <div class="row">
    <div class="col-xs-12 title">
      <a href="/jobs/4102/summer-associate---mba/job" class="iCIMS_Anchor"><h3>Summer Associate - MBA</h3></a>
    </div>
  </div>
</div>
<a href="/jobs/intro">Back</a>
"""


def test_icims():
    jobs = sources.parse_icims(ICIMS_HTML, "https://grad-chire.icims.com/")
    assert [(j["id"], j["title"]) for j in jobs] == [
        ("icims-grad-chire.icims.com-4101", "Associate - MBA"),
        ("icims-grad-chire.icims.com-4102", "Summer Associate - MBA"),
    ]
    assert jobs[0]["url"] == "https://grad-chire.icims.com/jobs/4101/associate---mba/job"
    assert jobs[0]["location"] == "US-NY-New York"
    assert jobs[1]["url"] == "https://grad-chire.icims.com/jobs/4102/summer-associate---mba/job"


def test_workday():
    data = {
        "total": 1,
        "jobPostings": [
            {
                "title": "NERA: Consultant (MBA)",
                "externalPath": "/job/New-York/NERA-Consultant_R_1234",
                "locationsText": "New York",
                "postedOn": "Posted 2 Days Ago",
                "bulletFields": ["R_1234"],
            }
        ],
    }
    [job] = sources.parse_workday(data, "https://mmc.wd1.myworkdayjobs.com/en-US/MMC")
    assert job["id"] == "wd-R_1234"
    assert job["url"] == "https://mmc.wd1.myworkdayjobs.com/en-US/MMC/job/New-York/NERA-Consultant_R_1234"


# --- Cornerstone-style event calendars ------------------------------------------------

ACCORDION = """
<nav><a href="/careers/">Careers</a></nav>
<h2>The Associate Experience</h2>
<p>Founded in 1989, we opened offices on May 3 in many cities.</p>
<h2>Associate Recruiting Events</h2>
<div class="accordion">
  <button class="accordion__title">Harvard Business School</button>
  <div class="accordion__panel">
    <ul>
      <li>October 2, 2026 | Coffee Chats | Virtual <a href="https://hbs.example/register">Register</a></li>
      <li>October 15, 2026 | Corporate Presentation | Boston</li>
    </ul>
  </div>
  <button class="accordion__title">MIT Sloan School of Management</button>
  <div class="accordion__panel">
    <p>Oct. 9th – Case Interview Workshop</p>
  </div>
</div>
"""


def test_events_accordion():
    events = sources.parse_events(ACCORDION, "https://www.cornerstone.com/careers/associate/")
    titles = [e["title"] for e in events]
    assert titles == [
        "Harvard Business School: October 2, 2026 | Coffee Chats | Virtual Register",
        "Harvard Business School: October 15, 2026 | Corporate Presentation | Boston",
        "MIT Sloan School of Management: Oct. 9th – Case Interview Workshop",
    ]
    assert events[0]["url"] == "https://hbs.example/register"
    assert events[1]["url"] == "https://www.cornerstone.com/careers/associate/"  # no link: the page itself


TABLE = """
<h3>Upcoming Events</h3>
<table>
  <tr><th>School</th><th>Event</th><th>Date</th></tr>
  <tr><td>Kellogg</td><td>Information Session</td><td>10/07/2026</td></tr>
  <tr><td>Wharton</td><td>Coffee Chat</td><td>Nov 3</td></tr>
</table>
"""


def test_events_table():
    titles = [e["title"] for e in sources.parse_events(TABLE, "https://x.example/")]
    assert titles == [
        "Kellogg · Information Session · 10/07/2026",
        "Wharton · Coffee Chat · Nov 3",
    ]


def test_events_ids_are_stable_and_change_with_content():
    a = sources.parse_events(ACCORDION, "https://x.example/")
    b = sources.parse_events(ACCORDION, "https://x.example/")
    c = sources.parse_events(ACCORDION.replace("October 15", "October 16"), "https://x.example/")
    assert [e["id"] for e in a] == [e["id"] for e in b]
    assert a[1]["id"] != c[1]["id"]


def test_events_fallback_to_links():
    html = '<h2>Events</h2><a href="/e/1">Register for our MBA webinar</a><a href="/about">About us</a>'
    events = sources.parse_events(html, "https://x.example/")
    assert [e["title"] for e in events] == ["Register for our MBA webinar"]


# --- filtering and state ----------------------------------------------------------------


def test_title_filter():
    job = {"type": "greenhouse"}
    keep = [
        "Associate, MBA - Corporate Finance",
        "Summer Associate - MBA",
        "Consultant",
        "Senior Associate, Finance (2027 MBA Graduates)",
        "NERA: Consultant - Energy",
    ]
    drop = [
        "Research Associate",
        "Analyst",
        "Associate Principal, Antitrust",
        "Administrative Assistant",
        "Recruiting Coordinator",
        "IT Help Desk Associate",
        "Vice President",
    ]
    for t in keep:
        assert core.matches(t, job, DEFAULTS), t
    for t in drop:
        assert not core.matches(t, job, DEFAULTS), t
    assert not core.matches("Consultant", {"require": "NERA"}, DEFAULTS)


def fake_fetcher(results):
    def fetch(src):
        r = results[src["board"]]
        if isinstance(r, Exception):
            raise r
        return r

    return fetch


def job(i, title="Associate - MBA"):
    return {"id": f"gh-{i}", "title": title, "url": f"https://x/{i}", "location": "", "posted": ""}


def test_refresh_tracks_new_and_removed():
    config = {"defaults": DEFAULTS, "firms": [{"name": "A", "sources": [{"type": "greenhouse", "board": "a"}]}]}
    state = {"items": {}, "runs": []}

    new, _ = core.refresh(config, state, fake_fetcher({"a": [job(1), job(2, "Analyst")]}), now="2026-09-01T00:00:00Z")
    assert [i["id"] for i in new] == ["gh-1"]

    new, _ = core.refresh(config, state, fake_fetcher({"a": [job(1), job(3)]}), now="2026-09-02T00:00:00Z")
    assert [i["id"] for i in new] == ["gh-3"]
    assert state["items"]["gh-1"]["first_seen"] == "2026-09-01T00:00:00Z"

    new, _ = core.refresh(config, state, fake_fetcher({"a": [job(3)]}), now="2026-09-03T00:00:00Z")
    assert new == [] and state["items"]["gh-1"]["active"] is False

    # A failing source keeps its items as they were.
    new, reports = core.refresh(config, state, fake_fetcher({"a": RuntimeError("down")}), now="2026-09-04T00:00:00Z")
    assert state["items"]["gh-3"]["active"] is True and "down" in reports[0]["error"]


def test_render():
    config = {"defaults": DEFAULTS, "firms": [{"name": "A & B", "sources": [{"type": "greenhouse", "board": "a"}]}]}
    state = {"items": {}, "runs": []}
    core.refresh(config, state, fake_fetcher({"a": [job(1, "Associate <MBA>")]}), now="2026-09-01T00:00:00Z")
    html = render.render_html(state)
    assert "Associate &lt;MBA&gt;" in html and "A &amp; B" in html and ">New<" in html
    rss = render.render_rss(state, "https://example.com/")
    assert "<title>[A &amp; B] Associate &lt;MBA&gt;</title>" in rss
