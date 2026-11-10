# AGENTS.md

How to work on this repository, what must not change, and the architecture decisions with their reasons. It is
written for coding agents and for people. **Keep it current:** when a decision is made or changed, update this file
in the same commit. README.md describes the project for its users; this file is for those who change it.

## How to work here

- **Commit straight to `main`.** No feature branches or pull requests (the maintainer's decision, 2 Nov 2026).
- **Run the whole test suite before every push:** `uv run pytest -q` (about 3 minutes). The **test** workflow runs
  it again on every push; a red run is fixed before anything else.
- **Explain why in commit messages.** Say what changed for the site or the data, and the reason.
- **Update README.md with every feature:** the section that describes it, the archive layout, the commands, the
  module layout and the schedule, as they apply.
- **Ask RIK little.** A one-off full pass through a register is fine when a feature needs it. Recurring reads must
  be incremental, or gated by the election calendar (see *Fetching from RIK*).
- **The development sandbox may not reach RIK; GitHub's runners can.** Run anything that needs RIK through
  `workflow_dispatch`. To tune OCR on real documents, use the masked diagnostics: `izbori observers --station
  CODE/NUMBER --diagnose N --layout` and `izbori boards --diagnose N` print the layout with every word that isn't
  printed on the form masked.
- **Only one pending run per workflow.** Each workflow has a concurrency group; a second dispatch while one is
  pending cancels the pending one. Queue at most one run of a workflow at a time.
- **Talk to the maintainer in Serbian** (Latin script), briefly and to the point. Code, comments and docs are in
  English.

## Principles

These are the project's promises to its readers. Never change them without the maintainer.

1. **The same rules for every contestant.** No party is hardcoded. A test swaps contestants' votes and checks that
   the flags don't change.
2. **A flag is a question, not a verdict.** The site says "unusual, check the minutes", never "fraud".
3. **Flags come from primary sources only:** laws, RIK's documents, ODIHR reports. A news report is a note, marked
   unconfirmed; it never makes a flag or changes a ranking. An OCR score is never a flag either.
4. **No personally identifying data; link to RIK instead** (the maintainer's decision, 3 Nov 2026).
   - The archive, the site, logs and CI output never record a person's name or other identifying detail, even
     though RIK publishes them in its documents (board members, observers, commission members). Linking to RIK's
     own document is always fine: whoever needs the names reads them there.
   - Never store, log, print or transcribe a name from a document.
   - Don't copy titles that commissions write: they may name a person. Keep RIK's own kind of document instead.
   - Diagnostics in public CI logs mask every word that isn't printed on the form.
   - Summaries of observers' remarks never name anyone.
   - Anything parsed from a document that could hold a name is checked before it is kept. For example,
     `boards.clean_address` drops a member's line read where an address should be, and stores are scrubbed when
     they are read and written.
5. **Nothing from third parties on the pages:** no analytics scripts, cookies, external fonts or scripts. Visitor
   counts, if any, come from the host or the edge (for example Cloudflare's proxy analytics), not from a script on
   the page.
6. **The observer target list stays private.** It is never committed or built in GitHub Actions, because anyone
   with a GitHub account can download a public repository's build outputs.

## Architecture decisions

### Archive and data

- **Git is the archive.** `data/rounds/<id>/` holds RIK's files as downloaded and the derived stores; the history is
  a timestamped record of what RIK published. A file is committed only when its content changed.
- **The derived stores are written one entry per line** (`jsonfile.py`), so git keeps a small diff.
- **Each derived store keeps only what a page needs.** None of them holds a name:
  - `boards.json`: per decision, the station, kind, link, address, and whether each list appointed a member.
  - `documents.json`: label, link and upload time of every station document in RIK's register of minutes.
  - `commission.json`: link, RIK's kind and the day, for the municipal commissions' documents; for a document RIK
    lists under a city the results don't have (Niš, Belgrade), RIK's name of that city.
  - `observers.json`: the OCR numbers only.
  - `observer_reviews.csv`: what a person found in an observers' record.
  - `settlements.json`: per station, its census municipality and settlement and the rule that found them (each
    election's Settlements page and Explore's census measures use it).
- **Stations are keyed `municipality code/number` per round.** Municipality codes are stable across elections,
  but names differ ("Ниш-Медијана" in 2022, "Градска општина Медијана" in RIK's registers). Names map to codes
  with `boards.municipality_key`, using every archived round.
- **The 2022 census** (`data/census/2022/`) is kept as the Statistical Office (RZS) published it, by settlement
  and by municipality, with `sources.json` (address, SHA-256, size, first fetched); a table is written only when
  its content changed. Which tables: `census.TABLES`. The census is final, so the **census** workflow runs by
  hand; the development sandbox can't reach the Office's site (its proxy refuses it), GitHub's runners can. The
  tables count people and hold no names. Education, ethnicity, activity and migration exist only by municipality.
- **Each station's settlement** (`settlements.py`): the first rule that answers decides, the same for every
  station: a correction in `data/settlements.csv`, a settlement named in the decision's address (after its first
  part: "address"; in it: "building"), in the station's name, the municipality's only settlement, the same place
  in another election ("place", by `places.py`), and last the seat, assumed only for an address with a street or a
  house number that names no settlement. No rule, no entry: unknown is not zero. The census prints names, not codes:
  its units come from the first column's indentation, and RIK's municipalities match them by name (brackets say
  which city; a city municipality RIK doesn't list in a round belongs to the city's own). The **boards** workflow
  joins again after reading decisions, since they give the addresses.
- **Places across elections** (`places.py`) are matched going forward in time, by priority: manual correction
  (`data/places.csv`), then address, then name, then number. A new election never changes how the earlier ones
  were joined. An address read from a decision that names another building than the station's own name in the
  results is not used, for matching or for display (3 Nov 2026). Such addresses come from decisions filed under the
  wrong station, or from a line that is only the town's name.

### Fetching from RIK

- **Endpoints:**
  - `/get-elections/`: the rounds.
  - `/get_results/`: progress and totals.
  - `/export-results/{round}/2`: the results file.
  - `/get-election`: the register of minutes, ten stations a page.
  - `/get-additional-documents`: decisions on polling boards (type 4) and the municipal commissions' documents
    (type 1).
- **The election calendar sets how often RIK is asked** (`schedule.py`). Election days come from the archive and
  from `data/elections.csv`, which a maintainer fills in when an election is called. The cadence:
  - with no election under way, once a day;
  - on election day, every 6 hours, then every hour from two hours before the polls close;
  - every hour for two days after;
  - every 3 hours until 14 days after.

  How the schedule is kept reliable:
  - `data/looks.json` records the last look, because GitHub drops many scheduled runs (3 of about 22 hourly runs
    on 3 Nov 2026).
  - While a count is open, the watch loop starts the next run itself.
  - Sunday evenings get extra cron runs.
- **Registers are read incrementally:**
  - The register of minutes is re-read only when a cheap count per document kind changed.
  - The register of additional documents is read newest first, stopping at the first page with nothing new.
  - A full pass happens only when a store lacks something, for example the decisions' links, or the cities' names
    in the commissions' store (`commission.needs_reading`).
- **Time windows after election day:**
  - The register of minutes: daily for 14 days, then on Mondays until 60 days.
  - Board decisions: until 14 days, since they are appointed before election day.
  - Observers' records: OCR until 60 days.
  - The commissions' documents: once for every archived round, then with the register of minutes.

### OCR

- **Engine:** Tesseract with `srp+srp_latn` on GitHub's runners. In the development sandbox the Serbian data can't
  be downloaded; use `rus` for local checks and confirm on a runner.
- **Decisions on polling boards** use the PDF's text layer when there is one, otherwise OCR. Each list's slot gives
  "member yes/no", and the address is cleaned before it is kept.
  - The workflow reads in four jobs at once (about 1,600 decisions an hour each): `--plan` lists what to read,
    `--read --shard I/4` reads one share, `--merge` keeps everything and commits once. The plan and the parts are
    workflow artifacts, so they hold no names either.
  - A reading's version (`boards.PARSER`) is kept with every decision read (`v`). Raise it when `parse_decision`
    reads more than before: `plan()` then lists every decision read by an older version (by its kept link, since
    the register is paged only for new decisions once read whole), and the daily run reads them again, about
    1,600 an hour per job. Don't reread by hand per municipality for a parser fix; raise the version.
  - Layouts: the numbered parser ("1. члан:", "1) члан:") goes first, so nothing that read before changes; the
    unnumbered one (`_unnumbered`) takes over only where it finds no slot. A new layout comes from the masked
    layouts the read jobs log (`--diagnose`, or `--diagnose-ids` for decisions already read), never from a
    decision's text with names.
  - Tables with a row per member and per deputy, each with its own proposal (Ub, 2026): a page OCR read column by
    column (`read_columns`) is read again line by line (psm 6), and each numbered slot's list is the one its text
    names most (`named_most`), its own number first. Only decisions in that layout take this path.
  - Kinds: RIK's label, which the commission picks when it uploads, decides; only at a station with no standing
    decision and two extended ones does the title naming the standing composition, or the president, make one of
    them standing (`standing_under_extended`). A title alone never overrules a label: on 6 Nov 2026 a title-first
    rule turned 29 of Ada's extended decisions into standing ones (both of a station's titles name the standing
    composition) and was taken back the same night. A re-index gives decisions already read the current kind.
  - Placement (`Placer`): by municipality and number, and where the register's station name disagrees with the
    results, by that name among the city municipalities of the same district, or among municipalities whose name
    in any election, or district, contains the register's; "РИК" (RIK's own boards) among the stations abroad and
    in prisons. Nothing placed under its own name moves (checked on every archived election).
- **Observers' records (RG-11)** are read by a person. OCR only orders the review list:
  - The score is the ink and words between "… су следеће:" and "(примедбе уписује …)". Each column of a landscape
    page is read on its own, and printed rules are left out by the length of their dark runs.
  - A person writes what they found in `observer_reviews.csv`, through `izbori observers --review` and `--merge`.
    Only a confirmed "yes" becomes a flag.

### Site

- **Static pages in two scripts:** Latin (the default) and Cyrillic (`i18n.BUILT`). Every string also exists in
  English (`i18n.LOCALES`), but the English pages are not built since 8 Nov 2026: they were 291 MB of a 962 MB site
  against GitHub Pages' 1 GB. Putting "en" back into `BUILT` brings them back.
  - Serbian text is written once in Cyrillic; the Latin pages are the whole page transliterated.
  - Links to RIK are percent-encoded, so transliteration can't break them.
  - There is no JavaScript framework. Charts are SVG drawn when the site is built, except on the Explore page:
    its own script (`static/explore.js`, no library) draws in the browser from `api/r/<id>/stations.json` and
    `api/geo/municipalities.json`, with the strings and lists the page carries in its language. The stations'
    names in `api/` are as RIK wrote them, so the script transliterates them as `translit.py` does.
  - **Explore never chooses a list.** A measure that needs one waits for the reader, and picking another election
    clears the choice (ballot numbers belong to one election). Measures and filters are the same for every list.
    Its ready-made analyses are questions grouped by theme (`THEMES` in the script), its measures sit in groups
    (`MGROUPS`), and every measure, view, theme and question has its words in `i18n.py` (`m_desc_*`,
    `view_desc_*`, `preset_theme_*`, `preset_q_*`); a test reads the script and checks that none is missing.
    Unknown is not zero: a station whose board decision wasn't read has no controller value, and an election
    whose observers' records weren't read has none for them.
- **Results by kind of settlement** (`bysettlement.py`, `r/<id>/settlements.html`): every contestant's share and
  controllers by the class of its stations' settlements (type, population, change since 2011), in the order of
  their votes, nothing ranked or flagged. The census's figures are read from the archived tables when the site is
  built (`settlements.load_figures`), so the tables and each round's `settlements.json` are inputs of the round's
  pages. Explore's filters use the same classes (`bysettlement.CLASSES`); for a municipality a census measure counts
  each of its settlements with stations once, and census measures aren't compared between elections. Controllers
  are shown for a class only where at least half of its stations' decisions (and at least 10) were read: Belgrade's
  2024 decisions were mostly never published.
- **Incremental build:** each page's inputs are fingerprinted in `_site.state.json`.
  - **Every input of a page must be in its fingerprint.** On 3 Nov 2026 the place pages missed their board
    decisions, so the 2026 pages kept the old version.
  - The incremental test compares with a full build. When you add an input, extend that test.
- **The languages are built side by side** in forked processes (`Site.side_by_side`). Windows, or
  `IZBORI_SERIAL=1`, builds them one after another. The result is the same file for file.
- **The guide for controllers and observers** (`guide.sr.html`, `guide.en.html`) gives the article or RIK document
  for every rule, and says which month it was checked against. When the law or RIK's instructions change, update
  both languages and that line. Rules come from the law and RIK only; a party's handbook may suggest what to cover,
  never what the rule is, and its partisan advice stays out.
- **Size budget:** GitHub Pages allows 1 GB, and the site is about 660 MB with about 40,000 files (Nov 2026).
  - Keep repeated markup out of per-row HTML: cell labels live in the generated `static/labels.css`, links carry no
    per-link `rel`, and a `title` appears only where it adds something.
  - The municipality's lists keep to the documents of the vote. Decisions on polling boards are listed only on the
    place's page.
- **Hosting:** GitHub Pages through Actions at **izbornipodaci.rs** (since 8 Nov 2026); the previous build is kept
  in the Actions cache. The domain is registered at Loopia; its DNS has the four GitHub Pages A records for the
  apex and `www` as a CNAME to izborni-podaci.github.io. The custom domain is set in the repository's Pages
  settings (an Actions deployment needs no CNAME file). `SITE_URL` in config.py is the only place the address
  lives in code: feeds, the 404 page, the mail and the map image's source line all take it from there.
  - Possible later: Cloudflare in front for visitor counts at the edge.
  - Cloudflare Pages' free plan doesn't fit, with its limit of 20,000 files. Workers' paid plan (100,000 files) or
    a VPS are the fallback if the site outgrows 1 GB.

### Workflows

| Workflow | When | What |
|---|---|---|
| update | hourly, plus Sunday evenings; asks RIK by the calendar | results, flags, feeds, email |
| documents | daily | register of minutes, commission documents |
| boards | daily, until 14 days after election day | decisions on polling boards: plan, four OCR jobs, merge (one commit); then the stations' census settlements |
| observers | daily, until 60 days after election day | OCR score of observers' records |
| pages | on push | incremental site build and deploy |
| geo | by hand | municipal boundaries from OpenStreetMap (Overpass); with kim, Kosovo and Metohija in RIK's division |
| census | by hand | the 2022 census tables from the Statistical Office (RZS), into `data/census/2022/` |
| test | on push | the whole test suite |

A run started with `GITHUB_TOKEN` can dispatch another workflow (`gh workflow run`). That is how data runs start
**pages**, and how a watch run starts the next **update** run.

### Tests

- The tests use the real archive in `data/`, plus small made-up files. The full site is built once per module and
  shared; a test that needs changed data builds from a copy of only the rounds it needs.
- When new real data breaks a test on the real archive, find the cause in the code first. The test broken by the
  2023 addresses led to the rule on addresses that contradict the results. Change the expectation only when the new
  data is right and the old expectation was wrong.

## Known issues and open decisions

- **Belgrade 2024 decisions on polling boards (round 567956):** RIK's register holds only 129 decisions for its
  1,265 stations, listed under "Београд"; the station's name places them by district since 5 Nov 2026, and its 17
  decisions on the extended composition now read. The rest were never published there.
- **Despotovac and Ub 2023 (round 341140):** their decisions on the extended composition (44 and 51) are tables,
  people in one column and lists in the other, which OCR interleaves line by line. Ub's rows give the list's
  ballot number ("члан 6"), but no rule tells an empty name cell from a filled one, and Despotovac's don't even say
  which list a member belongs to: they stay unread rather than guessed (masked layouts in boards run 42106667607).

## Decisions log

- **2 Nov 2026:** work goes straight to `main`; the place pages follow each station across elections, matched by
  address, then name, then number.
- **3 Nov 2026:**
  - Observers' records are reviewed by a person; OCR only orders the list.
  - RIK's registers are read incrementally, and results by the election calendar.
  - Decisions on polling boards are linked on the place's page.
  - The commissions' documents are listed on the municipality page without their titles.
  - Member lines are never kept as addresses, and an address that contradicts the results is not used.
  - Personally identifying data is never recorded; links to RIK's documents are. The 401 member lines that
    leaked into `boards.json` as addresses before this date stay in git history: the names are public at RIK,
    the fragments are shown nowhere, and rewriting history would break every clone. It is not rewritten.
  - Repeated markup was cut from 713 MB to 657 MB, and the languages are built in parallel.
  - Decisions on polling boards are read in four jobs at once, and the stores are written one entry per line.
  - "In short" on the pages across elections is short labelled rows (flags, turnout, most votes, the place,
    records), the main fact first and context below, figures for the latest election unless a line names
    another, instead of paragraphs of sentences. The maintainer chose this layout.
  - The custom domain waits until it is clear how useful the site is.
- **5 Nov 2026:** the observer guide became the guide for controllers and observers, at the maintainer's request:
  written from the law (14/2022 and the 2026 amendments) and RIK's 2026 handbook for polling boards and instruction
  on handovers, with the topics of a controllers' handbook he shared. That handbook's partisan advice is left out,
  and the old guide's objection rule is corrected: a request to annul a station's vote goes to the local commission
  within 72 hours of closing (Art. 148). The same day it gained a section on local elections, from the Law on Local
  Elections (14/2022, 35/2024, 47/2026): that law leaves the procedure at the station to the parliamentary law
  (its Art. 8), so the section lists only what differs, each with its article.
- **5 Nov 2026, home page:** the maintainer chose to add the latest election's state beside the search, the
  archive in numbers, the next election from `data/elections.csv`, and three cards (controllers by list,
  municipalities, data and alerts); he passed on a feed of the latest events and on a card for changes after
  publication. The next election's deadlines are counted back from voting day (N days: that date; 24 and 48
  hours: two days before) and the strip says the commission's calendar is the authority. The municipalities
  page is new, sorted in Serbian alphabetical order per script. On phones the nav says only "Guide".
  - Later that day he removed the latest election's state: the space beside the search shows the next election
    only when one is entered, and stays empty otherwise. The phones' short "Guide" comes from a `data-short`
    attribute through CSS, so the link's text is the whole name everywhere else (copying, reader views, a stale
    stylesheet): two spans in one link showed both names when the CSS didn't apply.
