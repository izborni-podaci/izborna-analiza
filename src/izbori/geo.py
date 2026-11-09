"""Municipal boundaries for the map on the Explore page, from OpenStreetMap.

OpenStreetMap's Serbian boundaries came from the cadastre's open register of spatial units, and they carry its
municipality and city codes (`ref:RS:opstina`, `ref:RS:grad`): the same matični broj RIK uses, so each boundary
joins RIK's municipalities by code. `izbori geo` fetches them once, on a GitHub runner, through the Overpass API,
simplifies them to what a map of the whole country needs and writes data/geo/municipalities.json. The file is a
database derived from OpenStreetMap, so it is under the ODbL and every map built from it names its source.

Shapely assembles and simplifies the polygons. It is needed only by this command, not to build the site, so it isn't
a dependency of the package: the workflow runs `uv run --with shapely izbori geo`."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
QUERY = """[out:json][timeout:900];
(
  relation["boundary"="administrative"]["ref:RS:opstina"];
  relation["boundary"="administrative"]["ref:RS:grad"];
);
out geom;"""
AGENT = "izborna-analiza (https://github.com/izborni-podaci/izborna-analiza)"
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE = "ODbL 1.0, https://opendatacommons.org/licenses/odbl/1-0/ (data: https://www.openstreetmap.org/copyright)"
TOLERANCE = 0.003  # degrees, about 250 m: a pixel or less on a map of the whole country
DIGITS = 4  # about 10 m


def fetch(query: str = QUERY, timeout: int = 960) -> dict:
    """The relations with their member ways' geometry, from the first Overpass server that answers."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt, url in enumerate(OVERPASS * 2):  # each server twice; a 504 at a busy hour is common
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - a busy server: try the next one
            last = e
            time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"Overpass didn't answer: {last}")


