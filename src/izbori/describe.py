"""One line per flag with the numbers behind it, in each locale."""

from __future__ import annotations

import re

from izbori.checks import Flag
from izbori.i18n import fmt_int, fmt_num, fmt_pct, fmt_time, t

FIELD_KEYS = {
    "upisani_biraci": "registered", "glasali_biraci": "voted", "listici_u_kutiji": "ballots",
    "vazeci_glasovi": "valid", "nevazeci_listici": "invalid", "zapisnik_link": "field_minutes",
    "korekcija_dokument_link": "field_correction", "bm_naziv": "field_name", "*station*": "field_removed",
}

_TEXT = {
    "ballots_over_signed": ("У кутији {ballots} листића, потписало се {voted} бирача ({diff} листића више)",
                            "{ballots} ballots in the box, {voted} signatures ({diff} more ballots)"),
    "sum_mismatch": ("Збир гласова {sum}, важећих листића {valid}", "Votes add up to {sum}, valid ballots {valid}"),
    "ballot_mismatch": ("Важећих {valid} и неважећих {invalid}, у кутији {ballots}",
                        "{valid} valid and {invalid} invalid, {ballots} in the box"),
    "signed_over_ballots": ("Потписало се {voted} бирача, у кутији {ballots} листића ({diff} листића мање)",
                            "{voted} signatures, {ballots} ballots in the box ({diff} fewer ballots)"),
    "signed_over_registered": ("Гласало {voted}, уписано {registered}", "{voted} voted, {registered} registered"),
    "full_turnout_typo": ("Гласали свих {registered} уписаних; медијана излазности у општини {median}",
                          "All {registered} registered voted; municipality median turnout {median}"),
    "correction_still_odd": ("Решење о исправци {form}", "Correction ruling {form}"),
    "changed": ("Промењено: {items}", "Changed: {items}"),
    "minutes_replaced": ("Последња замена {last}, укупно {count}", "Last replaced {last}, {count} in total"),
    "correction_unapplied": ("Решење {form} појавило се {appeared}", "Ruling {form} appeared {appeared}"),
    "invalid_spike": ("Неважећих: {invalid} ({share})", "Invalid: {invalid} ({share})"),
    "invalid_spike_address": ("Неважећих: {invalid} ({share}); медијана на истој адреси {median}",
                              "Invalid: {invalid} ({share}); median at the same address {median}"),
    "invalid_spike_municipality": ("Неважећих: {invalid} ({share}); медијана у општини {median}",
                                   "Invalid: {invalid} ({share}); municipality median {median}"),
    "turnout_jump": ("Излазност {before} → {now}; медијана промене у општини {base} поена",
                     "Turnout {before} → {now}; municipality's median change {base} points"),
    "turnout_drop": ("Излазност {before} → {now}; медијана промене у општини {base} поена",
                     "Turnout {before} → {now}; municipality's median change {base} points"),
    "near_unanimity": ("Излазност {turnout}; {contestant}: {share} важећих гласова",
                       "Turnout {turnout}; {contestant}: {share} of valid votes"),
    "high_turnout": ("Излазност {turnout}, уписано {registered}", "Turnout {turnout}, {registered} registered"),
}


def field_label(field: str, loc: str, kind: str = "") -> str:
    if field in FIELD_KEYS:
        return t(FIELD_KEYS[field], loc)
    m = re.search(r"(\d+)$", field)
    if m:
        return t("field_candidate" if kind == "presidential" else "field_list", loc, n=m.group(1))
    return field


def _signed_pct(x: float, loc: str) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + fmt_pct(abs(x), loc)


def describe(flag: Flag, loc: str, contestant_label=lambda n: str(n), kind: str = "") -> str:
    d = flag.data
    i = lambda n: fmt_int(n, loc)  # noqa: E731
    p = lambda x: fmt_pct(x, loc)  # noqa: E731
    code = flag.code
    if code == "invalid_spike" and d.get("basis") in ("address", "municipality"):
        code = f"invalid_spike_{d['basis']}"
    sr, en = _TEXT[code]
    text = en if loc == "en" else sr
    values: dict = {}
    if flag.code in ("ballots_over_signed", "signed_over_ballots", "signed_over_registered", "sum_mismatch",
                     "ballot_mismatch", "full_turnout_typo", "high_turnout"):
        values = {k: (i(v) if isinstance(v, int) else p(v) if isinstance(v, float) else v) for k, v in d.items()}
    elif flag.code == "correction_still_odd":
        values = {"form": d.get("form") or ""}
    elif flag.code == "changed":
        parts = [f"{field_label(f, loc, kind)} {d['first'].get(f) or '—'} → {d['now'].get(f) or '—'}"
                 for f in d["fields"][:3]]
        if len(d["fields"]) > 3:
            parts.append("…")
        values = {"items": "; ".join(parts)}
    elif flag.code == "minutes_replaced":
        values = {"last": fmt_time(d["last"], loc), "count": i(d["count"])}
    elif flag.code == "correction_unapplied":
        values = {"form": d.get("form") or "", "appeared": fmt_time(d["appeared"], loc)}
    elif flag.code == "invalid_spike":
        values = {"invalid": i(d["invalid"]), "share": p(d["share"]),
                  "median": p(d["median"]) if "median" in d else ""}
    elif flag.code in ("turnout_jump", "turnout_drop"):
        n = 100 * d.get("base", d.get("national", 0))
        values = {"before": p(d["before"]), "now": p(d["now"]),
                  "base": ("+" if n > 0 else "−" if n < 0 else "") + fmt_num(abs(n), loc)}
    elif flag.code == "near_unanimity":
        values = {"turnout": p(d["turnout"]), "contestant": contestant_label(d["contestant"]), "share": p(d["share"])}
    return " ".join(text.format(**values).split())