- **5 Nov 2026, Explore page:** the maintainer asked for a tab where visitors run their own analyses and chose,
  for the first version: the election fingerprint (turnout against the largest share of any list), two elections
  compared, municipalities across elections as a heat table, filters with a CSV download, and a map of
  municipalities; ready-made analyses as well as free choice; controllers and observers' records as criteria for
  every list alike; OpenStreetMap's boundaries; Kosovo and Metohija by RIK's municipalities (pending RGZ's data).
  An earlier session had started a "Compare" page (the `geo` command and its data); the work continued as this
  page, and that session's unfinished strings and nav link were replaced.
- **5 Nov 2026, later:** Kosovo and Metohija are on the map in RIK's division, from Glaurdić et al. (2021, CC BY
  4.0), the 1999 layer, joined by name (either of the dataset's two names; Gora is the municipality seated in
  Dragaš). RGZ's register would have needed an account, and OpenStreetMap follows Kosovo's division since 2000.
  The map's classes hold equal numbers of municipalities, as the province's turnout squeezed equal steps.
  The maintainer asked why so many board decisions were missing (750 of 8,392 stations in 2026): unreadable
  layouts (371), decisions listed under a city or a name the results don't use (319: Niš, abroad, prisons), 17
  of Kostolac and Sevojno added to Požarevac and Užice by number (a bug), and 43 never published. The parser
  learnt three layouts and decisions are placed by the station's name; `--reindex` applies it to what was read.
  After the re-index, 8,345 of 2026's 8,392 stations have their controllers known (7,642 before); of the 47 left,
  43 have no decision in RIK's register (37 in Kosovo and Metohija) and 4 are unreadable. The 2023 elections were
  re-indexed and re-read too: parliamentary 8,120 of 8,273 (7,269 before), provincial 1,771 of 1,776 (1,621).
