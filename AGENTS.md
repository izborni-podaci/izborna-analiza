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

- **Static pages in three languages:** Latin (the default), Cyrillic and English.
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
- **Hosting:** GitHub Pages through Actions; the previous build is kept in the Actions cache.
  - Planned: a custom domain, with Cloudflare in front for visitor counts at the edge.
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

- **Custom domain and hosting:** set aside until it is clear how useful the site is; GitHub Pages meanwhile.
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
