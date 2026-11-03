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

    # Latin and English pages carry no Cyrillic except the name of the Cyrillic switch
    for path in [*out.glob("*.html"), *(out / "r").rglob("*.html"), *(out / "s").glob("*.html"),
                 *(out / "m").glob("*.html"), *(out / "en").rglob("*.html")]:
        text = path.read_text(encoding="utf-8").replace("Ћирилица", "")
        assert not CYRILLIC.search(text), path
    assert CYRILLIC.search((out / "cyr/r/680072/index.html").read_text(encoding="utf-8"))

    page = (out / "r/680072/check.html").read_text(encoding="utf-8")
    assert "Bosilegrad" in page and "BM 21" in page
    # links to RIK documents are percent-encoded, so they survive transliteration
    hrefs = re.findall(r'href="(https://rik[^"]+)"', page)
    assert hrefs and all(not CYRILLIC.search(h) for h in hrefs)
    # nothing loaded from other servers
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8").replace("https://example.org/x/", "")  # the site's own address
        assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', text), path
    assert "https://example.org/x/static/site.css" in (out / "404.html").read_text(encoding="utf-8")


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
    shutil.copytree(archive.root, data)
    rnd = archive.load("680072")
    s = next(x for x in rnd.stations if x.municipality == "Дољевац" and x.number == "23")
    store = {"docs": {"x": {"s": s.key, "k": "extended", "r": False, "t": "1", "unmatched": 0,
                            "addr": "ОШ ПРИМЕР, ГЛАВНА 1", "slots": [[1, True, True], [3, True, False], [2, False, False]]}}}
    (data / "rounds/680072/boards.json").write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    out = build(Archive(data), tmp_path / "site", None, "https://example.org/x/")
    round_page = (out / "r/680072/index.html").read_text(encoding="utf-8")
    assert "Kontrolori u biračkim odborima" in round_page
    mun = (out / f"r/680072/m/{s.municipality_code}.html").read_text(encoding="utf-8")
    assert "Kontrolori: liste 1, 3" in mun and "od 18" not in mun and "OŠ PRIMER, GLAVNA 1" in mun
    assert "Controllers: lists 1, 3" in (out / f"en/r/680072/m/{s.municipality_code}.html").read_text(
        encoding="utf-8")
    assert "Kontrolora ukupno" in mun and "Kontrolora ukupno" in round_page
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
    rows = re.findall(r'<th scope="row" class="election"><a href="\.\./r/(\d+)/m/89010\.html">', page)
    assert rows == ["680072", "341143", "341140", "42732"]  # newest first, one row each
    assert "Opština nije glasala na: Lokalni 2024." in page
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
    assert "isto mesto po nazivu" in page and "Ranije: BM 10" in page
    assert "Nije glasalo na: Pokrajinski 2023." in page
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
