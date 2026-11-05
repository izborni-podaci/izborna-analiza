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
                     "r/680072/changes.html"):
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

    # the home page: the latest election beside the search, by group of flags; the archive in numbers; six ways in
    home = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="status"' in home and 'href="r/680072/check.html#g-paper"' in home and "Sa oznakom: " in home
    assert "Izbora u arhivi: " in home and "dokumenata sa sajta RIK-a: " in home
    for target in ('href="municipalities.html"', 'href="about.html#podaci"', 'href="r/680072/index.html#controllers"',
                   'href="guide.html"', 'href="repeat.html"'):
        assert target in home, target
    assert "data-next" not in home  # no election ahead in data/elections.csv
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
    assert "data-next" in home and f'data-days-until="{day.isoformat()}"' in home
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


def test_incremental_build_matches_a_full_build(tmp_path, archive):
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

    # a round leaves the archive: its pages and its places' pages go
    shutil.rmtree(data / "rounds/341143")
    run(tmp_path / "b" / "site", True)
    assert not (tmp_path / "b" / "site" / "r" / "341143").exists()
    run(tmp_path / "d" / "site", False)
    assert same(tmp_path / "d" / "site", tmp_path / "b" / "site")