def geometry(relation: dict):
    """A relation's area: the outer ways joined into rings, less the inner ones. None when the outer ways don't
    close."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    lines: dict[str, list] = {"outer": [], "inner": []}
    for m in relation.get("members", []):
        pts = [(p["lon"], p["lat"]) for p in m.get("geometry") or [] if p]
        if m.get("type") != "way" or len(pts) < 2:
            continue
        lines["inner" if m.get("role") == "inner" else "outer"].append(LineString(pts))
    if not lines["outer"]:
        return None

    def faces(ways):
        noded = unary_union(ways)  # joined and split where they meet, as polygonize needs
        return unary_union(list(polygonize(getattr(noded, "geoms", [noded]))))

    area = faces(lines["outer"])
    if lines["inner"]:
        area = area.difference(faces(lines["inner"]))
    return None if area.is_empty else area


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], DIGITS), round(coords[1], DIGITS)]
    return [_round(c) for c in coords]


def features(data: dict) -> list[dict]:
    """One feature per code: a municipality's own boundary where it has one, otherwise the city's."""
    from shapely import set_precision
    from shapely.geometry import mapping

    best: dict[str, tuple[int, dict]] = {}
    for rel in data.get("elements", []):
        tags = rel.get("tags", {})
        code = (tags.get("ref:RS:opstina") or tags.get("ref:RS:grad") or "").strip()
        if not code.isdigit():
            continue
        rank = 0 if tags.get("ref:RS:opstina") else 1
        if code in best and best[code][0] <= rank:
            continue
        area = geometry(rel)
        if area is None:
            continue
        area = set_precision(area.simplify(TOLERANCE, preserve_topology=True), 10 ** -DIGITS)
        if area.is_empty:
            continue
        shape = mapping(area)
        best[code] = (rank, {"type": "Feature",
                             "properties": {"code": code, "name": tags.get("name", ""),
                                            "level": tags.get("admin_level", "")},
                             "geometry": {"type": shape["type"], "coordinates": _round(shape["coordinates"])}})
    return [best[code][1] for code in sorted(best)]


def write(path: Path, feats: list[dict], fetched: str = "", source: str = "") -> None:
    """The boundaries as GeoJSON, one feature per line so git keeps a small diff when a few change. Those of
    Kosovo and Metohija come from another dataset, which the attribution and licence then name too."""
    kim = any(f["properties"].get("source") == "ELWar" for f in feats)
    head = {"type": "FeatureCollection",
            "attribution": ATTRIBUTION + (f"; Kosovo and Metohija: {KIM_SOURCE}" if kim else ""),
            "license": LICENSE + (f"; Kosovo and Metohija: {KIM_LICENSE}" if kim else ""),
            "source": source or f"OpenStreetMap through the Overpass API, {fetched}"}
    lines = [json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in feats]
    text = json.dumps(head, ensure_ascii=False)[:-1] + ', "features": [\n' + ",\n".join(lines) + "\n]}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# --- settlements -----------------------------------------------------------------------------------------------------
# Serbia's settlements (naselja) are in OpenStreetMap as administrative relations at admin_level 9 carrying the
# cadastre's settlement code (ref:RS:naselje). The census tables name settlements but carry no code, so a boundary
# joins the census by its municipality (the one its representative point falls in, from municipalities.json) and
# its name, normalised the way settlements.py matches RIK's names. A boundary that matches no census settlement is
# kept with an empty "census" and drawn grey.

SETTLEMENT_QUERY = """[out:json][timeout:1800][maxsize:1073741824];
area["ISO3166-1"="RS"]->.rs;
relation["boundary"="administrative"]["admin_level"="9"]["ref:RS:naselje"](area.rs);
out geom;"""
SETTLEMENT_TOLERANCE = 0.0004  # degrees, about 35 m: a pixel on a map of one municipality
SETTLEMENT_FILE = "settlements.json"


def settlement_features(data: dict, municipalities: list[dict], census_names, log=print) -> list[dict]:
    """One feature per settlement relation: its code, name, the RIK municipality whose boundary holds its
    representative point, and the census settlement it matches there (census_names(code) → {normalised name:
    printed name}; empty when the municipality has no census unit)."""
    from shapely import STRtree, set_precision
    from shapely.geometry import mapping, shape

    from izbori.settlements import norm

    polys, codes = [], []
    for f in municipalities:
        polys.append(shape(f["geometry"]))
        codes.append(f["properties"]["code"])
    tree = STRtree(polys) if polys else None
    out, unmatched, outside = [], 0, 0
    for rel in data.get("elements", []):
        tags = rel.get("tags", {})
        code = (tags.get("ref:RS:naselje") or "").strip()
        if not code:
            continue
        area = geometry(rel)
        if area is None:
            continue
        point = area.representative_point()
        hits = [i for i in tree.query(point) if polys[i].covers(point)] if tree else []
        if not hits:
            outside += 1
            continue
        mun = codes[min(hits, key=lambda i: polys[i].area)]  # a city municipality lies inside its city: the smaller wins
        name = tags.get("name") or tags.get("name:sr") or ""
        names = census_names(mun)
        match = names.get(norm(name), "") if names else ""
        if names and not match:
            unmatched += 1
        area = set_precision(area.simplify(SETTLEMENT_TOLERANCE, preserve_topology=True), 10 ** -DIGITS)
        if area.is_empty:
            continue
        shp = mapping(area)
        out.append({"type": "Feature",
                    "properties": {"code": code, "name": name, "municipality": mun, "census": match},
                    "geometry": {"type": shp["type"], "coordinates": _round(shp["coordinates"])}})
    out.sort(key=lambda f: (f["properties"]["municipality"], f["properties"]["code"]))
    log(f"settlements: {len(out)} boundaries, {unmatched} without a census match, {outside} outside every municipality")
    return out


def write_settlements(path: Path, feats: list[dict], fetched: str) -> None:
    head = {"type": "FeatureCollection", "attribution": ATTRIBUTION, "license": LICENSE,
            "source": f"OpenStreetMap through the Overpass API, {fetched}; admin_level 9 with ref:RS:naselje"}
    lines = [json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in feats]
    text = json.dumps(head, ensure_ascii=False)[:-1] + ', "features": [\n' + ",\n".join(lines) + "\n]}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def settlements_by_municipality(path: Path) -> dict[str, list[dict]]:
    """The settlement boundaries grouped by RIK municipality code; empty when the file isn't there."""
    data = load(path)
    out: dict[str, list[dict]] = {}
    for f in (data or {}).get("features", []):
        out.setdefault(f["properties"]["municipality"], []).append(f)
    return out


# --- Kosovo and Metohija, in RIK's division ------------------------------------------------------------------------
# OpenStreetMap maps Kosovo's municipalities as Kosovo divides them since 2000, which isn't how RIK counts there.
# RIK keeps the earlier division; its boundaries are in Glaurdić et al., a CC BY 4.0 dataset of the municipalities of
# Yugoslavia and its successor states, 1970-2020, deposited at the University of Luxembourg.