- **5 Nov 2026, new checks and the commissions:** of the projects proposed for the data already archived, the
  maintainer chose new checks in the numbers and a page on the municipal commissions.
  - **Same votes as another station** (`identical_results`, unusual, weight 2) is a station flag: every contestant
    with the same votes at two stations of one municipality, with at least 50 votes and 3 contestants with votes.
    Two contestants match by chance too often (a two-way race); no archived election has a pair even at 10 votes.
  - **Round percentages and last digits stay statistics, never station flags:** a test over many stations can't say
    which one is unusual. Round percentages are now compared with the count expected from each station's
    denominator, exactly; the old note's "about 10% by chance" was wrong for small ones (of 500 votes, 20%). Per
    municipality both are tested and corrected for the number of municipalities (Bonferroni); none of the
    archived elections has one below 0.05.
  - **The commissions page has no score,** in keeping with "a flag is a question": each column is a fact, and cells
    are highlighted by absolute rules (something missing, a median over 12 hours, minutes after a day, changes), not
    by rank, so no municipality is marked only for being slower than others. A commission with no document isn't
    marked: RIK lists a city commission's documents under the city (Niš's, for its five city municipalities; the
    Belgrade city election of 2024), which the results don't have. At the maintainer's request they are shown with
    the city's municipalities ("+ city's"), apart from their own: the store keeps RIK's name of such a city, after
    one full pass of the register per election, and `commission.city_parts` joins a city to its city
    municipalities by every election's names ("Ниш-Медијана") and districts ("Град Београд"), or, where the city
    has a code, to the city municipality of its district (Kostolac to Požarevac, Sevojno to Užice). Vranjska Banja
    (2023 only, with no district in that file) stays alone. Hours come from the
    upload stamp in each document's link: the register of minutes shows the same time for almost every document,
    but days later for some (Bačka Palanka 2023: register 20 Dec, files 18 Dec). Abroad and prisons are left out
    (RIK runs them). Explore gained the same hours as a measure, a median per municipality.
- **6 Nov 2026, Ub's decisions:** the maintainer found Ub's station 2 (2026) showing controllers of lists 1, 7 and
  15, while the decision names the student list, and its standing composition counted as the extended one. Both
  came from the register and the scans: the commission uploaded its standing compositions under the extended
  composition's label (now recognised station by station, by the title naming the president), and its extended
  compositions are scanned tables that OCR read half by columns (now read line by line, row by row). The decisions
  of Ub and eight municipalities with similar readings (Vranje, Zrenjanin, Bajina Bašta, Petrovac na Mlavi,
  Kragujevac, Senta, Srbobran, Blace) were read again: 179 stations' controllers changed, Ub's station 2 to the
  eleven lists its decision names and Vranje's 83 stations to fuller lists. The masked layouts are in boards runs
  42125804884 and 42127173840.
- **6 Nov 2026, a list's votes on Explore:** the maintainer asked to see how many people voted for a list, not
  only its share, and to compare a list's fall between two elections. A list's votes are a measure like its share
  (a count, added up per municipality); the table shows each beside the other. In two elections a count changes by
  a number and in per cent (a share in percentage points, as before), the largest changes rank by either, and the
  summary gives both elections' totals over every chosen station, matched or not, so a list's national result
  reads directly. The ready-made "a list's votes in two elections" still waits for the reader to choose the lists.
- **6 Nov 2026, census tables:** for a study of controllers by list (outside the site, every list measured alike),
  the maintainer chose to archive the 2022 census, so that polling stations can be joined to their settlements and
  compared with like places. The Office publishes seven tables by settlement (population, age and sex, households,
  families, every census from 1948, dwellings); education, ethnicity, economic activity and migration only by
  municipality, education also by type of settlement. `izbori census` keeps those seven and eight by
  municipality, as published; joining stations to settlements comes next.
