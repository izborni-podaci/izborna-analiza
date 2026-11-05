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
  - `commission.json`: link, RIK's kind and the day, for the municipal commissions' documents.
  - `observers.json`: the OCR numbers only.
  - `observer_reviews.csv`: what a person found in an observers' record.
- **Stations are keyed `municipality code/number` per round.** Municipality codes are stable across elections,
  but names differ ("Ниш-Медијана" in 2022, "Градска општина Медијана" in RIK's registers). Names map to codes
  with `boards.municipality_key`, using every archived round.
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
  - A full pass happens only when a store lacks something, for example the decisions' links.
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
    Unknown is not zero: a station whose board decision wasn't read has no controller value, and an election
    whose observers' records weren't read has none for them.
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
| boards | daily, until 14 days after election day | decisions on polling boards: plan, four OCR jobs, merge (one commit) |
| observers | daily, until 60 days after election day | OCR score of observers' records |
| pages | on push | incremental site build and deploy |
| geo | by hand | municipal boundaries from OpenStreetMap (Overpass), for the Explore map |
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
- **Belgrade 2024 decisions on polling boards (round 567956):** 127 of 129 are listed under "Београд" with a station
  number, while the results number stations within each city municipality, so they can't be placed. All 17
  decisions on the extended composition are unreadable by the current parser. The round is small and in the past.
- **Kosovo and Metohija on the Explore map:** the maintainer wants them by RIK's municipalities. OpenStreetMap
  doesn't follow that division there; RGZ's register of spatial units does (opendata.geosrbija.rs, free
  account), so it waits for a maintainer to download the layer. Until then the map names them below it.

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
