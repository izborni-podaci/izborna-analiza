"""Site, feeds, email digest and the private target list."""

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import json

import pytest

from izbori import feed, mail, targets
from izbori.site import build

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


@pytest.fixture(scope="module")
def site(tmp_path_factory, archive):
    """The site built once from the archive, shared by the tests that only read it."""
    return build(archive, tmp_path_factory.mktemp("site") / "site", None, "https://example.org/x/")


def test_site(site):
    out = site
    for prefix in ("", "cyr/", "en/"):
        for page in ("index.html", "guide.html", "about.html", "r/680072/index.html", "r/680072/check.html",
                     "r/680072/changes.html", "r/680072/commissions.html"):
            assert (out / prefix / page).exists(), prefix + page
    assert len(list((out / "r/680072/m").glob("*.html"))) == 191
    # a phone shows each cell's label from one stylesheet, in the page's language
    labels = (out / "static/labels.css").read_text(encoding="utf-8")
    assert ':lang(sr-Cyrl) table.history td.l-registered::before { content: "Уписани бирачи"; }' in labels
    assert ':lang(sr-Latn) table.history td.l-registered::before { content: "Upisani birači"; }' in labels
    place = next((out / "s").glob("*.html")).read_text(encoding="utf-8")
    assert "static/labels.css" in place and "l-registered" in place and "data-label" not in place

    # Latin and English pages carry no Cyrillic except the name of the Cyrillic switch
    for path in [*out.glob("*.html"), *(out / "r").rglob("*.html"), *(out / "s").glob("*.html"),
                 *(out / "m").glob("*.html"), *(out / "en").rglob("*.html")]:
        text = path.read_text(encoding="utf-8").replace("Ћирилица", "")
        assert not CYRILLIC.search(text), path
    assert CYRILLIC.search((out / "cyr/r/680072/index.html").read_text(encoding="utf-8"))

    page = (out / "r/680072/check.html").read_text(encoding="utf-8")
    assert "Bosilegrad" in page and "BM 21" in page

    # the guide is for controllers too, links the latest election and names the site's own flags in each language
    guide = (out / "guide.html").read_text(encoding="utf-8")
    assert "Vodič za kontrolore i posmatrače" in guide and re.search(r'href="r/\d+/check\.html"', guide)
    assert 'id="brojanje"' in guide and "Više listića nego potpisa" in guide and "čl. 116" in guide
    # local elections: the differences, with the higher court for appeals and four copies of the minutes for lists
    assert 'id="lokalni"' in guide and "višem sudu" in guide and "<strong>četiri</strong>" in guide
    guide_en = (out / "en/guide.html").read_text(encoding="utf-8")
    assert "Guide for controllers and observers" in guide_en and "More ballots than signatures" in guide_en
    assert 'id="lokalni"' in guide_en and "<strong>higher court</strong>" in guide_en

    # the home page: the archive in numbers under the search, nothing beside it with no election ahead, six ways in
    home = (out / "index.html").read_text(encoding="utf-8")
    assert "Izbora u arhivi: " in home and "dokumenata sa sajta RIK-a: " in home
    assert 'class="hero"' in home and "data-next" not in home  # no election ahead in data/elections.csv
    # the guide's link reads its whole name; phones show the short one from the attribute, not a second text
    assert '<a href="guide.html" data-short="Vodič">Vodič za kontrolore i posmatrače</a>' in home
    for target in ('href="municipalities.html"', 'href="about.html#podaci"', 'href="r/680072/index.html#controllers"',
                   'href="guide.html"', 'href="repeat.html"'):
        assert target in home, target
    assert 'id="podaci"' in (out / "about.html").read_text(encoding="utf-8")
    assert 'value="g-paper"' in (out / "r/680072/check.html").read_text(encoding="utf-8")  # the group's link lands
    # every municipality, in Serbian alphabetical order: Latin (lj after l, ć after c) and Cyrillic
    names = re.findall(r'<td><a href="m/\d+\.html">([^<]+)</a>', (out / "municipalities.html").read_text(encoding="utf-8"))
    assert len(names) > 150 and names.index("Lučani") < names.index("Ljig")
    assert names.index("Crna Trava") < names.index("Ćićevac")
    cyr = re.findall(r'<td><a href="\.\./cyr/m/\d+\.html">([^<]+)</a>',
                     (out / "cyr/municipalities.html").read_text(encoding="utf-8"))
    assert cyr.index("Тутин") < cyr.index("Ћићевац") < cyr.index("Уб")

    assert "Водич за контролоре и посматраче" in (out / "cyr/guide.html").read_text(encoding="utf-8")
    # links to RIK documents are percent-encoded, so they survive transliteration
    hrefs = re.findall(r'href="(https://rik[^"]+)"', page)
    assert hrefs and all(not CYRILLIC.search(h) for h in hrefs)
    # nothing loaded from other servers
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8").replace("https://example.org/x/", "")  # the site's own address
        assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', text), path
    assert "https://example.org/x/static/site.css" in (out / "404.html").read_text(encoding="utf-8")