- **6 Nov 2026, stations' settlements:** the maintainer chose to keep the join in the repo: a store per round that
  records the rule behind each station's settlement, and corrections by hand in `data/settlements.csv`, as
  `data/places.csv` does for places. The seat is assumed only where a decision gives a street address naming no
  place: falling back to it for every station put all 91 of Prokuplje's stations, from 107 settlements, in the
  town. The same place in another election comes before the seat, and fills the 2022 round, whose results name
  no station. In 2026, 7,556 of the 8,210 stations where the census was held have a settlement (6,520 named or
  certain, 607 from another election, 429 assumed seats); 654 have none, mostly where decisions give no address
  (Prokuplje, Knjaževac, Negotin, Bajina Bašta). openpyxl joins the dependencies, to read the census.
- **6 Nov 2026, the municipality page:** the maintainer chose its order: the result in per cent first (with who
  voted: registered, voted, turnout, invalid ballots, which replace the tiles), then the polling stations (the
  first ten and a full-width button for the rest), then the votes of the three lists with most votes at each
  station as numbers instead of shares (same columns, shaded by share, now with a total row), then every list at
  every station behind a full-width button, and everything else below (controllers by list, the commission's
  documents). The button and the CSV of the whole table are `static/site.js`, which only adds to a page: without
  it every station shows and the CSV button stays hidden. A link to a station further down opens the list, as the
  pages across elections link to `#bm-<number>`. The same day the analyses moved towards the site: the maintainer
  wants what is relevant there, joined with the census where it shows something, not in separate dashboards.
  Phones: `.table-wrap` is positioned, so a visually hidden header label inside a scrolling table no longer
  widens the page (municipality and round pages scrolled sideways at 390 px, by up to 124 px), the
  round page's statistics tables scroll inside their own box, and the vote list's national share has the width
  of the votes and the share.
- **6 Nov 2026, analyses on the site:** of four analyses offered for the site (controllers against votes by list,
  the settlement on the station's page, results and controllers by kind of settlement, the census on Explore), the
  maintainer chose the last two first. Each election has a Settlements page: shares and controllers by the
  settlement's type, population and change since 2011, with the urban-other difference within municipalities,
  which keeps a list strong in rural municipalities from looking strong in villages everywhere, and the other way
  round: in 2026 two lists' controllers covered about as many village stations as town stations in the country's
  totals, yet 10 to 12 points fewer of the village stations than of the town stations within the same
  municipality. Explore gained the census's measures (an
  urban settlement, its people, its change since 2011, its share aged 65 or more) and filters by the same classes.
  The research dashboard of the same day is not kept up: the site is where the analyses go.
- **6 Nov 2026, Explore reorganised:** the maintainer asked for Explore to be conceptually ordered, more relevant
  and easier to use. The twelve ready-made analyses in one row became twenty questions in six themes (turnout,
  lists, voter register, controllers, settlements, minutes and checks), the question titling its answer; the form
  reads election, measure, view; the sixteen measures sit in five groups with a sentence each, and each view has
  one; the filters are grouped, and those in use show as removable chips with one reset; the notes that matter
  for what is shown stand beside it. Nothing new is computed, and every list is still the reader's choice.
- **7–8 Nov 2026, the redesign and its readers:** the maintainer defined three readers and asked for the site to
  serve each: (1) a curious visitor or a controller, who comes through a link to the site, wants their station or
  municipality, how it compares and anything that stands out, with little text and nothing to decode; (2) a
  coordinator of 30–60 controllers (the maintainer counts himself here), who works by municipality or part of one
  and needs the weak spots of its stations, ranked by his order (warnings repeated across elections, near-unanimous
  votes with a high turnout, no controller of his list, a sudden rise in registered voters, a turnout far from the
  surroundings), comparisons with the municipality, similar settlements and the country, and the history of its
  stations; (3) a statistician or a curious reader who wants the long view: data to download and Explore. Of two
  concepts sketched on a design canvas (one page in layers; three entrances), he chose **three entrances**: the
  navigation reads *Moje mesto · Za kontrolore i koordinatore · Analize i podaci · Vodič*, the home page is the
  search, three doors and what stands out. His other decisions: a neutral title ("every polling station in Serbia,
  through every election since 2022"), no example of a station page and no "what you get in three lines" on the
  first door but a short story instead; no "what's new since your last visit" anywhere, since it would look like
  tracking (what the browser keeps is shown as shortcuts only, with a forget button); the strip with the latest
  election's figures dropped; **"upozorenje" replaces "oznaka"** as the word for a flag (clearer, a mildly negative
  connotation accepted) — the pages still say "oznaka" and change in a separate commit; the cards must be clear
  to someone who doesn't yet know what a warning is, so they say "brojke ukazuju na nešto neobično" and name the
  places; lists may be named; the cards are the four in `highlights.py`, in the style of the canvas's fourth
  variant (a big line, a sentence, the figures below), with a palette where a colour means a kind of content and
  never a list: ink, sand, amber, brick (only for unusual numbers), teal, and yellow on dark. Build order he set:
  home → the station's page → the municipality → analyses.
- **8 Nov 2026, the palette for the whole site.** Three schemes were drawn on the canvas over the same home page and
  a table: A ink and sand (what the home page had), B newsprint with one accent, C navy and gold. Marko chose **C**.
  The roles are fixed in the tokens so every page follows: navy for the brand and the data, gold for the one thing
  to look at, red only for warnings, teal for the lists; the header sits on navy with a gold rule; `--gold`,
  `--gold-ink`, `--brand`, `--on-brand` and `--warn-track` were added, and warnings no longer share the data colour
  (`td.warn`, `tr.flagged` use `--critical`). The first tab is *Početna*: a tab that brings you back should say so.
- **8 Nov 2026, replaced minutes are a document, not a warning.** Marko asked why a replaced minutes document
  counted as a warning: it lifted some municipalities' averages without saying anything about the numbers (Bački
  Petrovac stood at 11 of 11 flagged in 2026 only because its commission re-uploaded every set of minutes). The
  `minutes_replaced` check is retired; the earlier minutes stay on the station as a document (*Ранији записник*,
  "Earlier minutes"), so both versions can still be opened and compared, and old feed entries keep the entry but
  drop that line. Remarks on the minutes stay a flag (he accepts that one, with some doubt: it says a document
  exists, not what it says).
- **8 Nov 2026, "upozorenje" on every page.** The Serbian pages now say *upozorenje* for a flag everywhere (the
  strings, the about page, the guide); English keeps "flag". Neuter noun, so the adjectives and verbs around it
  changed with it ("isto upozorenje", "pojavilo").
- **8 Nov 2026, Izbori back in the header.** Marko asked for it: *Početna · Izbori · Za kontrolore i koordinatore ·
  Analize i podaci · Vodič*. Izbori is current on the elections page and every round page; the coordinators' tab
  on the municipalities' pages. Five tabs fit a 390 px phone with the short names; at 360 px the row scrolls.
