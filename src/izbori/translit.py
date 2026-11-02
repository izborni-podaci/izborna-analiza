"""Serbian Cyrillic to Latin, letter by letter, plus the few other Cyrillic letters that turn up in RIK's data.
Anything else passes through."""

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


def latin(text: str | None) -> str:
    """Transliterate Serbian Cyrillic to Latin. Lj, Nj and Dž become all caps inside all-caps words."""
    if not text:
        return ""
    out = []
    n = len(text)
    for i, ch in enumerate(text):
        up = ch.upper()
        m = _MAP.get(up)
        if m is None:
            out.append(ch)
            continue
        if ch != up:
            out.append(m.lower())
            continue
        if len(m) > 1:
            nxt = text[i + 1] if i + 1 < n else ""
            prev = text[i - 1] if i > 0 else ""
            if nxt.isalpha():
                caps = nxt.isupper()
            else:
                caps = prev.isalpha() and prev.isupper()
            if caps:
                out.append(m.upper())
                continue
        out.append(m)
    return "".join(out)


def has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in text)
