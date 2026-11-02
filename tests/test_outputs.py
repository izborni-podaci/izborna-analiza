"""Site, feeds, email digest and the private target list."""

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

from izbori import feed, mail, targets
from izbori.site import build

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def test_site(tmp_path, archive):
    out = build(archive, tmp_path / "site", None, "https://example.org/x/")
    for prefix in ("", "cyr/", "en/"):
        for page in ("index.html", "guide.html", "about.html", "r/680072/index.html", "r/680072/check.html",
                     "r/680072/changes.html"):
            assert (out / prefix / page).exists(), prefix + page
    assert len(list((out / "r/680072/m").glob("*.html"))) == 191

    # Latin and English pages carry no Cyrillic except the name of the Cyrillic switch
    for path in list(out.glob("*.html")) + list((out / "r").rglob("*.html")) + list((out / "en").rglob("*.html")):
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