- **8 Nov 2026, the station's page.** Second step of the build order. Drawn on the canvas ("Strana biračkog mesta")
  and approved as proposed: the latest election first and open, in a block with the result and bars, three tiles
  against the municipality, each flag as a sentence with what to check right under it (the "What to check" list at
  the bottom is gone), controllers with the lists that have none (a coordinator's weak spot), documents; then "In
  short" and the trends; then the earlier elections folded into the same block. The wide history table is gone
  from this page (it stays on the municipality's history page and in the JSON). Rules kept: every contestant alike
  (shown when at least 1% here, the first three always), names shortened by the same rule as in sentences.
- **8 Nov 2026, the coordinator's municipality page, and two checks.** Third step of the build order, drawn on the
  canvas ("Pregled opštine za koordinatora") and approved with the order as drawn, the sixth card kept, and similar
  municipalities by five size classes × town/not. A look at izbori26.rs (notes in the project doc
  `claude/izbori26-analiza.md`) fed two things: the per-list deviation chart against the municipality, and the
  register check. New checks, same for every list: `registered_jump` (register up 15% more than the municipality's
  median change at the same place, under 40%: above that the area was most likely redrawn) and `turnout_apart`
  (20 points from the median of the other stations in the same census settlement, at least two of them). Both
  weight 1, group "unusual". A municipality-wide fallback for `turnout_apart` was measured and dropped: towns differ
  from villages everywhere and it flagged 400 stations in 2026 against 55 for the settlement rule. "My list" lives
  only in the reader's browser (`viewed.lists`), consistent with the no-tracking principle; the page is rendered
  for the leading list so it reads without scripts. The near-unanimity card is the `near_unanimity` rule alone,
  since that rule already requires turnout of 90%.
- **8 Nov 2026, the size budget: English dropped from the build, indentation stripped.** The station page redesign
  took the places' pages from 441 to 674 MB and the site to 962 MB (Cyrillic 332, English 291, Latin 286, API 52).
  Measured options: without English and Cyrillic the site is ~340 MB; stripping the templates' indentation saves
  5.5%. Marko chose: drop English for now, keep Cyrillic, strip the indentation. `i18n.BUILT` lists what is built;
  the English strings, templates and tests of the strings stay. `site.compact` removes indentation only (a line
  break stays a line break), never the space between tags on one line, so inline elements don't run together.
  Expected: ~650 MB.
- **8 Nov 2026, how every settlement voted.** A Reddit post that drew a crowd was a map of one region's villages
  with a list "which list is first in which villages", made by hand from izbori26.rs's data; people answered about
  their own village. The municipality's page now gives that material to anyone: a sentence naming the settlements
  each list is first in, and a table per census settlement. Next: settlement boundaries (OSM `ref:RS:naselje`) for a
  map per municipality, then an image to download and an `og:image`, so a link carries the map.
  Done the same day: `izbori geo --settlements` (4,720 boundaries, 7 without a census match), the map on the page
  (`maps.py`; colour = the list's rank in the whole election, lighter under 5 points, grey without a result), names
  where they fit, and "Download the image (PNG)" drawn on a canvas in the browser. `og:image` still needs a raster
  made at build time; not done. Known gap seen on Novi Sad: Kovilj's stations are not placed in Kovilj
  (settlements.py), so it draws grey.
- **8 Nov 2026, lists' colours on the maps.** Marko asked for the Student list in red and United Serbia in blue
  on the settlement maps. The maps had coloured by rank in the election to keep colour from meaning a list; a
  map people share is read against what they expect, so the two largest lists' colours are now set by hand per
  election in `data/list_colours.csv` (round, number, colour), and every other list still takes the next free
  colour by rank. The rule is the same for every list — any list can be given a colour there — and it stays out
  of the checks, which never look at who gains. The file is in the round pages' fingerprint.
- **8 Nov 2026, charts in the shared map image.** The PNG a reader downloads now has the map on the left and
  two charts on the right: the municipality's result with the country's share as a tick, and turnout by
  settlement with the municipality's turnout as a line. Both are drawn on the canvas from the page's own JSON
  (`#mun-data` carries each list's colour slot and country share, and the municipality's and country's turnout),
  so the image needs no server and no third party, and it is the same for every municipality and every list.
  The page itself does not gain the charts: the image is the thing people pass around, the page has the table.
- **8 Nov 2026, custom domain.** The site moved to izbornipodaci.rs, the name of the GitHub organisation
  spelled as one word; GitHub Pages stays the host and the old github.io address redirects. The address lives in
  `SITE_URL` alone, and the image people download names the new host so a shared picture leads back to the site.
- **8 Nov 2026, a misread "на" dropped controllers.** Mali Iđoš, station 1: the Student list's member and deputy
  are in the decision, the station showed none. OCR had read "на предлог" as "ха предлог" in three of six slots and
  the parser kept only slots with "на предлог", so those lists vanished without a trace (not "unparsed", just
  fewer slots). A proposal is now "предлог" with any short word before it, and decisions carry the reading's
  version so a parser fix rereads what the old reading read (8,700 decisions this time, one daily run). The
  symptom to watch for: a municipality whose decisions read far fewer slots than its stations have lists.
  The reread (8,701 decisions, one run) found 470 controllers more in 281 decisions and lost none. The second
  pattern from the same municipality (station 16): OCR garbled the word "члан" in one slot's heading, the slot
  ran into the one before it, and the merged text named two lists; a slot now starts at any "N. <short word>:"
  (reading version 3, read again). Each new example Marko sends is worth a diagnosis before a guess.
  Marko then checked nine suspect decisions by hand: two kinds of suspect. Decisions that add up (a supplement
  or a mislabelled standing decision beside the real one) only looked thin per document — `coverage` unions them,
  nothing was lost. The real losses were three layouts (Žabalj, Zrenjanin, Novi Sad). So the daily merge now logs
  `odd_stations`: stations lacking a list that 90% of their municipality's stations have, computed on the union,
  the honest version of the per-document statistic.
  Reading version 3 was a regression: its looser slot pattern also passed the sanity check that picks a PDF's
  text layer over OCR, so bad text layers (whole commissions: Čoka, Trstenik, Žitorađa…) were taken for the
  decision and 4,700 slots vanished for an hour. Version 4: the strict pattern decides the text layer, the loose
  one applies only inside a decision that has proper slots. Lesson: a pattern used as a sanity check must not be
  the one you loosen. Version 4 also reads again (line by line, or OCR instead of the text layer) whenever a
  decision names more members than slots were found, takes "подносиоца" as a proposal's mark, a slot whose number
  OCR turned into letters, and a deputy's role without its colon.
- **8 Nov 2026, "(naselje nije utvrđeno)".** Marko asked which six Novi Sad stations had no settlement and why.
  Two had an address whose building OCR mangled a little ("ЂУРАДАНИЧИЋ", "ІІСВЕТИ CABAіІ"), so the building rule
  (`places.contradicts`) set the whole address aside, town included; it now tolerates a lost space or a letter or
  two. The other four had no usable address line at all (no address, no town in it, or the building and the town
  run together) and got rows in `data/settlements.csv` with the reason. The map's settlements are clickable: a
  settlement's stations list under the map, from the page's own JSON.
- **8 Nov 2026, the 700 stations without a settlement.** 442 of them had an address from the board decision that
  names only the building (Senta, Negotin, Bajina Bašta, Valjevo …), 173 none at all (Prokuplje, Knjaževac). Guessing
  "no street means the town" was rejected: the same commissions write bare names for village stations too. RIK's
  station lookup (biracka-mesta/) has no addresses either. The primary source is the local commission's decision
  on polling stations (law, art. 56–57: number, name, address, area), published on the web — a handful are in
  RIK's register of commission documents (Negotin, Ljubovija, Pirot), the rest on the municipalities' own sites.
  `data/station_lists.csv` collects the links Marko or I find, `stationlist.py` reads them (rule "list", before the
  address rule, passed on to other elections), the **stations** workflow runs it. An act of 2023 serves 2026
  through the places. Rows must look like the station (a shared word in the name) so a renumbering can't move a
  station to another's settlement.
  9 Nov: the first reads put whole villages one station off (Barajevo, Varvarin, Dimitrovgrad, Odžaci): a table
  cell of several lines puts the start of a row's address above its number in the extracted text. Now both
  alignments are read and the one agreeing with more of the board decisions' explicit addresses is kept; an act
  agreeing with under 60% of at least four is set aside whole, and an explicit address beats the act's row.
- **9 Nov 2026, the shared map image.** Marko: the numbered settlements looked like a bug (a key with no heading,
  among the facts), the country tick wasn't explained, Vranje's 90 settlements were a crowd, and the no-result grey
  was too close to the blue list. Now: the map is drawn 1.6× with names at their size and cropped to the outline;
  a name that would cover a wider settlement's name becomes a number (`maps.label_box`, judged at that scale),
  numbered row by row; the key sits beside the map under the charts, small, with a heading; the tick is explained
  under the chart's title and labelled on the first bar; `--mp-none` is a neutral grey (light #e6e3de, dark #3b3a38).
  Same day: on Pirot's map the Student list (red, set by hand) and Faktor stabilnosti (orange, by rank) read as one
  colour. `maps.slots` now pushes a hand-set colour's look-alikes (`ALIKE`: red–orange–pink, blue–purple,
  green–dark green, orange–yellow) to the end of the free slots, and with colours set by hand takes yellow and green
  first (`PREFER`), apart from red and blue for most eyes. Without hand-set colours the order stays the seats'.
  Same day: the image's source line names the page (izbornipodaci.rs/pirot, `mun_url`), so a shared image leads back
  to it. The turnout chart beside the map gave way to how the twelve largest settlements voted: a 100% bar each,
  split among the four largest lists in their map colours (Marko chose this of three drafts: the settlements named
  per leading list, which repeated the legend; the two largest lists' difference, one-sided where one list leads
  everywhere). Turnout stays in the facts under the map. The share beside each bar is in the leading list's colour (yellow and pink darkened), so it says whose it is.
- **9 Nov 2026, shades on the settlement map.** Marko asked for gradients showing how strong a settlement is. A
  first version had two modes behind buttons ("who leads", "my list"); Marko wanted one map and one image showing
  everything, no buttons for now. So: the leader's colour by opacity in four fixed steps of the leader's share
  (`maps.LEAD_STEPS`, fixed so maps compare across municipalities), drawn at build time, the legend giving each list
  its four shades and one line with the steps; the numbers per settlement are in the chart beside the map in the
  image. Opacity over the page rather than a mixed colour, so both themes work.
- **9 Nov 2026, Novi Sad by its quarters.** Marko wants the city of Novi Sad drawn by its quarters (Telep, Novo
  naselje…), not as one settlement. First a probe (`izbori geo --quarters-inspect`) of what OpenStreetMap has
  inside the settlement. It has 24 quarters with boundaries (Telep, Liman 1–4, Detelinara, Grbavica; Novo naselje as
  Bistrica) and 31 local communities (admin_level 10, finer). Marko left the choice to me: quarters, the names he
  used. `--quarters` keeps them in data/geo/quarters.json with public buildings' names → quarter, to place each
  station by its building's name where the city's act gives no address.
  First fetch: 25 quarters; 141 of the 153 stations in the settlement placed by building (schools, kindergartens,
  local communities' halls); the rest (a utility company, pensioners' clubs) stay "Novi Sad". Quarters are taken
  smallest first, so Sajlovo isn't swallowed by the industrial zone around it. Bistrica is shown as Novo naselje.
  Same day, Marko: keep the municipality's map as it was and open the urban city, larger, on a click on Novi Sad.
  So the quarters no longer replace the settlement: `Site.quarter_zoom` draws a second map (own hatch pattern ids,
  "zh1…", so it paints while the first steps aside; the first is hidden by visibility, not display, for the same
  reason), the page data carries `q` (station number → quarter) for its panel and its PNG.
  Same day, Marko: make similar shades easier to tell apart. Five steps instead of four (60–70% and 70%+ apart, as
  most of Novi Sad's quarters sat in one step), opacities evenly spaced, and the top step darkened
  (brightness 0.72, `mp-deep`; mun.js darkens the same in the PNG) since opacity alone can't go past full.
  Same day, Marko: two names and two places instead of the in-page zoom — "Opština Novi Sad" (the whole, Novi Sad one
  settlement) and "Grad Novi Sad" (the urban city by quarters) in the search, the labels and the references; a click
  on Novi Sad on the Opština page goes to Grad. Grad is `municipality_context(part=True)` at /novi-sad/grad/: the
  same page over the city's stations, quarters as its settlements, no similar-municipality ranks, no history strip.
  RIK's name "Град Нови Сад" is shown as "Општина Нови Сад" (`display_names`, `mname` in station/check/repeat/
  changes); the data files keep RIK's name.
  Same day, Marko asked why /beograd/ had no PNG: the export lived in mun.js, which a city's page doesn't load. It
  moved to `static/mapimg.js` (`window.mapImage(figure, data)`), used by mun.js and city.js; the city's JSON gained
  each municipality's registered, valid and votes and the lists' colours, and the image says "the city" and "the
  largest municipalities".
- **8 Nov 2026, preparing for local elections.** Marko asked how to prepare; agreed order: (1) a registry of the
  municipalities' sites and a weekly watch for the commissions' documents (done: `data/municipal_sites.csv` from
  RIK's address book — only the e-mail's domain is kept, never the address, phone or mailbox — and `watch.py`);
  later a pre-election mode of the municipality page (stations, controller coverage, deadlines before any result),
  rounds of one day grouped on the elections page and the home, the "area" column of the station acts as a
  street index for "where do I vote", feeds that announce new commission documents, and a size/time measurement
  with dozens of simultaneous rounds. Not a dry run on Belgrade 2024: Marko expects Belgrade's commission to be the
  best-run; a small municipality's local election is the better test.
  9 Nov: the first pass left 100 of 148 sites with nothing — 28 didn't answer (24 URLError, 4 HTTP 403/5xx),
  72 answered with nothing found. Marko asked for both now. The watch goes three links deep (pages about documents,
  notices and decisions too, up to 100 pages), reads WordPress's upload search and the sitemaps, sends a
  browser-like client name, and logs why a site failed, so a certificate problem can be told from a site that is
  down. Run by hand for those 100 (`only`).
  9 Nov, what to do with what the watch found (2,607 documents, 48 municipalities): Marko chose local elections
  from the commissions' own documents — board decisions for controllers by list, then the results tables — on
  Pančevo first (1,082 documents: 2023/11–12 and 2024/04 uploads), plus the new acts on polling stations for the
  stations still without a settlement. `local.py` starts with a masked probe of the layouts (workflow **local**).
  The first probe of Pančevo's 121 commission documents: minutes of the commission's sessions and proposals of
  lists, many of them of the 2026 parliamentary election (the site's upload folders don't follow the dates). The
  results of a local election weren't among them: the watch kept only documents about stations, boards or "the
  commission", and a results report names none of those. It now also keeps "results" (rezultat + izbor, odbornici,
  zapisnik, izveštaj) and "lists" (list + proglašenje, zbirna, kandidati, odbornici).
  Marko asked how to handle 145 sites that all differ. Not a project or an analyser per site: the law fixes the
  documents, the sites differ in where they put them. So three layers in this repo — discovery the same for every
  site (a site's quirks as data in municipal_sites.csv, code only where nothing else works), classification by the
  first page's words of the form (`local.classify`, data/local_docs.json), readers per kind of document, not per
  site, a new layout a new variant of the reader. Unclassified documents go to a list for a person, coverage per
  municipality is shown as a fact. Order: classification, Pančevo end to end, then Temerin and Sečanj.
  Marko: Valjevo's site is valjevo.rs, not the mail's valjevo.org.rs, "and some sites may be like that". A domain
  that doesn't answer is now tried as name.rs, name.org.rs, name.ls.gov.rs, name.gov.rs; the one that answers is
  written back to municipal_sites.csv with the old one in the note, so the file stays the record of where to look.
  The deeper pass over the 100 sites crashed after 2.5 hours on one malformed link ("Invalid IPv6 URL") and kept
  nothing, since the store was written only at the end. Now a link that doesn't parse is skipped, a site that
  throws is logged and passed, and the store is written after every site with finds.
  10 Nov, Pančevo's local results: its "ukupan izveštaj o rezultatima … za sva biračka mesta" (2 June 2024) is a
  scanned typed table that OCR reads well (79 stations, five lists). `local.result_rows` checks each row against
  itself and sets aside what doesn't add up; the reading becomes a draft round in RIK's format (`local.build`,
  data/local/L80314-20240602/), its stations named from the 2026 round (the same 79, by number), published by
  moving it to data/rounds/ after a check. The lists' names come from the proclamations (contestants, public as
  RIK's are; a precedent: Belgrade 2024's round names its lists' leaders). Station minutes (158) are not read:
  hand-filled, OCR is unreliable on them.
  First reading: 74 of 79 stations add up; registered (106,192) and valid (49,527) match the published totals to
  the vote, invalid is 26 short (1,567 of 1,593: some derived cell). Marko read the five set aside in the report
  (`data/local_corrections.csv`) and confirmed the lists' names (`data/local_lists.csv`, from the decision on the
  collective list, a scan). With them every list's total matches. The report's column order differs from
  Wikipedia's (ordered by votes): 1 Vučić, 2 SVM, 3 Pančevo protiv nasilja, 4 POKS, 5 Pančevačka grupa.
  Published the same day as round `L80314-20240602` (moved from data/local/ to data/rounds/): the first local
  election read from a commission's own documents. Invalid ballots looked 26 short of Wikipedia's 1,593, but Marko
  checked the four cells derived from a sum (stations 16, 26, 69, 74) and they are right: Wikipedia's figure is
  voters (51,120, which matches) less valid votes, while the report's invalid ballots count what was in the box
  (51,094 ballots = 49,527 valid + 1,567 invalid). The 26 are voters who signed but left no ballot in the box.
  10 Nov, Pančevo's polling boards. The commission published, per station, the standing composition
  (`N-stalni-sastav.pdf`, 79), the extended (`BM-N-Prosireni-sastav.pdf`, 79; classified as lists' documents,
  since they name the lists) and 44 changes (`N_PS.pdf`, `izmena-bm-…`). The extended one writes a slot as
  "1. član: <person>, <…>, <list>;" and its deputy on the next line, with no "na predlog", which RIK's reader
  doesn't take, so `local.board_slots` matches each role's own text to a list (`boards.match_list`) and keeps
  only the list's number and whether the role was filled; changes and the standing composition are kept as links
  (`local.read_board`, by the decision's title). `izbori local --boards ROUND` (the workflow's `results` input with
  `kind` boards) reads the documents of the 60 days before the election into the round's boards.json in RIK's
  store format, with the commission's own link, so the site shows controllers and decisions as for RIK's rounds.
  With `path_has` as well, only those documents are read and each role is logged with every word masked but
  the lists' own after its first comma (`local.role_shape`), to see why a role matched no list; nothing is kept.
  The first full reading put list 4's roles under list 3 ("Панчево-Борба против насиља" shares three words with
  list 3's name; `boards.match_list` divides by the shorter name) and matched none of list 5's, named in the
  decisions as Група грађана „ГРУПА ПАНЧЕВО", not by its ballot name. `local.role_list` now counts, in the role's
  text after the person, the words of each list's name that no other list's name has ("Панчево", "против",
  "насиља" are in three; "борба" only in list 4's), the best clearly ahead and with two of its words in the text;
  or, for a citizens' group, the round's only citizens' group list (two such lists: not guessed). OCR's garbled
  "2. чпан;" and "~ замсник 1. чпана:" at a line's start still start a role (the deputy's on one line: "сутра" at
  the end of a line once took the next member for a deputy), and a role in quotes, as a supplement (допуна)
  writes it, is read. Third reading: lists 1–5 have a member at 79, 76, 79, 70 and 65 of 79 stations; at 103
  slots a list named its member and no deputy (the decisions have no deputy's line there). Left: station 65's
  decision, whose OCR garbled lists 2 and 4 (four roles matched to no list), and a supplement at station 54
  whose one role names its list otherwise than any of the five (not guessed). The controllers' note on a local
  round names the commission's decisions on the municipality's site as the source (`ctrl_note_local`).
  10 Nov, Temerin and Sečanj: the watch found neither one's report of results. Sečanj's commission adopted its
  "Ukupni izveštaj o rezultatima" on 21 Dec 2025 (minutes of its 25th session, after the repeated vote at
  stations 7 and 8), but no upload by that name was among the documents: the media search looked only for boards,
  stations and the commission. It now also asks for results and reports, and the site's search for "rezultati
  izbora". That found both: Sečanj's `2025/12/Ukupan-izvestaj.pdf` (classified as a list's document) and
  Temerin's "УКУПАН ИЗВЕШТАЈ О РЕЗУЛТАТИМА ИЗБОРА ЗА ОДБОРНИКЕ…" (dated 6 June, its own day). So `--results` no
  longer asks for the kind or the election's day: any local report with "izveštaj" in its link, dated up to 40
  days after, is read, and the one with most stations kept (`local.report_candidates`).
  Both reports hold only the municipality's totals (Temerin: 31 stations, 24,763 registered, 11,687 valid, four
  lists; Sečanj: 17 stations, 10,226 registered, 6,787 valid, five lists). Results by station are only in the
  boards' minutes, filled in by hand: OCR reads "5 4 6'" for a number. Marko chose to have them read by eye:
  `local.crop_results` cuts out the minutes' results section (from "РЕЗУЛТАТИ" to the board, its members,
  signatures or remarks, by Tesseract's line boxes), the images go to a temporary branch `crops-tmp`
  (a run's artifacts are stored where the session can't reach), deleted once read, and Claude
  reads the numbers into `data/local_hand.csv`; each row must add up and all of them to the report's totals,
  and a row that doesn't is left for Marko.
  Read the same day. Temerin: 31 stations, every row adds up, and their sum is the report's to the vote
  (registered 24,763, voted 12,055, ballots 12,054, invalid 367, lists 7,208 / 2,002 / 2,055 / 422). Sečanj: 17
  stations, stations 7 and 8 from their repeated votes (10 and 17 Dec 2025; the first minutes summed with the
  rest miss the report by 10 valid votes, the repeats match it exactly): voted 6,966, ballots 6,965, invalid 178,
  lists 4,103 / 285 / 111 / 2,179 / 109; the registered voters add up to 10,227, one more than the report's
  10,226, with every cell read twice: left as the minutes have it, for Marko. The lists' names are printed on the
  minutes. Published as `L80446-20240602` and `L80373-20251130`. A municipality's page no longer lists another
  municipality's local election among the elections it "didn't vote in".
  10 Nov, the classifier reads the title first. The whole first page misfiled documents that name lists,
  boards and results in passing: Pančevo's extended boards (BM-N-Prosireni-sastav) as lists, Sečanj's report of
  results as lists, and the appointments to Sečanj's commission on the lists' proposals as results. Now the title
  (from the heading in capitals — РЕШЕЊЕ, ИЗВЕШТАЈ, ЗАПИСНИК, ОДЛУКА — 400 characters) is matched first
  (`local.TITLE_KINDS`, with a new kind, `commission`, for appointments to the electoral commission), the page
  only when the title matches nothing. Entries carry the classification's version (`v`); `run_classify` reads
  the new documents first, then every entry of an older version again, so one rule applies to all.
  `izbori local --overview` answers what can be published next: per municipality, its local documents
  grouped by time (a document's day is often its own date, not the election's), and for each group whether a
  report by station reads (`result_rows`, at least 3 rows), only a report of totals exists, or only minutes.
- **10 Nov 2026, Novi Sad's stations without a quarter.** 13 of the city's 153 were left out of the quarters
  (round 680072). Why: a name with no quotes holding a building's whole name and more (ГРАДСКА УПРАВА ЗА
  ИНСПЕКЦИЈСКЕ ПОСЛОВЕ ГРАДА НОВОГ САДА; the rule took only names inside quotes); local communities named for a
  neighbourhood OpenStreetMap draws inside a quarter but leaves out of the map (МЗ САЈЛОВО ×2, МЗ ШАНГАЈ); and
  buildings outside the fetched kinds (ЈКП Водовод и канализација, ЈКП Градско зеленило, Железнице Србије, ДЕС,
  two pensioners' clubs) or missing from OpenStreetMap (ПУ Радосно детињство – вртић Чаробни шешир ×2, Дом
  здравља Лиман). Same rules for every station: an unquoted name is also matched by a building of three or more
  words it holds whole; a named place at least 80% inside one other quarter is a name for that quarter (Liman,
  over Liman 1–4, is not); and the fetch also takes offices, companies' buildings and social centres. No
  per-station table: what OpenStreetMap doesn't have stays out of the quarters.
  First refetch: 142 of 153 placed (the water utility in Rotkvarija, the inspection office in Stari grad).
  Sajlovo and Šangaj are only points in OpenStreetMap, so a neighbourhood's (or locality's) point inside a quarter
  is a name for it too; a suburb's label, over several quarters, is not.