KIM_PAGE = "https://orbilu.uni.lu/handle/10993/58375"
KIM_SOURCE = ("Glaurdić, Kaniški, Budimir, Ondrejka (2021): Spatial data of municipalities in Yugoslavia and its "
              "successor states, 1970-2020. GESIS, https://doi.org/10.7802/2358")
KIM_LICENSE = "CC BY 4.0, https://creativecommons.org/licenses/by/4.0/"


def get(url: str, timeout: int = 900, context=None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as r:
            return r.read()
    except urllib.error.URLError as e:
        if context is not None or not isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            raise
    return get(url, timeout, completed_chain(urllib.parse.urlsplit(url).hostname))


def completed_chain(host: str) -> ssl.SSLContext:
    """A context that also knows the intermediate certificate a server leaves out of its chain, fetched from the
    address its own certificate names, as browsers do. The chain must still end at a root this system trusts:
    partial chains stay off, so the fetched certificate is only a missing link, never a trust anchor."""
    import tempfile
    leaf = ssl.get_server_certificate((host, 443))
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(leaf)
    issuers = ssl._ssl._test_decode_cert(f.name).get("caIssuers", ())  # noqa: SLF001 - the only decoder in ssl
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    for url in issuers:
        der = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}), timeout=60).read()
        ctx.load_verify_locations(cadata=der.decode() if der.startswith(b"-----") else ssl.DER_cert_to_PEM_cert(der))
    return ctx


def kim_archive(log=print) -> bytes:
    """The dataset's zip, from the link on its repository page."""
    import html as html_lib
    page = get(KIM_PAGE, 120).decode("utf-8", "replace")
    links = sorted({html_lib.unescape(h) for h in re.findall(r'href="([^"]+?\.zip[^"]*)"', page)})
    links += sorted({html_lib.unescape(h) for h in re.findall(r'href="([^"]*bitstream[^"]*)"', page)} - set(links))
    log(f"links on the page: {links}")
    for href in links:
        url = urllib.parse.urljoin(KIM_PAGE, href)
        try:
            data = get(url)
        except Exception as e:  # noqa: BLE001 - try the next link
            log(f"  {url}: {e}")
            continue
        log(f"  {url}: {len(data)} bytes, starts {data[:4]!r}")
        if data[:2] == b"PK":
            return data
    raise RuntimeError("the dataset's zip wasn't found on its page")


def inspect(data: bytes, log=print, pattern: str = r"(KOS|XK|SRB|SCG|YUG)[^/]*/(1991|1998|1999|2000|2020)\.dbf$") -> None:
    """What the archive holds: every file, and for the layers that may cover Kosovo in the 1990s, their fields,
    coordinate system and the first records (municipality names only, which are public)."""
    import io
    import zipfile

    import shapefile  # pyshp, only for this command

    def walk(zf: zipfile.ZipFile, prefix: str = ""):
        for info in zf.infolist():
            name = prefix + info.filename
            if info.filename.lower().endswith(".zip"):
                yield from walk(zipfile.ZipFile(io.BytesIO(zf.read(info))), name + "!")
            else:
                yield name, info.file_size, (lambda zf=zf, info=info: zf.read(info))
    files = list(walk(zipfile.ZipFile(io.BytesIO(data))))
    log(f"{len(files)} files")
    folders: dict[str, list[str]] = {}
    for name, size, _ in files:
        folder, _, leaf = name.rpartition("/")
        folders.setdefault(folder, []).append(leaf)
    for folder, leaves in sorted(folders.items()):
        layers = sorted({leaf.rsplit(".", 1)[0] for leaf in leaves if leaf})
        log(f"  {folder}: {len(leaves)} files, layers {layers[:3]} … {layers[-3:]}")
    read = {name: get_ for name, _, get_ in files}
    shown = 0
    for name, _, get_ in files:
        if not name.lower().endswith(".dbf") or not re.search(pattern, name, re.I) or shown >= 12:
            continue
        shown += 1
        base = name[:-4]
        prj = next((read[n]() for n in read if n.lower() == (base + ".prj").lower()), b"")
        rdr = shapefile.Reader(dbf=io.BytesIO(get_()))
        fields = [f[0] for f in rdr.fields[1:]]
        log(f"layer {name}: {len(rdr)} records, fields {fields}")
        log(f"  prj: {prj[:300]!r}")
        for rec in rdr.records()[:400]:
            log("  | " + " | ".join(str(v) for v in rec))