def test_commissions(site, archive):
    import csv
    import io
    """Each election's page on the municipal commissions: one row per municipality in Serbia, linked from the
    round's pages and the municipalities page, with the same table as CSV."""
    out = site
    for prefix in ("", "cyr/", "en/"):
        page = (out / prefix / "r/680072/commissions.html").read_text(encoding="utf-8")
        assert re.search(r'<a href="[^"]*commissions\.html" aria-current="page">', page)
        root = "../../../" if prefix else "../../"
        assert f'href="{root}api/r/680072/commissions.csv"' in page
    page = (out / "r/680072/commissions.html").read_text(encoding="utf-8")
    rows = re.findall(r'<tr id="c-(\d+)"', page)
    rnd = archive.load("680072")
    domestic = {s.municipality_code for s in rnd.stations if s.kind == "domestic"}
    assert set(rows) == domestic and "33000" not in rows
    assert "Opštinske izborne komisije" in page and "Ovo nije ocena." in page
    assert 'class="num warn"' in page  # something is worth a question, and says so
    assert 'href="r/680072/commissions.html"' in (out / "municipalities.html").read_text(encoding="utf-8")
    assert 'href="../../r/680072/commissions.html"' in (out / "r/680072/index.html").read_text(encoding="utf-8")
    one = next(iter(rows))
    assert f'href="../../../r/680072/commissions.html#c-{one}"' in (out / f"r/680072/m/{one}.html").read_text(
        encoding="utf-8")
    for rid in archive.round_ids():
        lines = (out / f"api/r/{rid}/commissions.csv").read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("code,municipality,district,stations,minutes,median_hours")
        assert len(lines) > 10
    # Kostolac's vote is run by Požarevac's commission: its documents are shown with Kostolac, apart from its own
    rows26 = {r["code"]: r for r in csv.DictReader(io.StringIO(
        (out / "api/r/680072/commissions.csv").read_text(encoding="utf-8")))}
    assert rows26["71340"]["commission_documents"] == "0" and int(rows26["71340"]["city_commission_documents"]) > 0
    kostolac = (out / "r/680072/m/71340.html").read_text(encoding="utf-8")
    assert 'id="city-commission"' in kostolac and "Požarevac" in kostolac
    # the 2022 election's decisions on polling boards weren't read: unknown, not none
    old = (out / "api/r/42732/commissions.csv").read_text(encoding="utf-8").splitlines()[1].split(",")
    assert old[8] == old[9] == ""

    # the round page: round percentages against chance, and the same tests per municipality
    index = (out / "r/680072/index.html").read_text(encoding="utf-8")
    assert 'id="local"' in index and "Bonferoni" in index and "Očekivano" in index


