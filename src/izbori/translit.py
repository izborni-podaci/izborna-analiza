"""Serbian Cyrillic to Latin, letter by letter, plus the few other Cyrillic letters that turn up in RIK's data.
Anything else passes through."""

import re

_MAP = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z",
    "И": "I", "Ј": "J", "К": "K", "Л": "L", "Љ": "Lj", "М": "M", "Н": "N", "Њ": "Nj", "О": "O",
    "П": "P", "Р": "R", "С": "S", "Т": "T", "Ћ": "Ć", "У": "U", "Ф": "F", "Х": "H", "Ц": "C",
    "Ч": "Č", "Џ": "Dž", "Ш": "Š",
    # Not Serbian, but they turn up in scanned documents read by OCR (Roman numerals read as І) and in
    # foreign place names abroad; without them a Latin page would show Cyrillic letters.
    "І": "I", "Ї": "I", "Є": "E", "Ґ": "G", "Й": "J", "Ы": "Y", "Э": "E", "Ё": "E", "Ў": "U",
    "Ю": "Ju", "Я": "Ja", "Щ": "Šč", "Ъ": "", "Ь": "",
}


def _table() -> dict[int, str]:
    """Every Cyrillic letter, capital or small, whose capital is in the map."""
    table = {}
    for cp in [*range(0x0400, 0x0530), *range(0x1C80, 0x1C90), *range(0x2DE0, 0x2E00), *range(0xA640, 0xA6A0)]:
        ch = chr(cp)
        m = _MAP.get(ch.upper())
        if m is not None:
            table[cp] = m if ch == ch.upper() else m.lower()
    return table


_TABLE = _table()
_WIDE = re.compile("[" + "".join(k for k, v in _MAP.items() if len(v) > 1) + "]")  # capitals that become two letters
_RUN = re.compile("[Ѐ-ԯᲀ-᲏ⷠ-ⷿꙀ-ꚟ]+")  # whole pages are mostly not Cyrillic


def _wide(match: re.Match) -> str:
    """Lj, Nj, Dž and the like: all caps when the next letter is a capital, or, at the end of a word, the one
    before."""
    text, i = match.string, match.start()
    m = _MAP[match.group()]
    nxt = text[i + 1] if i + 1 < len(text) else ""
    prev = text[i - 1] if i > 0 else ""
    caps = nxt.isupper() if nxt.isalpha() else prev.isalpha() and prev.isupper()
    return m.upper() if caps else m


def _run(match: re.Match) -> str:
    return match.group().translate(_TABLE)


def latin(text: str | None) -> str:
    """Transliterate Serbian Cyrillic to Latin. Lj, Nj and Dž become all caps inside all-caps words."""
    if not text:
        return ""
    return _RUN.sub(_run, _WIDE.sub(_wide, text))


def has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in text)