def _key(name: str) -> str:
    """A municipality's name for comparing across spellings and scripts."""
    import unicodedata

    from izbori.translit import latin
    s = unicodedata.normalize("NFD", latin(name).upper().replace("Đ", "DJ"))
    return "".join(ch for ch in s if ch.isalnum() and not unicodedata.combining(ch))


_CYR = {"lj": "љ", "nj": "њ", "dž": "џ", "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "đ": "ђ", "e": "е",
        "ž": "ж", "z": "з", "i": "и", "j": "ј", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "r": "р",
        "s": "с", "t": "т", "ć": "ћ", "u": "у", "f": "ф", "h": "х", "c": "ц", "č": "ч", "š": "ш"}


def cyrillic(name: str) -> str:
    """Serbian Latin to Cyrillic, for the names of Kosovo's municipalities RIK has no station in: the site writes
    Serbian in Cyrillic and transliterates it for the Latin pages."""
    out, i = [], 0
    while i < len(name):
        two = name[i:i + 2]
        if two.lower() in _CYR:
            c = _CYR[two.lower()]
            out.append(c.upper() if two[0].isupper() else c)
            i += 2
            continue
        c = _CYR.get(name[i].lower())
        out.append((c.upper() if name[i].isupper() else c) if c else name[i])
        i += 1
    return "".join(out)


# RIK's name → the dataset's, where they differ beyond the dataset's two names ("Gjilan/Gnjilane"). Serbia's Gora,
# merged with Opolje in 1992, is the municipality seated in Dragaš; Kosovska Kamenica is plain Kamenica there.
KIM_ALIASES: dict[str, str] = {"Гора": "Dragaš", "Косовска Каменица": "Kamenica"}


def kim_features(data: bytes, wanted: dict[str, str], years=("1999", "1998"), log=print) -> list[dict]:
    """Boundaries for the wanted municipalities ({code: RIK's name}) from the dataset's layers of Kosovo or Serbia
    for the last years before 1 July 2000, when Kosovo's municipalities were redrawn: RIK's division. Matched by
    name; each kept with its RIK code, simplified as the OpenStreetMap ones are."""
    import io
    import zipfile

    import shapefile  # pyshp, only for this command
    from shapely import set_precision
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    zf = zipfile.ZipFile(io.BytesIO(data))
    want = {_key(KIM_ALIASES.get(name, name)): code for code, name in wanted.items()}
    best: tuple = (-1, False, "", {}, {})  # matches, Kosovo's own layer, layer, {code: shapes}, {name: shape}
    for year in years:
        for n in zf.namelist():
            m = re.match(r"(.*/(?:KOS|XK|SRB|SCG|YUG)[^/]*)/" + year + r"\.dbf$", n, re.I)
            if not m:
                continue
            base = n[:-4]
            cpg = next((zf.read(x).decode().strip() for x in zf.namelist() if x.lower() == (base + ".cpg").lower()),
                       "utf-8")
            rdr = shapefile.Reader(shp=io.BytesIO(zf.read(base + ".shp")), shx=io.BytesIO(zf.read(base + ".shx")),
                                   dbf=io.BytesIO(zf.read(n)), encoding=cpg or "utf-8")
            fields = [f[0] for f in rdr.fields[1:]]
            name_field = next((f for f in fields if f.upper().startswith("MUNIC")), fields[-1])
            found: dict[str, list] = {}
            for sr in rdr.iterShapeRecords():
                name = str(sr.record[name_field])  # Kosovo's in both languages: "Gjilan/Gnjilane"
                code = next((want[k] for k in [_key(name)] + [_key(p) for p in name.split("/")] if k in want), None)
                if code:
                    found.setdefault(code, []).append(shape(sr.shape.__geo_interface__))
            log(f"{base}: {len(rdr)} municipalities, {len(found)} of the {len(want)} wanted")
            kosovo = bool(re.search(r"/(?:KOS|XKX?)[^/]*$", base.rsplit("/", 1)[0], re.I))
            others = {} if not kosovo else {str(sr.record[name_field]): shape(sr.shape.__geo_interface__)
                                             for sr in rdr.iterShapeRecords()
                                             if not any(k in want for k in [_key(str(sr.record[name_field]))]
                                                        + [_key(p) for p in str(sr.record[name_field]).split("/")])}
            if (len(found), kosovo) > best[:2]:  # on a tie, Kosovo's own layer, which also has the rest of it
                best = (len(found), kosovo, base, found, others)
    count, _, base, found, others = best
    if count <= 0:
        return []
    rdr_names = []
    missing = sorted(name for code, name in wanted.items() if code not in found)
    if missing:
        log(f"not in {base}: {missing}")
        zfn = base + ".dbf"
        rdr = shapefile.Reader(dbf=io.BytesIO(zf.read(zfn)))
        rdr_names = sorted(str(r[-1]) for r in rdr.records())
        log(f"the layer's names: {rdr_names}")
    feats = []
    for code in sorted(found):
        area = unary_union(found[code])
        area = set_precision(area.simplify(TOLERANCE, preserve_topology=True), 10 ** -DIGITS)
        if area.is_empty:
            continue
        g = mapping(area)
        feats.append({"type": "Feature", "properties": {"code": code, "name": wanted[code], "level": "",
                                                         "source": "ELWar"},
                      "geometry": {"type": g["type"], "coordinates": _round(g["coordinates"])}})
    # the province's other municipalities in RIK's division, where no election in the archive had a station: drawn,
    # so the province has no holes, but with no code and nothing to colour
    for name, area in sorted(others.items()):
        area = set_precision(area.simplify(TOLERANCE, preserve_topology=True), 10 ** -DIGITS)
        if area.is_empty:
            continue
        g = mapping(area)
        serbian = name.split("/")[-1].strip()  # "Gjakova/Đakovica": the second name is the Serbian one
        feats.append({"type": "Feature", "properties": {"code": "", "name": cyrillic(serbian), "level": "",
                                                         "source": "ELWar", "none": 1},
                      "geometry": {"type": g["type"], "coordinates": _round(g["coordinates"])}})
    log(f"{len(feats)} boundaries in RIK's division from {base}"
        + (f", {len(others)} of them with no station" if others else ""))
    return feats


