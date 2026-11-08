"""Email digest of new flags: at most one message every 15 minutes, plus one when a count completes.

Settings come from the environment (GitHub secrets): SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
MAIL_FROM, MAIL_TO (comma-separated). Recipients are only ever passed to the mail server, never written
into a header or the repository. State (what's pending, when the last message went) is in data/mail.json."""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from izbori.feed import entry_title, flag_lines
from izbori.history import Archive
from izbori.i18n import PREFIX, fmt_int, latin_page, parse_time, t

MIN_INTERVAL = timedelta(minutes=15)


def settings(env=os.environ) -> dict | None:
    s = {k: (env.get(k) or "").strip() for k in
         ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO")}
    if not (s["SMTP_HOST"] and s["MAIL_FROM"] and s["MAIL_TO"]):
        return None
    s["recipients"] = [a.strip() for a in s["MAIL_TO"].split(",") if a.strip()]
    s["port"] = int(s["SMTP_PORT"] or 587)
    return s


def _path(data_root: Path) -> Path:
    return Path(data_root) / "mail.json"


def load_state(data_root: Path) -> dict:
    p = _path(data_root)
    state = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    state.setdefault("last_sent", None)
    state.setdefault("pending", [])
    state.setdefault("final_pending", [])
    state.setdefault("final_sent", [])
    return state


def save_state(data_root: Path, state: dict) -> None:
    _path(data_root).write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                encoding="utf-8")


def queue(data_root: Path, entry: dict | None = None, final_round: str | None = None) -> None:
    state = load_state(data_root)
    if entry:
        state["pending"].append({"t": entry["t"], "round": entry["round"], "title": entry["title"],
                                 "kind": entry.get("kind", ""), "counted": entry["counted"],
                                 "total": entry["total"], "flags": entry["flags"]})
    if final_round and final_round not in state["final_sent"] and final_round not in state["final_pending"]:
        state["final_pending"].append(final_round)
    save_state(data_root, state)


def compose(state: dict, archive: Archive, site_url: str) -> EmailMessage:
    n = sum(len(e["flags"]) for e in state["pending"])
    finals = state["final_pending"]
    parts_sr, parts_en = [], []
    for rid in finals:
        meta = archive.meta(rid)
        parts_sr.append(t("mail_final", "cyr", title=meta.get("title", rid)))
        parts_en.append(t("mail_final", "en", title=meta.get("title_en") or latin_page(meta.get("title", rid))))
    if state["pending"]:
        parts_sr.append(t("mail_intro", "cyr"))
        parts_en.append(t("mail_intro", "en"))
    for e in state["pending"]:
        for loc, parts in (("cyr", parts_sr), ("en", parts_en)):
            parts.append("")
            parts.append(f"{entry_title(e, loc, archive)} — " + t("counted_of", loc, counted=fmt_int(e["counted"], loc),
                                                                  total=fmt_int(e["total"], loc)))
            parts.extend(f"- {line}" for line in flag_lines(e, loc, archive, limit=None))
            parts.append(f"{site_url}{PREFIX[loc]}r/{e['round']}/check.html")
    parts_sr += ["", t("mail_footer", "cyr")]
    parts_en += ["", t("mail_footer", "en")]
    body = latin_page("\n".join(parts_sr)) + "\n\n" + "—" * 20 + " English " + "—" * 20 + "\n\n" + "\n".join(parts_en)
    msg = EmailMessage()
    if n:
        subject = latin_page(t("mail_subject", "cyr", n=fmt_int(n, "lat"))) + " / " + t("mail_subject", "en",
                                                                                          n=fmt_int(n, "en"))
    else:
        subject = latin_page(t("mail_final", "cyr", title="")).rstrip(": ") + " / " + \
            t("mail_final", "en", title="").rstrip(": ")
    msg["Subject"] = "[Izborni podaci] " + subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=site_url.split("://", 1)[-1].split("/", 1)[0])
    msg.set_content(body + "\n")
    return msg


def send(msg: EmailMessage, s: dict) -> None:
    msg["From"] = s["MAIL_FROM"]
    msg["To"] = s["MAIL_FROM"]  # recipients get it as blind copies
    context = ssl.create_default_context()
    if s["port"] == 465:
        server = smtplib.SMTP_SSL(s["SMTP_HOST"], s["port"], context=context, timeout=60)
    else:
        server = smtplib.SMTP(s["SMTP_HOST"], s["port"], timeout=60)
        server.starttls(context=context)
    with server:
        if s["SMTP_USER"]:
            server.login(s["SMTP_USER"], s["SMTP_PASSWORD"])
        server.send_message(msg, from_addr=s["MAIL_FROM"], to_addrs=s["recipients"])


def maybe_send(data_root: Path, archive: Archive, site_url: str, now: datetime, env=os.environ,
               sender=send) -> bool:
    s = settings(env)
    state = load_state(data_root)
    if not s:
        if state["pending"] or state["final_pending"]:
            state["pending"], state["final_pending"] = [], []
            save_state(data_root, state)
        return False
    if not state["pending"] and not state["final_pending"]:
        return False
    last = parse_time(state["last_sent"])
    if not state["final_pending"] and last is not None and now - last < MIN_INTERVAL:
        return False
    sender(compose(state, archive, site_url), s)
    state["last_sent"] = now.replace(microsecond=0).isoformat()
    state["final_sent"] += state["final_pending"]
    state["pending"], state["final_pending"] = [], []
    save_state(data_root, state)
    return True