def test_explore(site, archive):
    """The Explore page: its script draws everything in the browser from api/, with the strings and the lists that
    come with the page in its language, and the boundaries joined to RIK's municipalities by code."""
    out = site
    for prefix in ("", "cyr/", "en/"):
        page = (out / prefix / "explore.html").read_text(encoding="utf-8")
        assert re.search(r'<a href="[^"]*explore\.html" aria-current="page">', page)
        assert "static/explore.js" in page and "<noscript>" in page
        meta = json.loads(re.search(r'<script type="application/json" id="ex-meta">(.*?)</script>', page, re.S).group(1))
        assert meta["loc"] == {"": "lat", "cyr/": "cyr", "en/": "en"}[prefix]
        assert [r["id"] for r in meta["rounds"]][0] == "680072"  # newest first
        # every list of every election, in ballot order: the reader chooses one, the page never does
        assert all([x["n"] for x in r["lists"]] == sorted(x["n"] for x in r["lists"]) for r in meta["rounds"])
        assert all(k.startswith(("ex_", "m_", "view_", "level_", "preset_", "group_")) for k in meta["t"])
        assert meta["abroad"] == "33000" and meta["prisons"] == "55001"
    lat = json.loads(re.search(r'id="ex-meta">(.*?)</script>', (out / "explore.html").read_text(encoding="utf-8"),
                               re.S).group(1))
    assert lat["muns"]["80438"] == "Grad Subotica" and lat["t"]["ex_msg_list"].startswith("Izaberite listu")
    cyr = json.loads(re.search(r'id="ex-meta">(.*?)</script>', (out / "cyr/explore.html").read_text(encoding="utf-8"),
                               re.S).group(1))
    assert cyr["muns"]["80438"] == "Град Суботица"
    assert 'href="explore.html"' in (out / "index.html").read_text(encoding="utf-8")  # in the nav of every page

    # one election's stations as columns of equal length, each list's votes in ballot order
    rnd = archive.load("680072")
    data = json.loads((out / "api/r/680072/stations.json").read_text(encoding="utf-8"))
    cols = data["stations"]
    assert {len(v) for v in cols.values()} == {len(rnd.stations)}
    assert len(data["votes"]) == len(rnd.contestants) == len(data["contestants"])
    i = next(k for k, s in enumerate(rnd.stations) if s.registered)
    s = rnd.stations[i]
    assert (cols["mc"][i], cols["no"][i], cols["reg"][i], cols["voted"][i]) == (
        s.municipality_code, s.number, s.registered, s.voted)
    assert [v[i] for v in data["votes"]] == s.votes
    assert data["groups"] == ["paper", "change", "records", "unusual"] and data["controllers"]
    hours = [h for h in cols["min"] if h is not None]  # from the polls closing to the first minutes in RIK's register
    assert len(hours) > 8000 and 0 < sorted(hours)[len(hours) // 2] < 24
    assert all(p for p in cols["place"])  # every station leads to its page across elections
    # each station's settlement, by its index in the election's settlements, with the census's figures
    from izbori import bysettlement, settlements
    joined = settlements.load_store(archive.dir("680072"))["stations"]
    fig = settlements.load_figures(archive.root)
    assert sum(k is not None for k in cols["set"]) == len(joined)
    k = next(j for j, s in enumerate(rnd.stations) if s.key in joined)
    e = joined[rnd.stations[k].key]
    f = fig[(e["u"], e["s"])]
    assert data["settlements"][cols["set"][k]] == [e["s"], int(f.urban), f.pop2011, f.pop2022, f.old]
    assert lat["classes"] == {k: list(v) for k, v in bysettlement.CLASSES.items()}
    assert all(r["census"] for r in lat["rounds"]) and lat["t"]["ex_sx_size_0"] == "do 499"
    for rid in archive.round_ids():
        assert (out / f"api/r/{rid}/stations.json").exists(), rid

    # the boundaries of RIK's municipalities only: a city counted by its city municipalities isn't drawn over them
    geo = json.loads((out / "api/geo/municipalities.json").read_text(encoding="utf-8"))
    codes = {f["properties"]["code"] for f in geo["features"] if not f["properties"].get("none")}
    assert codes and codes <= set(lat["muns"]) and "79014" not in codes and "70181" in codes  # not Belgrade, New Belgrade
    assert "OpenStreetMap" in geo["attribution"] and "ODbL" in geo["license"]
    # Kosovo and Metohija in RIK's division, credited; its municipalities with no station are named, with no code
    assert {"90263", "90336"} <= codes and "Glaurdić" in geo["attribution"] and "CC BY 4.0" in geo["license"]
    assert all(f["properties"]["kim"] for f in geo["features"] if f["properties"]["code"].startswith("9"))
    assert all(f["properties"]["name"] and not f["properties"]["code"] for f in geo["features"]
               if f["properties"].get("none"))


@pytest.mark.parametrize("name", ["explore.js", "site.js"])
def test_scripts_parse(name):
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    script = Path(__file__).parents[1] / "src/izbori/static" / name
    subprocess.run([node, "--check", str(script)], check=True)


def test_home_shows_the_next_election(tmp_path, archive):
    import shutil

    from izbori.history import Archive
    from izbori.i18n import BELGRADE

    data = tmp_path / "data"
    shutil.copytree(archive.dir("567956"), data / "rounds" / "567956")  # a small round keeps the build quick
    today = datetime.now(BELGRADE).date()
    day = today + timedelta(days=20)
    (data / "elections.csv").write_text("date,round,kind,note\n"
                                        f"{(today - timedelta(days=3)).isoformat()},,parliamentary,\n"
                                        f"{day.isoformat()},,local,Примерне општине\n", encoding="utf-8")
    out = build(Archive(data), tmp_path / "site", None, "https://example.org/x/")
    home = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="hero with-next"' in home and f'data-days-until="{day.isoformat()}"' in home
    assert "Lokalni izbori" in home and "Primerne opštine" in home
    first = day - timedelta(days=15)
    assert f"do {first.day}.{first.month}.{first.year}." in home and "predlog članova biračkih odbora" in home
    assert 'href="guide.html#rokovi"' in home
    assert "Local election" in (out / "en/index.html").read_text(encoding="utf-8")


def test_feeds(archive):
    for loc in ("lat", "en"):
        xml = feed.build(archive.root, archive, loc, "https://example.org/x/")
        root = ET.fromstring(xml)
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        assert len(entries) == len(feed.load_entries(archive.root))
        assert not CYRILLIC.search(xml)


def test_feed_entry_orders_every_group():
    """A remark RIK published with the minutes (the records group) went into a feed entry on 5 Nov 2026 and stopped
    the documents run: the entry's order knew only three of the four groups."""
    from types import SimpleNamespace as NS

    from izbori.checks import Flag

    st = [NS(key=f"70017/{n}", municipality="Александровац", municipality_code="70017", number=str(n), name="")
          for n in (1, 2, 3)]
    flags = [Flag("70017/3", "turnout_drop", {}), Flag("70017/1", "remark_filed", {}),
             Flag("70017/2", "signed_over_ballots", {})]
    a = NS(flags=flags, round=NS(stations=st, id="1", title="", kind="parliamentary"),
           totals=NS(counted=3, stations=3))
    entry = feed.make_entry(a, [f.id for f in flags], "2026-11-05T12:33:00+00:00")
    assert [f["code"] for f in entry["flags"]] == ["signed_over_ballots", "remark_filed", "turnout_drop"]


def test_mail_digest(tmp_path, archive):
    entry = feed.load_entries(archive.root)[-1]
    mail.queue(tmp_path, entry=entry)
    env = {"SMTP_HOST": "smtp.example.org", "SMTP_PORT": "587", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
           "MAIL_FROM": "alerts@example.org", "MAIL_TO": "a@example.org, b@example.org"}
    sent = []

    def sender(msg, s):
        mail_from = s["MAIL_FROM"]
        msg["From"] = mail_from
        msg["To"] = mail_from
        sent.append((msg, s["recipients"]))

    now = datetime(2026, 12, 20, 21, 0, tzinfo=UTC)
    assert mail.maybe_send(tmp_path, archive, "https://example.org/x/", now, env=env, sender=sender)
    msg, recipients = sent[0]
    assert recipients == ["a@example.org", "b@example.org"]
    assert "Bcc" not in msg and "a@example.org" not in msg.as_string()
    body = msg.get_content()
    assert "Bosilegrad" in body or "Prikazano" not in body
    # within 15 minutes nothing more goes out, even with new flags pending
    mail.queue(tmp_path, entry=entry)
    assert not mail.maybe_send(tmp_path, archive, "https://example.org/x/", now + timedelta(minutes=5), env=env,
                               sender=sender)
    # a finished count is sent at once
    mail.queue(tmp_path, final_round="680072")
    assert mail.maybe_send(tmp_path, archive, "https://example.org/x/", now + timedelta(minutes=6), env=env,
                           sender=sender)
    assert len(sent) == 2
    # without settings nothing is sent and nothing piles up
    mail.queue(tmp_path, entry=entry)
    assert not mail.maybe_send(tmp_path, archive, "https://example.org/x/", now + timedelta(hours=1), env={},
                               sender=sender)
    assert mail.load_state(tmp_path)["pending"] == []


def test_targets(tmp_path, archive):
    rows = targets.rank(archive)
    assert rows and rows[0]["score"] >= rows[-1]["score"] > 0
    targets.write_csv(rows, tmp_path / "targets.csv")
    targets.write_html(rows, tmp_path / "targets.html")
    text = (tmp_path / "targets.csv").read_text(encoding="utf-8")
    assert "Bosilegrad" in text and not CYRILLIC.search(text)
    assert not CYRILLIC.search((tmp_path / "targets.html").read_text(encoding="utf-8"))


def test_site_shows_controllers(tmp_path, archive):
    import json
    import shutil

    from izbori.history import Archive
    data = tmp_path / "data"
    for rid in ("680072", "567956"):  # the round under test and a small one, to keep the build quick
        shutil.copytree(archive.dir(rid), data / "rounds" / rid)
    rnd = archive.load("680072")
    s = next(x for x in rnd.stations if x.municipality == "Дољевац" and x.number == "23")
    store = {"docs": {"x": {"s": s.key, "k": "extended", "r": False, "t": "1792900000", "unmatched": 0,
                            "addr": "ОШ ПРИМЕР, ГЛАВНА 1", "slots": [[1, True, True], [3, True, False], [2, False, False]],
                            "u": "/extfile/sr/files/additionalDocuments/810/101/Решење проширени БМ 23.pdf"},
                      "y": {"s": s.key, "k": "standing", "r": False, "t": "1791000000",
                            "u": "/extfile/sr/files/additionalDocuments/790/202/Resenje stalni 23.pdf"},
                      "z": {"s": s.key, "k": "extended_change", "r": False, "t": "1793000000", "u": ""}}}
    (data / "rounds/680072/boards.json").write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    # RIK's register of minutes lists an observers' record and a remark for the same station
    docs = {"labels": ["Записник о посматрачима (Образац РГ-11/НП)", "Примедба"], "unmatched": [],
            "stations": {s.key: [[0, "/extfile/sr/election_results/799/052/6ade751ba7cbb/@БМ 23 - РГ-11_b.pdf",
                                  "2026-10-25T22:31"],
                                 [1, "/extfile/sr/election_results/801/371/6ade7b1be1216/@Примедба 23_c.pdf",
                                  "2026-10-25T22:56"]]}}
    (data / "rounds/680072/documents.json").write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
    # the municipality's electoral commission published minutes of two sessions on one day, and a decision
    at = "/extfile/sr/files/additionalDocuments/820/"
    cdocs = {"complete": True, "docs": {
        "1": {"m": s.municipality_code, "c": "session", "t": "1793700000", "u": at + "1/З 1.pdf"},
        "2": {"m": s.municipality_code, "c": "session", "t": "1793700100", "u": at + "2/З 2.pdf"},
        "3": {"m": s.municipality_code, "c": "decision", "t": "1792000000", "u": at + "3/Р.pdf"}}}
    (data / "rounds/680072/commission.json").write_text(json.dumps(cdocs, ensure_ascii=False), encoding="utf-8")
    # a person read the observers' record and found remarks
    (data / "rounds/680072/observer_reviews.csv").write_text(
        "municipality_code,station,remarks,summary_sr,summary_en,checked\n"
        f"{s.municipality_code},{s.number},да,Гужва испред бирачког места,A crowd outside the station,2026-11-04\n",
        encoding="utf-8")
    out = build(Archive(data), tmp_path / "site", None, "https://example.org/x/")
    round_page = (out / "r/680072/index.html").read_text(encoding="utf-8")
    assert "Kontrolori u biračkim odborima" in round_page
    mun = (out / f"r/680072/m/{s.municipality_code}.html").read_text(encoding="utf-8")
    assert "Kontrolori: liste 1, 3" in mun and "od 18" not in mun and "OŠ PRIMER, GLAVNA 1" in mun
    assert "Controllers: lists 1, 3" in (out / f"en/r/680072/m/{s.municipality_code}.html").read_text(
        encoding="utf-8")
    assert "Kontrolora ukupno" in mun and "Kontrolora ukupno" in round_page
    # the observers' record and the remark are linked by name, and the remark is a flag
    row = mun[mun.index('id="bm-23"'):]
    row = row[:row.index("</tr>")]
    assert 'class="doc doc-observers"' in row and ">Posmatrači</a>" in row and ">Primedba</a>" in row
    assert "Primedba uz zapisnik" in row and "%D0%9F%D1%80%D0%B8%D0%BC%D0%B5%D0%B4%D0%B1%D0%B0" in row  # link encoded
    assert "Primedbe posmatrača" in row and "Gužva ispred biračkog mesta" in row and "pročitano 4.11.2026." in row
    place = re.search(r'href="\.\./\.\./\.\./(s/[^"]+\.html)"', row).group(1)
    page = (out / place).read_text(encoding="utf-8")
    assert re.search(r"Zapisnik o posmatračima objavljen|O posmatračima za \d od \d izbora", page)
    assert ">Observers</a>" in (out / "en" / place).read_text(encoding="utf-8")
    # the decisions on its polling board are linked on its page, apart from the documents of the vote
    board = page[page.index("Rešenja o biračkom odboru:"):]
    board = board[:board.index("</div>")]
    assert re.findall(r">([^<]+)</a>", board) == ["stalni sastav", "prošireni sastav"]  # one without a link: not shown
    assert "%D0%A0%D0%B5%D1%88%D0%B5%D1%9A%D0%B5%20%D0%BF%D1%80%D0%BE%D1%88%D0%B8%D1%80%D0%B5%D0%BD%D0%B8" in board
    assert "Decisions on the polling board:" in (out / "en" / place).read_text(encoding="utf-8")
    assert "Rešenja o biračkom odboru" not in mun  # the municipality's list keeps to the documents of the vote
    commission_part = mun[mun.index('id="commission"'):]
    assert "Dokumenti izborne komisije" in commission_part
    assert re.findall(r">([^<]+)</a>", commission_part)[:3] == ["3.11.2026. (1)", "3.11.2026. (2)", "14.10.2026."]
    assert "Zapisnici sa sednica" in commission_part and "%D0%97%201.pdf" in commission_part
    api = json.loads((out / "api" / place.replace(".html", ".json")).read_text(encoding="utf-8"))
    kinds = [d["kind"] for e in api["elections"] if e["round"] == "680072" for d in e["documents"]]
    assert kinds == ["minutes", "observers", "remark", "board_standing", "board_extended"]
    assert "Zapisano na biračkom mestu" in (out / "about.html").read_text(encoding="utf-8")
    order = [round_page.index(f'id="{x}"') for x in ("check", "results", "controllers", "municipalities", "stats")]
    assert order == sorted(order)
    # the Explore page's data: lists 1 and 3 appointed a member or deputy (bits 0 and 2), and an observers' record
    cols = json.loads((out / "api/r/680072/stations.json").read_text(encoding="utf-8"))["stations"]
    i = next(k for k in range(len(cols["mc"])) if cols["mc"][k] == s.municipality_code and cols["no"][k] == "23")
    assert cols["ctrl"][i] == 0b101 and cols["obs"][i] == 1
    assert cols["ctrl"][i - 1] is None  # no decision read: unknown, not "no controller"


def test_site_station_pages_and_breadcrumbs(site):
    out = site
    pages = sorted((out / "s").glob("*.html"))
    assert pages, "a page for every polling place"
    text = pages[0].read_text(encoding="utf-8")
    assert 'class="crumbs"' in text and "Kroz sve izbore" in text
    assert 'class="crumbs"' in (out / "r/680072/check.html").read_text(encoding="utf-8")
    assert (out / "elections.html").exists() and (out / "search.json").exists()


def test_search_leads_to_pages_across_elections(site):
    """Every search result opens a page across all elections: a municipality page with a row per election, and a
    page for every polling place, flagged or not."""
    for prefix in ("", "cyr/", "en/"):
        data = json.loads((site / prefix / "search.json").read_text(encoding="utf-8"))
        assert all(len(m) == 3 and m[2] >= 1 for m in data["m"])
        for m in data["m"]:
            assert (site / prefix / f"m/{m[1]}.html").exists(), m
        for s in data["s"]:
            mi, number, _, page, k, n, _ = s
            page = page or f"{data['m'][mi][1]}-{re.sub(r'[^0-9A-Za-z_-]', '_', number)}"
            assert (site / prefix / f"s/{page}.html").exists(), s
            assert 0 <= k <= n
    data = json.loads((site / "search.json").read_text(encoding="utf-8"))
    assert len(data["s"]) == len(list((site / "s").glob("*.html")))
    flagged = [s for s in data["s"] if s[4]]
    assert flagged and data["s"][:len(flagged)] == flagged  # flagged places first


def test_municipality_across_elections(site):
    # Novi Sad voted in the presidential 2022, parliamentary 2023, provincial 2023 and parliamentary 2026 elections
    page = (site / "m/89010.html").read_text(encoding="utf-8")
    rows = re.findall(r'<th scope="row" role="rowheader" class="election"><a href="\.\./r/(\d+)/m/89010\.html">', page)
    assert rows == ["680072", "341143", "341140", "42732"]  # newest first, one row each
    assert "Opština nije glasala na: Lokalni 2024" in page
    assert "7 od 221 biračkih mesta za proveru" in page
    assert "207 (Predsednički 2022) → 221 · novih" in page
    assert 'href="../r/680072/check.html#m-89010"' in page
    assert 'href="../s/89010-140.html"' in page and "Biračka mesta kroz izbore" in page
    # round pages link to it, and their stations to their own pages
    mun = (site / "r/680072/m/89010.html").read_text(encoding="utf-8")
    assert 'href="../../../m/89010.html"' in mun and 'href="../../../s/89010-1.html"' in mun


def test_results_by_settlement(site, archive):
    """Each election's page by kind of settlement: in the round's navigation, every list's share and controllers by
    class as bysettlement computes them, and the tables as CSV."""
    from izbori import boards, bysettlement, settlements
    from izbori.i18n import fmt_pct

    for prefix in ("", "cyr/", "en/"):
        for rid in archive.round_ids():
            assert (site / prefix / f"r/{rid}/settlements.html").exists(), prefix + rid
    page = (site / "r/680072/settlements.html").read_text(encoding="utf-8")
    assert re.search(r'<a href="[^"]*settlements\.html" aria-current="page">Naselja</a>', page)
    assert 'href="../../r/680072/settlements.html"' in (site / "r/680072/index.html").read_text(encoding="utf-8")
    heads = re.findall(r"<h2[^>]*>([^<]+)</h2>", page)
    assert heads == ["Gradska i ostala naselja", "Naselja po broju stanovnika", "Naselja po promeni broja stanovnika",
                     "Kako je napravljeno"]
    rnd = archive.load("680072")
    r = bysettlement.analyse(rnd.stations, rnd.contestants, settlements.load_store(archive.dir("680072"))["stations"],
                             settlements.load_figures(archive.root),
                             boards.coverage(boards.load_store(archive.dir("680072"))))
    first = r["rows"][0]
    row = re.search(rf"<tr><th scope=\"row\">{first['number']}\. [^<]+</th>(.*?)</tr>", page).group(1)
    cells = re.findall(r">([^<]+)</td>", row)
    assert cells[:3] == [fmt_pct(v, "lat") for v in [first["votes_all"], *first["votes"]["type"]]]
    assert "Biračka mesta na kojima je lista imala kontrolora" in page and "Unutar opština" in page
    assert f"Naselje je poznato za {r['used']:,}".replace(",", ".") in page
    lines = (site / "api/r/680072/settlements.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("dimension,class,number,contestant") and len(lines) == 1 + 11 * len(rnd.contestants)
    # no decisions on polling boards were read for the presidential election of 2022: its votes only
    pres = (site / "en/r/42732/settlements.html").read_text(encoding="utf-8")
    assert "Share of valid votes" in pres and "had a controller" not in pres and "No controllers here" in pres


def test_municipality_page_order(site, archive):
    """A municipality in one election, in the order the maintainer chose: the result in per cent first, then the
    stations (site.js shows the first ten and a button for the rest), the votes of the three lists with most votes
    at each station with a total, every list at every station behind a button, and everything else."""
    from izbori.i18n import fmt_int, fmt_pct

    page = (site / "r/680072/m/70351.html").read_text(encoding="utf-8")
    heads = re.findall(r"<h2[^>]*>([^<]+)</h2>", page)
    assert heads[:4] == ["Rezultat u opštini", "Biračka mesta", "Glasovi po biračkim mestima",
                         "Sve liste na svim biračkim mestima"]
    assert heads.index("Kontrolori u biračkim odborima") == 4
    assert 'class="tiles"' not in page  # the tiles' figures are lines under the result and the stations
    assert "Glasalo je " in page and " · izlaznost " in page

    rnd = archive.load("680072")
    sts = sorted((s for s in rnd.stations if s.municipality_code == "70351"), key=lambda s: int(s.number))
    assert f'data-first="10" data-more="Prikaži sva biračka mesta ({len(sts)})"' in page
    counted = [s for s in sts if s.counted]
    totals = [sum(s.votes[i] or 0 for s in counted) for i in range(len(rnd.contestants))]
    top = sorted(range(len(totals)), key=lambda i: -totals[i])[:3]
    table = page[page.index('<table class="compact by-station">'):]
    table = table[:table.index("</table>")]
    # each station's votes for the three, shaded and titled by the share
    first = counted[0]
    valid = sum(v or 0 for v in first.votes)
    cells = re.findall(r'<td class="num heat" style="--h: \d+%" title="([^"]+)">([^<]+)</td>', table)[:3]
    assert cells == [(fmt_pct(first.votes[i] / valid, "lat"), fmt_int(first.votes[i], "lat")) for i in top]
    # the total row adds up to the municipality
    total = re.search(r'<tr class="total">(.*?)</tr>', table).group(1)
    shown = re.findall(r'<td class="num"[^>]*>([^<]+)</td>', total)
    rest = sum(totals) - sum(totals[i] for i in top)
    assert shown == [fmt_int(totals[i], "lat") for i in top] + [fmt_int(rest, "lat"), fmt_int(sum(totals), "lat")]
    # the whole table behind a button that says what it is, and a CSV made from it in the browser
    assert '<details class="all-votes">\n  <summary class="button secondary">Cela tabela</summary>' in page
    assert 'data-table-csv="#all-votes-table"' in page and 'data-file="680072-70351.csv"' in page

    en = (site / "en/r/680072/m/70351.html").read_text(encoding="utf-8")
    assert "Show all polling stations (" in en and "Every list at every polling station" in en
    assert "registered voters voted · turnout" in en
    pres = (site / "r/42732/m/70351.html").read_text(encoding="utf-8")
    assert "Svi kandidati na svim biračkim mestima" in pres and "tri kandidata sa najviše glasova" in pres


def test_place_across_elections(site):
    # Zemun's gymnasium was station 10 until 2023 and is 14 since 2024: one place, found by its name
    page = (site / "s/70157-14.html").read_text(encoding="utf-8")
    rows = re.findall(r'<a href="\.\./r/(\d+)/m/70157\.html#bm-(\d+)">', page)
    assert rows == [("680072", "14"), ("567956", "14"), ("341140", "10"), ("42732", "10")]
    assert "isto mesto po nazivu" in page
    # the analysis on top: flags and invalid ballots, turnout, most votes, then how the place changed
    analysis = re.search(r'<section class="analysis".*?</section>', page, re.S).group(0)
    assert "Najnoviji izbori: Parlamentarni 2026 · poređenje sa opštinom" in analysis
    order = [analysis.index(x) for x in ("<dt>Oznake</dt>", "Bez oznake ni na jednim od 4 izbora", "Nevažeći ",
                                         "<dt>Izlaznost</dt>", "70,4% · ", "Studentska lista 71,8%",
                                         "Ranije BM 10 (Parlamentarni 2023, Predsednički 2022)")]
    assert order == sorted(order)
    assert "Pokrajinski 2023" not in analysis  # not held in Belgrade, so not a gap in this station's history
    en = (site / "en/s/70157-14.html").read_text(encoding="utf-8")
    assert "Earlier No. 10 (Parliamentary 2023, Presidential 2022)" in en
    # a school that held stations 134 and 140 in 2023 kept only 140 in 2026; station 134 of 2026 is another place
    # with another name, so the number alone doesn't join it to the school's old 134
    def stations(path):
        return re.findall(r'<a href="\.\./r/(\d+)/m/89010\.html#bm-(\d+)">', (site / path).read_text(encoding="utf-8"))
    assert stations("s/89010-140.html") == [("680072", "140"), ("341143", "140"), ("341140", "140"), ("42732", "140")]
    assert stations("s/89010-134-341143.html") == [("341143", "134"), ("341140", "134"), ("42732", "134")]
    assert stations("s/89010-134.html") == [("680072", "134")]
    assert "JOVAN POPOVIĆ" in (site / "s/89010-134-341143.html").read_text(encoding="utf-8")
    assert "RADOSNO DETINJSTVO" in (site / "s/89010-134.html").read_text(encoding="utf-8")
    # the top three use names without the words every list's name starts with
    assert "1. ALEKSANDAR VUČIĆ - SRBIJA NE SME DA STANE" in page
    assert "IZBORNA LISTA KANDIDATA" not in page.split('title="')[0]


def test_incremental_build_matches_a_full_build(tmp_path, archive, monkeypatch):
    """An incremental build renders only pages whose data changed, and ends up byte for byte like a full build:
    with no change, after a station's numbers change, and after a whole round is removed."""
    import csv
    import filecmp
    import io
    import shutil

    from izbori.history import Archive
    from izbori.site import Site

    data = tmp_path / "data"
    for rid in ("341143", "567956"):  # two small rounds keep the test quick
        shutil.copytree(archive.dir(rid), data / "rounds" / rid)
    from izbori import settlements
    for f in settlements.FIGURE_TABLES:  # the census, for the pages by kind of settlement
        (data / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(archive.root / f, data / f)

    def same(a, b):
        cmp = filecmp.dircmp(a, b)
        stack = [cmp]
        while stack:
            c = stack.pop()
            assert not (c.left_only or c.right_only or c.diff_files or c.funny_files), (c.left, c.left_only,
                                                                                       c.right_only, c.diff_files)
            stack.extend(c.subdirs.values())
        return True

    def run(out, incremental):
        site = Site(Archive(data), out, None, "https://example.org/x/", incremental=incremental)
        site.build()
        return site

    full = run(tmp_path / "a" / "site", False)
    assert full.kept == 0
    shutil.copytree(tmp_path / "a", tmp_path / "b")
    again = run(tmp_path / "b" / "site", True)
    assert again.kept > 1000 and again.rendered < full.rendered / 10  # only what every build writes (feeds, search)
    assert same(tmp_path / "a" / "site", tmp_path / "b" / "site")

    # a correction at one Belgrade station
    f = data / "rounds/567956/results.csv"
    rows = list(csv.DictReader(io.StringIO(f.read_bytes().decode("utf-8-sig"))))
    rows[0]["upisani_biraci"] = str(int(rows[0]["upisani_biraci"]) + 50)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    f.write_bytes(("﻿" + out.getvalue()).encode("utf-8"))
    changed = run(tmp_path / "b" / "site", True)
    assert changed.kept > 1000 and changed.rendered < full.rendered / 2
    run(tmp_path / "c" / "site", False)
    assert same(tmp_path / "c" / "site", tmp_path / "b" / "site")

    # a decision on a polling board gets its link, and the station's commission publishes a document
    import json
    b = data / "rounds/567956/boards.json"
    store = json.loads(b.read_text(encoding="utf-8"))
    entry = next(v for v in store["docs"].values() if v.get("s"))
    entry["u"] = "/extfile/sr/files/additionalDocuments/1/2/Решење.pdf"
    b.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    cdocs = {"complete": True, "docs": {"9": {"m": entry["s"].split("/")[0], "c": "session", "t": "1793700000",
                                              "u": "/extfile/sr/files/additionalDocuments/1/3/З.pdf"}}}
    (data / "rounds/567956/commission.json").write_text(json.dumps(cdocs, ensure_ascii=False), encoding="utf-8")
    run(tmp_path / "b" / "site", True)
    run(tmp_path / "e" / "site", False)
    assert same(tmp_path / "e" / "site", tmp_path / "b" / "site")
    # the commissions page counts the commission's new document (its inputs are the round's)
    table = csv.DictReader(io.StringIO((tmp_path / "b/site/api/r/567956/commissions.csv").read_text(encoding="utf-8")))
    assert {r["code"]: r["commission_documents"] for r in table}[entry["s"].split("/")[0]] == "1"

    # a station's settlement is corrected: the page by kind of settlement is built again
    s = data / "rounds/567956/settlements.json"
    store = json.loads(s.read_text(encoding="utf-8"))
    key, e = next((k, v) for k, v in store["stations"].items() if v["s"] != "Борча")
    store["stations"][key] = {"u": "Палилула", "s": "Борча", "m": "manual"}
    s.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    before = (tmp_path / "b/site/r/567956/settlements.html").read_text(encoding="utf-8")
    run(tmp_path / "b" / "site", True)
    assert (tmp_path / "b/site/r/567956/settlements.html").read_text(encoding="utf-8") != before
    run(tmp_path / "g" / "site", False)
    assert same(tmp_path / "g" / "site", tmp_path / "b" / "site")

    # a document of Belgrade's city commission, which RIK lists under the city: shown with every city municipality.
    # These two elections don't say which municipalities are Belgrade's (2022 and 2026 do), so the test says it;
    # the pages made from that knowledge are built again, as it may come from any election
    from izbori import commission
    codes = {row["sifra_opstine"] for row in csv.DictReader(io.StringIO(
        (data / "rounds/567956/results.csv").read_bytes().decode("utf-8-sig")))}
    monkeypatch.setattr(commission, "city_parts", lambda stations: {c: ("name", "BEOGRAD") for c in codes})
    cdocs["docs"]["10"] = {"m": "", "n": "Град Београд", "c": "decision", "t": "1793700100",
                           "u": "/extfile/sr/files/additionalDocuments/1/4/Р.pdf"}
    (data / "rounds/567956/commission.json").write_text(json.dumps(cdocs, ensure_ascii=False), encoding="utf-8")
    run(tmp_path / "b" / "site", True)
    run(tmp_path / "f" / "site", False)
    assert same(tmp_path / "f" / "site", tmp_path / "b" / "site")
    table = list(csv.DictReader(io.StringIO((tmp_path / "b/site/api/r/567956/commissions.csv").read_text(
        encoding="utf-8"))))
    assert {r["city_commission_documents"] for r in table} == {"1"}
    page = (tmp_path / "b/site/r/567956/m/70092.html").read_text(encoding="utf-8")
    assert 'id="city-commission"' in page and "additionalDocuments/1/4/" in page

    # a round leaves the archive: its pages and its places' pages go
    shutil.rmtree(data / "rounds/341143")
    run(tmp_path / "b" / "site", True)
    assert not (tmp_path / "b" / "site" / "r" / "341143").exists()
    run(tmp_path / "d" / "site", False)
    assert same(tmp_path / "d" / "site", tmp_path / "b" / "site")