# What OpenStreetMap has inside one census settlement below the settlement: local communities (mesne zajednice,
# admin_level 10) and named quarters (place=suburb/quarter/neighbourhood), to see whether a city settlement such
# as Novi Sad can be split into its quarters (9 Nov 2026). Only names, kinds and counts are logged.
QUARTERS_QUERY = """[out:json][timeout:600];
rel["boundary"="administrative"]["admin_level"="9"]["name"="{name}"]->.s;
.s map_to_area->.a;
(
  rel(area.a)["boundary"="administrative"]["admin_level"~"^1[01]$"];
  nwr(area.a)["place"~"^(suburb|quarter|neighbourhood|city_block)$"];
  rel(area.a)["boundary"]["boundary"!="administrative"];
);
out tags center;"""


def quarters_inspect(name: str, log=print) -> None:
    data = fetch(QUARTERS_QUERY.replace("{name}", name), timeout=700)
    from collections import Counter
    kinds = Counter()
    for e in data.get("elements", []):
        t = e.get("tags", {})
        kind = (f"admin_level={t['admin_level']}" if t.get("boundary") == "administrative"
                else f"place={t['place']}" if t.get("place") else f"boundary={t.get('boundary')}")
        kinds[(kind, e["type"])] += 1
        log(f"{kind:24} {e['type']:9} {t.get('name', '')} | {t.get('name:sr-Latn', '')}")
    for (k, typ), n in sorted(kinds.items()):
        log(f"= {k} {typ}: {n}")


# --- a city settlement by its quarters ------------------------------------------------------------------------------
# A census settlement such as Novi Sad holds most of its municipality's stations in one shape. OpenStreetMap draws
# the city's quarters (place=quarter: Telep, Liman 1–4, Detelinara, Grbavica, Bistrica …) inside it; `izbori geo
# --quarters 89010=Нови Сад` keeps those shapes (clipped to the settlement, the overlaps given to the first drawn:
# quarters, then suburbs and neighbourhoods where no quarter is) and, to place the polling stations, the names of
# the public buildings inside the settlement (schools, kindergartens, community centres, local communities' halls),
# each with the quarter its point falls in. No coordinates of buildings are kept, only name → quarter.