- **10 Nov 2026, Novi Sad's stations placed by an address.** Of the 11 stations OSM has no building for, Marko
  gave four addresses (Čarobni šešir: Desanke Maksimović 80, from predskolska.rs; Dom zdravlja Liman: Bulevar
  cara Lazara 77; Železnice Srbije: Vase Stajića 2; JKP Gradsko zelenilo: Mladena Leskovca 1), kept in
  `data/geo/quarter_addresses.csv` with their source. The geo run asks OSM for those house numbers and places
  each building in the quarter its address point is in; an address OSM lacks places nothing. Sajlovo and Šangaj
  are not quarters (Marko), so their local communities' stations stay apart; DES and the two pensioners' clubs too.
- **9 Nov 2026, today's failed runs.** Three **pages** deploys timed out at GitHub's default 10 minutes in
  "syncing files" (the builds were fine, the next deploys took under 3 minutes): the deploy now waits 30. Two
  **geo** runs failed on Overpass's 504: a third server joins the rotation. The morning's **test** and **stations**
  failures were the station-list bugs fixed the same hour.
- **8 Nov 2026, the search opens the newest election's municipality page.** Marko: whoever picks their
  municipality or station in the search should land on the page just built, with the map. A municipality in the
  search, in the municipalities index and in a station page's crumbs now opens `r/<newest>/m/<code>.html`; the page
  across elections (`m/<code>.html`) stays one link away, as the station page keeps its earlier elections folded.
  Merged the same evening (next entry).
- **8 Nov 2026, one page per municipality and per place.** Marko: the previous designs go out of use; a municipality
  or a place found by the search shows the new page. `m/<code>.html` is now the coordinator's page for the newest
  election with the municipality's other elections at the end (narrative, trends, the table of elections and the
  places across elections, folded), and `r/<id>/m/<code>.html` is the same page for that election (the history only
  on the newest); `municipality_history.html` is gone. Both come from `Site.municipality_context` (per municipality)
  over `Site.round_shared` (per election and language, cached), so the two addresses can't drift apart. Under the
  title, a table of contents and a strip of the municipality's elections; the station page got the same strip, each
  election leading to its block (a link to a folded block opens it, `site.js`). "My list by station" was redrawn:
  bars of the list's share from zero, strongest first, a line at the municipality's share, six strongest and six
  weakest shown — Marko found the symmetric deviation chart unclear at first sight. The header has six sections
  again: "Places to watch" (`repeat.html`, until now "Station history"; the name says what the list is for without
  calling a place guilty, which "problematic places" would) is back between coordinators and analyses, the guide
  shows as "Vodič", and short names take over below 1150 px.
- **8 Nov 2026, cities split into municipalities.** Marko: Belgrade or Niš should come up in the search even
  though RIK splits them into municipalities, and asked how to treat "urban" against "territorial" Belgrade. The
  city is whatever the results put under it (`commission.city_parts`, from the names and districts of every
  archived election), so Belgrade is its 17 municipalities, as RIK counts; the page adds them up by a
  municipality's arithmetic (`cities.py`) and never computes a second "urban Belgrade" total. The customary split
  into ten central and seven outer municipalities is shown only as two groups with subtotals in the table, and the
  page says so. A city with a code of its own and one city municipality beside it (Požarevac + Kostolac, Užice +
  Sevojno) gets the same page, its own row first and marked. One address per city, `g/<slug>.html`; no per-election
  city pages, the table at the end has every election.