QUARTER_FETCH = """[out:json][timeout:900];
rel["boundary"="administrative"]["admin_level"="9"]["name"="{name}"]->.s;
.s out geom;
.s map_to_area->.a;
(
  rel(area.a)["place"~"^(suburb|quarter|neighbourhood)$"];
  way(area.a)["place"~"^(suburb|quarter|neighbourhood)$"];
  rel(area.a)["boundary"="administrative"]["admin_level"="10"];
);
out geom;
(
  nwr(area.a)["name"]["amenity"~"^(school|kindergarten|community_centre|college|university|library|arts_centre|social_facility|townhall|clinic|hospital|doctors|theatre|cinema|fire_station|police)$"];
  nwr(area.a)["name"]["building"~"^(school|kindergarten|civic|public|college|university)$"];
  nwr(area.a)["name"]["office"="government"];
  nwr(area.a)["name"]["club"];
  nwr(area.a)["name"]["leisure"~"^(sports_centre|sports_hall)$"];
);
out center tags;"""
QUARTER_KINDS = ("quarter", "suburb", "neighbourhood")  # the order the shapes are taken in
QUARTERS_FILE = "quarters.json"


def quarter_features(data: dict, name: str, log=print) -> tuple[list[dict], list[list[str]]]:
    """The quarters of one settlement (features: name, geometry) and the public buildings' names with their
    quarter ([name, quarter])."""
    from shapely import set_precision
    from shapely.geometry import Point, Polygon, mapping
    from shapely.ops import unary_union

    els = data.get("elements", [])
    city = next((geometry(e) for e in els if e["type"] == "relation"
                 and e.get("tags", {}).get("admin_level") == "9" and e.get("tags", {}).get("name") == name), None)
    if city is None:
        log(f"{name}: no settlement boundary")
        return [], []
    shapes = []
    for e in els:
        t = e.get("tags", {})
        if t.get("place") not in QUARTER_KINDS or not t.get("name"):
            continue
        if e["type"] == "relation":
            g = geometry(e)
        elif e["type"] == "way" and len(e.get("geometry") or []) >= 4:
            pts = [(p["lon"], p["lat"]) for p in e["geometry"]]
            g = Polygon(pts) if pts[0] == pts[-1] else None
        else:
            g = None
        if g is None or g.is_empty:
            continue
        g = g.buffer(0).intersection(city)
        if g.area > 0:
            shapes.append((QUARTER_KINDS.index(t["place"]), t["name"], g))
    shapes.sort(key=lambda s: (s[0], s[2].area))  # the smaller first: Sajlovo before the industrial zone around it
    taken, quarters = None, []
    for kind, qname, g in shapes:
        own = g if taken is None else g.difference(taken)
        if own.area < 0.5 * g.area:  # mostly inside a quarter already drawn (Liman around Liman 1–4)
            continue
        quarters.append((qname, own))
        taken = own if taken is None else unary_union([taken, own])
    rest = city.difference(taken) if taken is not None else city
    log(f"{name}: {len(quarters)} quarters, {100 * (1 - rest.area / city.area):.0f}% of the settlement covered")

    def quarter_of(pt) -> str | None:
        hits = [q for q, g in quarters if g.covers(pt)]
        return hits[0] if hits else None

    points: dict[str, str] = {}
    for e in els:
        t = e.get("tags", {})
        if e["type"] == "relation" and t.get("admin_level") == "10" and t.get("name"):  # a local community
            g = geometry(e)
            q = quarter_of(g.representative_point()) if g is not None else None
            if q:
                points.setdefault("месна заједница " + t["name"], q)
            continue
        c = e.get("center") or ({"lon": e["lon"], "lat": e["lat"]} if "lon" in e else None)
        if not c or not t.get("name") or t.get("place"):
            continue
        q = quarter_of(Point(c["lon"], c["lat"]))
        if q:
            points.setdefault(t["name"], q)
    feats = []
    for qname, g in quarters:
        g = set_precision(g.simplify(SETTLEMENT_TOLERANCE / 2, preserve_topology=True), 10 ** -(DIGITS + 1))
        if g.is_empty:
            continue
        shp = mapping(g)
        feats.append({"type": "Feature", "properties": {"name": qname},
                      "geometry": {"type": shp["type"], "coordinates": _round(shp["coordinates"])}})
    log(f"{name}: {len(points)} named buildings placed in a quarter")
    return feats, sorted([k, v] for k, v in points.items())


def write_quarters(path: Path, code: str, settlement: str, feats: list[dict], points: list, fetched: str) -> None:
    """data/geo/quarters.json: per municipality code, the settlement split into quarters and the buildings' names."""
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.update({"attribution": ATTRIBUTION, "license": LICENSE,
                 "source": f"OpenStreetMap through the Overpass API, {fetched}; place=quarter/suburb/neighbourhood"})
    data.setdefault("areas", {})[code] = {"settlement": settlement, "features": feats, "points": points}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