- **8 Nov 2026, three small ones from the principles.** The weak-spot cards say what to check, as the station page
  does (same rule, same sentence). The municipality a reader viewed last is remembered from the canonical address
  too (the script only knew `r/<id>/m/`). "Places to watch" filters by municipality and links back; the
  municipality's first card leads there with `#m-<code>`.
- **8 Nov 2026, addresses by name.** Marko: izbornipodaci.rs/beograd, /novisad. Every municipality and city
  is at `/<name>/` (`cities.name_slug`, `cities.slugs`; `<name>/index.html`, since Pages serves folders);
  `m/<code>.html` and `g/<slug>.html` became one-line pages with a meta refresh, so nothing shared breaks, and the
  run-together spelling (`/novisad/`) leads to the hyphenated one. The template helpers `mun_href(code)` and
  `city_href(slug)` are the only way to link a municipality or a city; `r/<id>/m/<code>.html` stays for earlier
  elections (and the newest, with `#bm-N` anchors from the check page). Size: the newest election's municipality
  page now exists twice (by name, and under r/); making the r/ copy a redirect would save ~30 MB but lose the
  anchors unless a script carries the hash — a lever if the budget tightens.
  The same evening the polling places followed: `/<municipality>/<number>/` (`Site.place_path`), `s/<place>.html`
  a redirect. A redirect page is a bare 300-byte file, not a page on the base template: with 8,000 places in two
  scripts the template cost 60 MB.
- **10 Nov 2026, the watch's acts on polling stations.** From the watch's candidates (735 links, most of them
  boards, lists, voting outside the station, forms), 22 acts that decide a municipality's polling stations for an
  archived election were added to `data/station_lists.csv`: for 2022 Blace, Kraljevo, Rača, Bač, Bačka Palanka,
  Opovo, Pančevo (a second act), Šid, Prokuplje; for 2023 Bogatić, Golubac, Rača, Bačka Palanka, Kanjiža, Temerin,
  Lapovo; for 2026 Golubac, Kraljevo, Rača, Bačka Palanka, Leskovac, Mali Zvornik. Amendments alone were left out,
  and acts for the local elections of 2024 (no archived round of those municipalities). Three rows came off: a
  2022 decision that a station's results can't be established (Majdanpek: not a list), and two of Pančevo's 2023 acts —
  one for the 2024 local election, one a four-row amendment that had replaced the whole 2023 decision, since a
  municipality's stations were those of the last act read. Now each act keeps its own reading (`"st"` in the
  round's station_lists.json) and a municipality's stations are merged from all its acts in the file's order
  (`stationlist.merge`); an act taken off the file takes what it gave with it. The stations workflow then reads
  every act again once (`reread`).
  What they read: kept the acts whose rows matched the stations — 2022 Kraljevo (97 stations), Rača (25), Opovo
  (12); 2023 Golubac (26), Rača (20), Bačka Palanka (10), Temerin (16); 2026 Golubac (23), Bačka Palanka (25): 254
  stations with a settlement from their act, and Pančevo 2023 back to its decision's 50. Taken off again: acts
  that read no row as a station (2022 Blace, Bačka Palanka, Pančevo's second act, Šid, Prokuplje's .docx; 2023
  Bogatić, Kanjiža, Lapovo — tables or scans the reader doesn't cut), 2022 Bač (its site didn't answer), and 2026
  Kraljevo, Rača, Leskovac (one or two rows matched, Rača's against the addresses) and Mali Zvornik (it disagreed
  with the board decisions' addresses and was set aside).
- **10 Nov 2026, classifying in parallel.** Reading the first page of all 4,838 documents again (a new
  classification's version) took one runner most of a day at four documents at once. Now the workflow's classify
  is a matrix of 8 runners, each with its share of municipalities (`local.shard_of`: largest first onto the least
  loaded share, the same split in every runner); a municipality stays on one runner, so its site gets no more
  requests at once than before. Each part's `data/local_docs.json` is an artifact, and a merge job commits every
  entry that differs from main's (`local.merge_parts`), also when some parts ran out of time, since a run resumes.
  The crops and crops-read runs have their own concurrency group: they commit nothing to main, so they don't wait.
- **10 Nov 2026, reading sheets for minutes filled in by hand.** Asked whether reading the minutes could be
  automatic, I measured on the 48 stations of Temerin 2024 and Sečanj 2025 read by eye: Tesseract read 14% of the
  handwritten cells; a small network trained on MNIST about 70% (78% once the cells were found by long ruled lines
  only); taking the most likely figures that add up (ballots less invalid are the valid votes, the lists sum to
  them) accepted 10 of Temerin's 31 stations with 2 wrong and 3 of Sečanj's 17 with all 3 wrong — a figure that
  adds up isn't a right one, and the registered voters aren't checked by any sum. So nothing is taken from a
  model. What it does instead: `izbori local --crops … --sheets` (the workflow's crops) puts only the number cells
  on reading sheets, a row per station, with the model's guess under each and red where a station doesn't add up,
  so a municipality is read from two or three images and nothing but figures leaves the minutes. 30 of Temerin's 31
  and all of Sečanj's stations were found that way. numpy, OpenCV and scikit-learn come in with `uv run --with`
  in the workflow only, as shapely does for geo; their tests skip without them.
- **10 Nov 2026, a queued classify builds on the one before.** The classify and merge jobs check out the branch as
  it is when they start, not the commit the run was dispatched on, so a run queued behind another one (the same
  concurrency group) skips what that one committed instead of reading it again and failing to push its merge.

