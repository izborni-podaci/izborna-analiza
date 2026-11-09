# Izborni podaci

A public site in Serbian (Latin and Cyrillic; every string also exists in English, but the English pages are not built, see Languages). It saves every results file that Serbia's Republic Electoral Commission (RIK) publishes. It checks every polling station by the same rules, whoever the candidates and lists are. It shows observers and journalists where to look.

**Site:** https://izbornipodaci.rs/ (the old address, izborni-podaci.github.io/izborna-analiza, redirects there)

**Status:** first version, being tested.
- **Working:**
  - the RIK client
  - the archive and its change log
  - election math
  - station checks
  - news notes
  - the private target list
  - the site in two scripts
  - Atom feeds and the email digest
  - the scheduled jobs
  - tests on the 2026 parliamentary files
- **RIK is reachable from GitHub's servers.** The probe on 2 November 2026 listed RIK's rounds:
  - parliamentary 2023 and 2026
  - Belgrade local 2024
  - provincial 2023

  This is re-checked before each election.

A Serbian version of this file (`README.sr.md`) will follow.

---

## Who it's for

- **Journalists:** what stood out, at which station, with the numbers and a link to RIK's own minutes.
- **Observer groups:** the same checks during the count, plus a private list of stations to watch next time.
- **Controllers** (members of a polling board's extended composition) **and observers:** a guide to the rules at the polling station, with each article, and every station's documents and history before they go.

## Principles

1. **Same rules for every contestant.** No party is hardcoded. Contestants appear in RIK's ballot order with neutral colours. A test swaps contestants' votes and checks that the flags don't change.
2. **A flag is a question, not a verdict.** Flags mean "unusual, check the minutes". The site never says "fraud".
3. **Flags come from primary sources only:** laws, RIK documents, ODIHR reports.
   - A news report about a specific polling station can be attached to it as a note, marked as unconfirmed.
   - A note never creates a flag or changes the ranking.
4. **No personally identifying data, links to RIK instead.** RIK's results are station totals. Its documents name board members, observers and commission members; the site links to those documents and never records, re-hosts or transcribes the names, even though RIK publishes them.
5. **Nothing from third parties.** No analytics, cookies, fonts or scripts from other servers.

## What it does

```
RIK ──fetch──▶ archive (git) ──check──▶ flags ──▶ site (GitHub Pages)
                                          ├──▶ Atom feeds
                                          └──▶ email digest
                                   private: target list (local only)
```

1. **Fetch.** Ask RIK which elections and rounds exist and how many stations are counted. Download the results CSV when that number changes.
2. **Archive.** Commit the file only if its content changed. Git history becomes a timestamped record of everything RIK published.
3. **Check.** Run the election math and the station checks below.
4. **Publish.** Rebuild the static site, update the feeds and email new flags.

## Election types

| Type | Who wins | What the site shows |
|---|---|---|
| Presidential | A candidate with **more than half of all voters who voted**. Invalid ballots count among those voters, so they work against the leader. Otherwise a runoff between the top two. | Each candidate's share of voters who voted; how many votes the leader is short of a majority; whether a runoff is coming. A round with two candidates is treated as the runoff: most votes wins. |
| Parliamentary | 250 seats by the D'Hondt method. Lists need 3% of voters who voted. Minority lists below 3% take part with votes ×1.35. | Seats; the majority (126) and two-thirds (167) lines; how many votes each list needs to gain a seat or can lose and keep its seats. |
| Local | The same method per assembly, using each assembly's size from its `meta.json`. | One contest per town. |
| Provincial | The same method, 120 seats. | As parliamentary. |

The loader finds contestant columns by their position, not their name. A presidential file with candidate columns therefore loads the same way as a file of lists.

## Station checks

Every check treats every contestant the same way. A station is followed across elections as a place: by address, then name, then number (see [Places across elections](#places-across-elections)).

**Paperwork and arithmetic.** The strongest signals; they apply to every station.

| Flag | Rule | Weight |
|---|---|---|
| More ballots than signatures | Ballots in the box > voters who signed the voter list. The law treats this as a serious error. | 5 |
| Votes don't add up | Contestant votes ≠ valid ballots. | 3 |
| Ballots don't add up | Valid + invalid ≠ ballots in the box. | 3 |
| More signatures than ballots | At least 3 more signatures than ballots. One or two is common, e.g. a voter leaving with the ballot. | 3 |
| More voters than registered | Voters who signed > registered voters. | 3 |
| Likely typing error | Voters exactly equal registered voters (with at least 10 registered), while the municipality's median turnout is below 80%. | 2 |
| Correction published, numbers still don't add up | RIK published a correction ruling (RG-7), but the station still fails one of the checks above. | 3 |

**Changes after publication.** These need the archive.

| Flag | Rule | Weight |
|---|---|---|
| Numbers changed after publication | A number at the station differs from the first value the archive saw. | 3 |
| Correction published, numbers unchanged | A correction ruling appeared after first publication, and no number has changed since. | 3 |

**Recorded at the station.** Remarks and rulings RIK published with the station's minutes (see [Documents per polling station](#documents-per-polling-station)). The flag says the document exists; what it says is only in the document.

| Flag | Rule | Weight |
|---|---|---|
| Voting annulled | A ruling annulling the vote at the station (form RG-9) was published; the vote is repeated. | 3 |
| Results can't be determined | A ruling that the station's results can't be determined (form RG-8) was published. | 3 |
| Remark filed with the minutes | A separate remark on the polling board's work was published with the minutes. | 2 |
| Observers' remarks | A person read the observers' record (RG-11) and found observers' remarks in it (see [Observers' records](#observers-records)). | 2 |

**Unusual results.** Weak signals and often legitimate, e.g. bloc voting in minority areas. They cover stations in Serbia only, not abroad or in prisons.

| Flag | Rule (starting values) | Weight |
|---|---|---|
| Invalid-ballot spike | At least 8% invalid with at least 100 voters. Or at least 10 invalid, at least 4%, and at least 3× the median at the same address, or in the municipality if the station has its own address. | 2 |
| Register jump | Registered voters changed by at least 10% (and at least 20 voters) since the last election held at the same station. | 2 |
| Turnout jump | Turnout changed by at least 20 points more than it did across the stations both elections share. | 2 |
| Sudden rise of registered voters | Registered voters at the same place rose by at least 15% more than the median rise at the municipality's other stations, and by less than 40% (a larger rise is most often a redrawn area and is not compared). A known sign of voters registered where they don't live; also a new suburb. | 1 |
| Turnout far from the settlement | Turnout at least 20 points from the median of the other stations in the same census settlement (at least two of them). A village that votes like its neighbours is unremarkable whatever the town does. | 1 |
| Near-unanimity | Turnout at least 90% and one contestant with at least 80% of valid votes, with at least 50 registered. | 1 |
| Very high turnout | Turnout at least 90% with at least 50 registered, when near-unanimity doesn't apply. | 1 |
| Same votes as another station | Every contestant got the same votes as at another station of the same municipality, with at least 50 votes and at least 3 contestants with votes. A chance match is then rare (none in any archived election, even at 10 votes and 2 contestants); a copied record or a slip when the numbers were entered gives one. | 2 |

The two turnout checks skip stations flagged as a likely typing error.

**Context statistics.** These cover the whole round and are never station flags. They are computed for the two contestants with the most votes, whoever they are:
- last-digit test
- round percentages: stations where turnout or a share lands within 0.05 points of a whole percent, against the number expected by chance. The expectation depends on each station's denominator (of 500 votes every fifth count is a whole percent, of 737 about every tenth), so it is computed station by station, exactly, leaving out counts within 10 of none or all; p is the Poisson chance of at least that many, a little cautious
- correlation between turnout and share
- turnout histogram

**Per municipality** (`stats.py`), on the round's page: round percentages (turnout and the two shares pooled, where at least 5 hits are expected) and last digits (every contestant's counts of at least 100, where there are at least 50). Each p is multiplied by the number of municipalities tested (Bonferroni), and the five smallest are shown; below 0.05 after that, a municipality is worth a question. On the archived elections none is (the smallest: 0.14 for round percentages, Kraljevo 2023; 0.07 for last digits, Smederevo 2022). Like the round's statistics, they are not station flags: a test over many stations can't say which of them is unusual.

## Documents per polling station

RIK's register of minutes ("Записници", e.g. [parliamentary 2026](https://www.rik.parlament.gov.rs/zapisnici/779676)) lists every document published for each polling station: the minutes (RG-2), the **observers' record** (RG-11: which observers attended and their remarks), separate **remarks**, corrections (RG-7) and rulings that annul the vote (RG-9) or find that the results can't be determined (RG-8). RIK's results export carries only the minutes and corrections.

`izbori documents` (and the daily **documents** workflow) reads the register for recent rounds and rounds not read yet:
1. pages through `POST /get-election` for the round, ten stations at a time;
2. keeps, per station, each document's label, link and upload time in `data/rounds/<id>/documents.json`;
3. never stores names: the register has none, and the documents themselves (which name board members and observers) are linked, never copied.

Station pages, the lists to check and the JSON name each document by its kind. When the results export's link to the minutes changes, the earlier minutes stay on the station as **earlier minutes**, so both versions can be opened and compared; a replacement is not a flag (8 Nov 2026: a commission re-uploading a whole municipality's minutes had flagged every one of its stations, which said nothing about any station's numbers). Remarks and the RG-8 and RG-9 rulings become flags (see [Station checks](#station-checks)); the observers' record is linked on every row, and the "In short" text says in which elections it exists. Remarks written by hand inside the observers' record become flags once a person has read them (see [Observers' records](#observers-records)).

The first reading of a round, and any reading of a round older than 60 days, is recorded without a feed entry; new flags from documents of a recent round go to the feed like any others. The register uses today's municipality names, so names from every archived election map to the codes (the 2022 table writes "Ниш-Медијана" for "Градска општина Медијана").

### Electoral commission documents

RIK's register of additional documents also lists, per municipality, what its electoral commission publishes: minutes of its sessions, reports on the results, decisions, resolutions and notices. `izbori documents` reads them once for every archived round, and then only what is new while the round is recent (one request when nothing is). Each is kept by its link, RIK's kind and the day it was published, in `data/rounds/<id>/commission.json`; the titles are not kept, since the commissions write them and they may contain names. RIK's own documents are left out. The municipality's page lists them by kind and day.

Where a city's commission runs the vote in all its city municipalities, RIK lists its documents under the city, which the results don't have (Niš; Belgrade at its city election of 2024). Those documents keep RIK's name for the city, and every city municipality of that city shows them under its own, as its city commission's: the city is joined to its city municipalities by every election's names ("Ниш-Медијана" in 2022) and districts ("Град Београд"). A city with a code of its own lends its documents the same way to the city municipality of its district (Kostolac and Požarevac, Sevojno and Užice).

## Observers' records

The observers' record (RG-11) lists, for each observer at the station, whether they had remarks, with lines to write them on. They are handwritten scans, and "нема" or a line struck through the empty space is common, so they aren't turned into flags automatically. Two parts work together:

1. **A person reads the record.** `data/rounds/<id>/observer_reviews.csv` has the columns `municipality_code`, `station`, `remarks` (`да`/`не`, `da`/`ne` or `yes`/`no`), `summary_sr`, `summary_en`, `checked` (the date). A "yes" becomes the flag "Observers' remarks" with the summary; a "no" shows on the station's page as read. **Summaries never name anyone.**
2. **OCR orders what to read.** `izbori observers` (and the daily **observers** workflow) reads each record once, finds the remark lines between "… су следеће:" and "(примедбе уписује …)" (each column of a landscape record on its own), and scores how much is written there: the share of dark pixels, leaving out the printed rules, plus the words OCR finds, less for a lone "нема". Only numbers are kept (`data/rounds/<id>/observers.json`), never the text, and a score is never a flag. `izbori observers --review --html review.html` writes the records not yet reviewed, most written-in first (`observers-review.csv`, and the same as a page with links); fill in `remarks`, the summaries and the date there, and `izbori observers --merge observers-review.csv` copies the rows with a yes or no into the round's `observer_reviews.csv`.

A high score means "read this first", not "there are remarks": a sentence such as "no remarks, so no need to sign" or lines struck through also leave ink. On a sample of 150 records from 2026, 136 scored below 2; of those scoring 5 or more that were checked by eye, all had something written in the remark lines. To tune the score on real records without showing what is written, `izbori observers --round <id> --station <code>/<number> --diagnose 5 --layout` logs the lines OCR found and the areas it measured, every word not printed on the form masked.

## Controllers on polling boards

Each list may appoint a member and a deputy to every polling board's extended composition; people call them
controllers. For each polling station the local commission publishes a decision listing every list's slot, with
the names or left blank. RIK publishes them in its register of decisions on polling boards.

`izbori boards` (and the daily **boards** workflow):
1. reads RIK's register of decisions for the round;
2. reads the decisions on the extended composition with OCR, since most are scans;
3. keeps, for each polling station, the address and, for each list, whether it appointed a member and a deputy;
4. never stores or logs names. An address is checked before it is kept: a member's line read where the address should be is dropped.

How a decision is read: members numbered "1. члан:" or "1) члан:" first; failing that, the layouts some whole
municipalities use: unnumbered entries, each role naming its list ("- члан: … на предлог … листе X"), or each list
first with its people under it ("На предлог … листе X: члан: …, заменик члана: …"). A table with a row for each
member and each deputy, each with its own proposal (Ub, 2026), is read row by row: where OCR read such a page
column by column (slots' numbers and roles alone on their lines), it reads it again line by line, and each
numbered slot's list is the one its text names most, its own number first when it names that one. Only filled in
or empty is kept for each list. After every merge the log lists, per municipality, the stations whose read decisions lack a list that nine in ten of the municipality's stations have (`boards.odd_stations`): where a commission's layout loses a slot, this is what it looks like; some of it is real, so it is a list to look at, never a flag. A proposal is "предлог" with whatever short word OCR put before it: "на" is often
misread ("ха", "иа"), and a slot whose proposal wasn't recognised used to be dropped, so the station showed no
controller of that list. When a decision names more members than slots were found (a number or a word OCR garbled), it is read again line by line, and by OCR where the text layer was used, and the reading with most slots counts. Every decision keeps the version of the reading that read it (`v`); when the reading
learns to read more, the version is raised and the daily run reads the older decisions again by their links,
the current ones untouched.

What a decision is comes from RIK's register: the label the commission picked when it uploaded it, and the
commission's own title. The label decides, but at a station with no decision on the standing composition and two
on the extended one, the one whose own title names the standing composition, or the president whom only the
standing composition has, is the standing one (Ub's standing compositions in 2026 were uploaded under the extended
composition's label). Elsewhere the title doesn't overrule the label: Ada's titles name the standing composition on
both of a station's decisions.

Where a decision goes: the register names the municipality and gives the station's number and name. A city's
commission may list its city municipalities' stations under the city (Kostolac's under Požarevac and Sevojno's
under Užice in 2026), each numbered within its own municipality, or under a name the results don't use (Niš). The
station's name then says which: the same number and name in a city municipality of the same district, or in a
municipality whose name in any archived election, or whose district, contains the register's (Belgrade's 2024
decisions are under "Београд"). RIK lists the boards it appoints itself, abroad and in prisons, under "РИК": they
are placed among those stations the same way. `--reindex` places every decision again after these rules change;
the plan logs what was placed how and what wasn't, naming municipalities only.

The workflow splits the reading so that four jobs read at once, about four times faster (a whole election's 8,700 decisions in about an hour and a half instead of five and a half): `--plan plan.json` indexes the register and lists what to read; four jobs each run `--read plan.json --shard I/4 --out part-I.json`; `--merge plan.json part-*.json` keeps the index and every part in the round's store and commits once. Run without these, `izbori boards` does all three in one process.

The site then shows, for each list, at how many stations it has a member, and on each station's row which
lists do. The private target list gets the lists with and without a member.

Every decision on a station's board is also linked on the station's page, under "Decisions on the polling board":
the standing and extended members, changes to either, and refused proposals, for the original and any repeated
vote. Only the link is kept, never the content; the municipality's lists keep to the documents of the vote.

Limits:
- This is who was appointed before election day, not who turned up. Attendance is only in the minutes.
- Later changes and dismissals are not yet applied; only appointments and supplements are. If a station voted
  again, only the boards appointed for the repeat vote count.
- A few decisions may be misread or filed under the wrong type by the commission; each station shows whether a
  decision was read at all.

Results are in `data/rounds/<id>/boards.json`.

The derived stores (`boards.json`, `documents.json`, `commission.json`, `observers.json`) are written one entry per line, so that git keeps a small diff when a few entries change.

## Notes from news reports

A maintainer can attach a news report about a specific polling station as a note. Notes appear next to the station's flags, labelled "media report, not confirmed".

- Notes are kept in `notes/<round>.csv`, one row per report. The columns are:
  - `municipality_code`, `station`
  - `date`, `outlet`
  - `url`, `archive_url`
  - `summary_sr`, `summary_en`
- Each note records an archived copy of the article, because articles get edited or removed.
- The outlet's name is always shown, so readers can weigh the source.
- Summaries don't name voters or board members.
- A note never creates a flag or changes the ranking. If the minutes or a RIK ruling confirm the report, the flag comes from that document.

## Observer target list (private)

`izbori targets` ranks stations as places to watch at the next election. Each row has:
- the municipality, station number and address
- a score and the reasons for it
- a link to the minutes
- any news notes, shown as context with no weight

The score adds up the flag weights, round by round. Each older round counts 70% of the one after it.

**The list is never published.**
- It is written only to a local file, and `.gitignore` keeps it out of commits.
- It is never built in GitHub Actions, because anyone with a GitHub account can download build outputs from a public repository.
- Groups get it as a CSV or a printable page.

## The site

**Languages:** Serbian Latin (default) and Serbian Cyrillic are built (`i18n.BUILT`). Serbian text is written once in Cyrillic and converted to Latin automatically, as are RIK's names. Every string also has an English version (`i18n.LOCALES`), but the English pages have not been built since 8 Nov 2026: they were 291 MB of a 962 MB site against GitHub Pages' 1 GB limit; adding "en" to `BUILT` brings them back. Pages are written without the templates' indentation (`site.compact`), which was 5–6% of the site.

**Pages:**
- **Home** (`index.html`), designed for three kinds of reader (8 Nov 2026): the question and the search, with three things to try (the largest municipality, a station by name, a station by number); three doors: *Moje mesto* for anyone (the search, and the places viewed in this browser), *Za kontrolore i koordinatore* (a municipality picker that opens the municipality's page in the latest election, and the municipality viewed last), *Analize i podaci* (three questions from Explore, all the questions, the data); **what stands out** in the latest election, four cards computed at build time by `highlights.py`, one rule each and the same for every list: the list whose share differs most between settlements under 500 people and cities over 100,000; the municipality with the largest share of flagged stations (at least 10 stations, in the country), and the two after it; the places flagged in every election they took part in (at least three); the three lists with most votes, each with the municipality where its share is largest and where it is smallest (at least 10 counted stations); then why to trust the site (sources, what a warning is, no names and no tracking). The next election, when one is entered in `data/elections.csv`, shows under the search with its deadlines. The places and the municipality a reader views are kept only in their browser (`localStorage`), as shortcuts on the next visit, with one button to forget them; nothing is sent anywhere.
- **Navigation** (every page): *Početna*, *Izbori* (the elections; current on every round page), *Za kontrolore i koordinatore* (the municipalities; current on municipality pages), *Analize i podaci* (Explore), *Vodič*; the elections, the stations' history and the project are in the footer.
- **Colours** (every page, `site.css` tokens): a colour means a kind of content, never a list or a party. Navy is the brand (header, buttons, borders) and the data (bars, meters, trend lines, heat cells); gold marks the one thing on a page to look at (the big number, the next election, the door labels, the current question); red is only for warnings (flagged rows, warning cells, the "unusual numbers" card); teal is for the lists' card. Dark mode keeps the roles on a night-navy page; print is black on white with the same roles.
- **Elections** (`elections.html`): every archived round, with its counting progress.
- **Municipalities** (`municipalities.html`): every municipality in Serbian alphabetical order (Latin or Cyrillic, by page), its name opening its page in its newest election; with how many elections it took part in (opening its page across elections), its polling stations at the latest one and a link to its electoral commission's documents; a filter finds one by name.
- **Explore** (`explore.html`): the reader's own analyses, computed in the browser by `static/explore.js` (no library, nothing from other servers) from `api/r/<id>/stations.json` and `api/geo/municipalities.json`.
  - The page starts from **questions**, grouped by theme (turnout; lists; the voter register; controllers; settlements; minutes and checks): each is a plain link to an analysis, such as "Where was turnout highest, and where lowest?" or "Does a list have controllers where it has votes?", and the question it answers titles the result. A question that needs a list waits for the reader to choose it, and the list field stands out until then; with two measures of one election that both need a list, the second starts as the first. The settlements theme also links to each election's Settlements page.
  - **Or build your own**, in the order a sentence reads: the election and the measure (in groups: voting, lists, minutes and checks, controllers, settlement from the census, each with a sentence saying what it is), then the view (each with a sentence on what it shows), its level and second measure or election. The filters ("Which stations") are grouped by place, flags and documents, controllers, settlement, and the range of the measure; those in use show as chips under the form, each removing itself, with one link to clear them all. The notes that matter for what is shown (the fingerprint, changes between elections, controllers, the census) appear beside the result; all of them stay at the end of the page.
  - Views: a map of municipalities with the municipalities ranked beside it; two measures against each other (for many stations' shares, a heat grid of counts: the election fingerprint); two elections (stations matched by place as on the pages across elections, municipalities by code, with the diagonal, the totals of both elections and the largest changes; a count such as a list's votes changes by a number and in per cent, either of which ranks the changes); a distribution; a table (a list's votes beside its share, and its share beside its votes); municipalities across elections.
  - Measures, the same for every list: turnout, invalid ballots, a chosen list's share, a chosen list's votes, the largest share of any list, registered voters, voters, signatures minus ballots in the box, flagged, whether a chosen list had a controller (member or deputy of the extended composition), the observers' record, hours from the polls closing to the upload of the station's first minutes (a median for a municipality). No list is ever chosen for the reader; after another election is picked, the reader chooses the list again.
  - The census's measures, from each station's settlement (see [Census 2022](#census-2022)): an urban settlement, the people in the settlement, its population change from 2011 to 2022 and its share aged 65 or more. For a municipality they count its settlements with stations, each once (a share of stations for "urban"), and they aren't compared between elections, as the census is the same. A station whose settlement isn't known has no value. Station lists and CSVs name each station's settlement.
  - Filters: municipality; stations in the country, abroad or in prisons; at least so many registered voters; flags (any, none, one group); a list's controller; the observers' record; a range of the measure; the settlement's kind (urban or other), population, change since 2011 and share aged 65 or more, in the classes of the page by kind of settlement (the bounds come from `bysettlement.CLASSES`; a station whose settlement isn't known is in none). They apply to each election's own stations; the controller filter only to the chosen election, whose lists it names.
  - Every analysis is in the address (`#v=…&r=…`), downloads as CSV (UTF-8 with a BOM, a link per row) and, for a chart, as SVG with its title and source. Clicking a cell, bar, point or municipality lists its stations.
  - The map's boundaries are OpenStreetMap's (ODbL, credited on the map), joined to RIK's municipalities by code; a city RIK counts by its city municipalities (Belgrade, Niš and others) isn't drawn over them. Kosovo and Metohija are drawn in RIK's division, which OpenStreetMap doesn't follow there, from Glaurdić et al. (2021, CC BY 4.0, credited on the map when drawn), as of 1999; the province's municipalities with no station in any archived election are grey and say so.
  - The map's seven classes each hold about as many municipalities, at round limits, so a few far values (the province's low turnout) don't squeeze the rest into two colours.
- **Round:** totals, results, seats or the majority, statistics for the whole round and per municipality, and municipalities.
- **Commissions** (`r/<id>/commissions.html`, `publishing.py`): per municipality in Serbia, what reached RIK for its stations and from its electoral commission, and when — stations whose minutes RIK published and how many hours after the polls closed the first came (median, and how many after 24 hours), rulings correcting the minutes, decisions on the standing and extended composition of the polling boards, the commission's own documents and its city commission's ("+ city's", see [Electoral commission documents](#electoral-commission-documents)), and stations whose numbers changed after publication. Hours come from the upload stamp RIK writes into every document's link; the register of minutes shows the same time for almost every document and, where it differs, a later one. No score: a cell is highlighted by absolute rules (something missing, a median over 12 hours, minutes after more than a day, changes), sortable, with the table as CSV (`api/r/<id>/commissions.csv`). Abroad and prisons are left out, as RIK runs those stations. A commission with no document isn't highlighted: a city municipality may have none of its own where its city's commission runs the vote.
- **Settlements** (`r/<id>/settlements.html`, `bysettlement.py`): the round's polling stations grouped by their settlement in the 2022 census: urban and other settlements (RZS's type); by the settlement's population (under 500, 500–1,999, 2,000–9,999, 10,000–99,999, 100,000 or more); and by its population change from 2011 to 2022 (down more than 20%, 10–20%, up to 10%, the same or more). For each group: stations, settlements, registered voters and turnout; every contestant's share of the valid votes at the group's counted stations; and, where decisions on polling boards were read for at least half of a group's stations (and at least 10), the share of its stations where the contestant had a controller (member or deputy of the extended composition). Between urban and other settlements, the difference within municipalities: other minus urban in each municipality with stations of both kinds, averaged with the smaller side's stations as weights, so a contestant strong in rural municipalities isn't read as strong in villages everywhere. Contestants come in the order of their votes in the whole election; the page ranks and flags nothing. Stations with no settlement are counted and left out. The tables are also CSV (`api/r/<id>/settlements.csv`).
- **To check:** every flagged station. Filter by municipality and flag type, or a whole group of flags (`#g-paper` and the like in the address). Each flag shows its rule, its numbers and RIK's minutes.
- **Municipality** (`/<name>/`, e.g. `/novi-sad/`, `/palilula-beograd/`, `/grad-pozarevac/`: its one address, the newest election in full with the other elections at the end; `r/<id>/m/<code>.html` is the same page for an earlier election; the old `m/<code>.html` and the run-together spelling `/novisad/` lead to it), the coordinator's page (8 Nov 2026). Under the title: a table of contents, and a strip of the municipality's elections, the current one marked. Then in this order:
  1. **My list**: a picker rendered on the municipality's leading list; `static/mun.js` redoes the parts marked "my list" for the list the reader picks and keeps the choice in the browser (`viewed.lists[round]`, with the municipality), never on the server;
  2. **How the municipality compares**: turnout, stations with a flag, invalid ballots and registered voters, each beside the whole country, the municipalities of similar size and kind (`coordinator.py`: five classes of registered voters, 5/15/40/100 thousand, and town or not by the share of stations in RZS urban settlements; at least five to compare with) and the rank among all;
  3. **Weak spots**, six cards in a coordinator's order, each one rule in a sentence, a count, the first five places, a "what to check" sentence (the same one the station page gives for that rule, or one for the card) and a link: flags at more than one election (the same place with a flag at two or more elections in the archive), near-unanimity with high turnout (the `near_unanimity` rule), no controller of my list (from the decisions on boards; the lists grouped by settlement), sudden rise of registered voters and turnout far from the settlement (the two checks above), and no remarks yet the numbers stand out (a paperwork or numbers flag and no remark filed or reviewed);
  4. **My list by station**: one bar per counted station, the list's share from zero, strongest first, a line at the list's share in the municipality and the difference beside each bar; the six strongest and the six weakest shown, the middle behind a button; a red circle where the list has no controller;
  5. the result: who voted and every list's votes and share of valid votes beside its national share;
  5a. **how every settlement voted** (when the municipality's stations are placed in more than one census settlement): a sentence saying which list is first in how many settlements, naming them ("Of 16 settlements, X is first in 15 (…); Y in one (…)"), then, where `data/geo/settlements.json` has the municipality's settlements, a **map by settlement** (`maps.py`: SVG drawn at build time, each settlement coloured by the leading list: the colours the maintainer set for an election in `data/list_colours.csv` (round, number, colour: blue, orange, green, yellow, pink, darkgreen, purple, red — the seats' palette `--s1…--s8`), the other lists by their rank in the election over the colours left, a hand-set colour's look-alikes (red–orange–pink, blue–purple, green–dark green, orange–yellow) taken last, so two lists never share a shade while a distinct colour is free; a close win hatched; grey without a result or a census match; hover for the name and result; names drawn where they fit; the legend counts settlements per list; under it a few facts for sharing: highest and lowest turnout by settlement, where the two largest lists are strongest and weakest, the municipality's turnout beside the country's; a settlement too narrow for its name, or whose name would cover one already placed (wider settlements first, judged at the shared image's scale), gets a number, numbered from the top left, and its name in the key under the map; settlements without a result are a grey with no blue in it; the leader's colour is stronger the more it leads with (`maps.LEAD_STEPS`: under 40%, 40–50%, 50–60%, 60% and over, by opacity, drawn at build time), each list in the legend with its four shades and one line naming the steps; a click on a settlement (or Enter on it) lists its polling stations under the map — link, turnout, my list's share, its controller — and the list follows the list picker; a button saves the map as a PNG with title, legend, those facts and the source line, the map drawn 1.6 times its size on the page with its names at their size and cropped to the municipality's outline, plus two charts beside the map, drawn from the page's own data: the municipality's result (the top six lists, each in its map colour, with an upright tick at the list's share in the whole country, said under the chart's title and labelled on the first bar) and how the twelve largest settlements voted (by registered voters: each a bar of 100% split among the municipality's four largest lists in their map colours, the other lists grey, the leading list's share in the settlement beside it, in that list's colour), then the numbers' key in two columns; drawn in the browser in the light palette whatever the page's theme, with the page's own address under it (izbornipodaci.rs/pirot) so a shared image leads back to its page; a close win is hatched, not lightened), then a table per settlement: stations, population 2022, registered, turnout, the leading list with its share ("close" when under 5 points ahead), my list's share; stations not placed in a settlement are one row at the end;
  6. the polling stations: settlement and name, registered, turnout, invalid, my list's share, its controller (member, deputy, none, not read), flags, minutes and notes. `static/site.js` shows the first ten and a button for the rest; a link to a station further down (`#bm-23`), and printing, open the whole list;
  7. every list at every station as numbers, behind a button, with a CSV made in the browser; then controllers by list, the electoral commission's documents and the link to the commissions page.
  A JSON block (`#mun-data`: lists, each station's votes, valid ballots, board letters per list, flag codes) feeds the script; without scripts the page stands as rendered.
  8. **Across elections** (`#kroz-izbore`, on the newest election only; until 8 Nov 2026 a page of its own at this address): the narrative, turnout and invalid ballots against the country across elections, then, folded, one row per election it took part in (stations, registered voters, turnout, invalid ballots, the top three contestants and the number of stations to check, each linking to that election) and its polling stations across elections, each linking to its own page.
- **City** (`/<name>/`, e.g. `/beograd/`, `/nis/`; the old `g/<slug>.html` leads there; 8 Nov 2026) for every city RIK's results split into several municipalities — Belgrade (17), Niš (5), Požarevac with Kostolac, Užice with Sevojno; which they are comes from the results (`commission.city_parts`), never from a list in the code. RIK has no row for such a city, so the page adds its municipalities up by a municipality's arithmetic (`cities.py`): four tiles beside the country, the result, a map of its municipalities coloured by the leading list (the municipality boundaries, hatched where close; a click on a municipality lists its polling stations under the map — number, name, turnout, warnings, each a link — from the page's own JSON, `static/city.js`), the municipalities with their figures and a link each (Belgrade's in two groups, central and outer, with a subtotal each — a customary split, not RIK's; the city's figures are always all of it), and the city added up at every election. A municipality's page says which city it is part of; the search finds a city by name.
- **Where the search leads** (`search.json`, built per language): a city or a municipality opens its page by name (`/beograd/`, `/novi-sad/`), a polling place `s/<place>.html`; municipalities and places open on the newest election.
- **Addresses by name** (`cities.slugs`): Latin, lowercase, ASCII, hyphens between words, the kind of municipality dropped ("Градска општина Палилула (Београд)" → `palilula-beograd`); a city's own municipality keeps the word ("Град Пожаревац" → `grad-pozarevac`, beside the city's `pozarevac`); a name two municipalities share gets the code appended, the one in the newest election keeping the plain name. Names are stable, so the addresses are; pages at old addresses are one-line pages with a refresh to the new one, since GitHub Pages has no server redirects.
- **Polling station across elections** (`/<municipality>/<number>/`, e.g. `/novi-sad/140/`, one for every polling place, the election's id after the number where another place in the municipality has the same newest number; the old `s/<place>.html` leads there; redesigned 8 Nov 2026 for the casual reader and the coordinator): under the title a strip of the station's elections, each leading to its block (a folded one opens); the latest election first and open — the result with bars (every contestant with at least 1% here, and at least three; each with its share in the municipality and in the whole election; the rest counted), three tiles (turnout with the municipality's and the rank among its stations, invalid ballots, registered voters with the two earlier counts), every flag as a sentence with "what to check" under it, then the station's number and name in that election, the controllers (and the lists without one), the documents and the decisions on the board; then "In short" and the two trend charts across elections; then the earlier elections folded, one line each (turnout, the leader and its share, invalid, flags), opening into the same form. No wide table: everything fits a phone in one column; the numbers are still in the JSON.
- **In short:** both pages across elections open with short labelled rows written from the numbers (`narrative.py`): flags and invalid ballots, turnout and how it compares, who had most votes, how the place changed, and the observers' records. Each row has the main fact first and a line or two of context; the figures are the latest election's unless a line names another. A station is compared with its municipality, a municipality with the whole election. The same rules apply to every place and contestant; the rows state numbers and never judge them.
- **Charts across elections:** below the text, turnout and the share of invalid ballots per election, the place against the area it is compared with (dashed).
- **Search** on the home page finds a municipality or a polling station, by its current or a former number, and opens its one page (newest election first).
- **Places to watch** (`repeat.html`, in the header; "Station history" until 8 Nov 2026): the polling stations with a flag in more than one election, with an example read line by line and the notes on the method; a flag is a question, so the name says what the list is for, not what the places are. Filters: municipality (a municipality's page links here with `#m-<code>`, and the page links back), kind of flag, the same flag repeated, search.
- **Changes:** what changed after first publication, and each archived version of the file.
- **Guide for controllers and observers** (`guide.sr.html`, `guide.en.html`): the rules at a polling station from the handover of the materials before the vote to the handover after it — who is who on the board, the deadlines in one table, opening and the control sheet, the voting steps, voting outside the station, order, the count and the arithmetic that must hold, the minutes and remarks, remedies and their deadlines, what differs at local elections (Law on Local Elections 14/2022, 35/2024, 47/2026: the municipal or city commission instead of RIK, four copies of the minutes for lists, objections to the commission and appeals to the higher court, and the rules when local and national elections fall on the same day), and the crimes with their penalties. Every rule gives its article in the Law on the Election of Members of Parliament (14/2022, 47/2026) or the RIK document it comes from (the 2026 handbook for polling boards, the instruction on handovers). The arithmetic names the site's matching flags, and the practical part points to the station's page, the controllers per list and the list to check. It states the law the same way for every list; a party's own handbook is used only where the law or RIK confirms it.
- **About:** method, how often RIK is asked, the data and alerts (Atom feeds, the JSON under `api/` including each election's stations and the boundaries, the archive on GitHub), the checks, limits.

### Places across elections

Everything that follows a station across elections uses the same places (`places.py`): the search and the pages across elections, the turnout checks against an earlier election, the station history table and the private target list. Going forward in time, within its municipality, a station is joined to a station of an earlier election:

1. by a manual correction in `data/places.csv`, if a maintainer recorded one;
2. by address, where the decisions on polling boards gave one;
3. then by name (its telling words: "ОШ Вељко Петровић" and "Основна школа Вељко Петровић" are one name; a name made only of words like "school" tells nothing);
4. then by number. A number alone never joins two stations whose address or name clearly differs.

Stations that share an address or a name are paired by equal number first, and the rest in number order only when as many are left on each side (a renumbered building, not a co-op hall in several villages). Matching runs forward, so a new election never changes how earlier ones were joined.

`data/places.csv` corrects the rules by hand. Columns: `action` (`join`: the two stations are one place; `split`: they never are), `municipality_code`, `round`, `number`, `other_round`, `other_number`, `note` (why, with a source). Rows with a missing field are skipped.

Every page says which RIK timestamp the data comes from and when it was fetched. Charts are drawn as SVG when the site is built, so the site needs no JavaScript libraries.

**Settlement boundaries.** `izbori geo --settlements` (the geo workflow with the `settlements` switch) fetches Serbia's settlements from OpenStreetMap (administrative relations at admin_level 9 with the cadastre's `ref:RS:naselje`), simplifies them to about 35 m, finds each one's municipality by the municipal boundary its representative point falls in, matches its name to the census settlements of that municipality the way `settlements.py` matches RIK's names, and writes `data/geo/settlements.json` (ODbL, one feature per line). Unmatched boundaries stay in the file and draw grey. `izbori geo --quarters 89010=Нови Сад` (the workflow's `quarters` input with `commit`) keeps a city settlement's quarters from OpenStreetMap (place=quarter, then suburbs and neighbourhoods where no quarter is, clipped to the settlement, each piece of ground to the first drawn) in `data/geo/quarters.json`, with the names of the public buildings inside it (schools, kindergartens, community centres, local communities' halls) and the quarter each stands in — names only, no coordinates of buildings; without `commit`, `--quarters-inspect` only lists what OpenStreetMap has inside one settlement — local communities (admin_level 10) and named quarters — to see whether a city can be drawn by its quarters; it writes nothing.

**Incremental build.** `izbori site --incremental` keeps the previous build and renders again only the pages whose data changed. Each page's inputs are fingerprinted into `_site.state.json`; a change to the code, templates or packages rebuilds every page, and pages that no longer exist are removed, so the result is byte for byte a full build. The **pages** workflow keeps the previous build in the Actions cache. The three languages are written side by side, each in a process of its own (one after another on Windows, or with `IZBORI_SERIAL=1`). A full build takes about a minute, an incremental one after new data a fraction of that. The site is about 660 MB in about 40,000 files, and GitHub Pages allows 1 GB; the workflow log prints the size. To keep it small, repeated markup stays out of each row: the labels a phone shows in each cell come from one stylesheet, `static/labels.css`, written with the pages.

## Alerts

- **Atom feeds** (`feed.sr.xml`, `feed.en.xml`): one entry per fetch that adds flags.
- **Email digest:**
  - At most one message every 15 minutes, plus one when a count completes.
  - Sent from a neutral mailbox.
  - Recipient addresses live only in a GitHub secret. They are handed straight to the mail server and never appear in a header or the repository.

## Archive

```
data/rounds.json                  every round RIK lists
data/feed.json                    feed entries
data/places.csv                   manual corrections to how stations are followed across elections
data/settlements.csv              manual corrections to which census settlement a station is in
data/station_lists.csv            the commissions' decisions on polling stations found on the web (round, municipality, link)
data/municipal_sites.csv          each municipality's web site (the domain of its commission's e-mail in RIK's address book)
data/municipal_docs.json          links to the commissions' documents found on those sites by the watch workflow (link, municipality, kind, first seen)
data/elections.csv                election days entered by hand once an election is called
data/looks.json                   when RIK was last asked (results, settled rounds, daily re-download)
data/mail.json                    email state: pending flags, time of the last message
data/geo/municipalities.json      municipal boundaries by RIK's municipality code: OpenStreetMap (ODbL); Kosovo and
                                  Metohija in RIK's division from Glaurdić et al. 2021 (CC BY 4.0)
data/census/2022/sources.json     where each census table came from: address, title, SHA-256, size, first fetched
data/census/2022/settlements/     the 2022 census tables by settlement, as the Statistical Office (RZS) published them
data/census/2022/municipalities/  census tables by municipality and city: ethnicity, education, activity, migration
data/rounds/<id>/meta.json        type, title, English title, election day, contestants (name, short
                                  name, minority status), seat rules
data/rounds/<id>/results.csv      latest file exactly as downloaded; git history keeps every version
data/rounds/<id>/snapshots.jsonl  one line per distinct file: fetch time, RIK time, progress, SHA-256
data/rounds/<id>/changes.jsonl    one line per value that changed at a station after it had results
data/rounds/<id>/first_seen.json  when each station first had results in the archive
data/rounds/<id>/flags_seen.json  when each flag first appeared
data/rounds/<id>/state.json       RIK's progress at the last download
data/rounds/<id>/boards.json      decisions on polling boards: per decision, station, link, address, each list's member yes/no
data/rounds/<id>/documents.json   every document RIK lists per station: label, link, upload time (no names)
data/rounds/<id>/observers.json   per observers' record: how much is written in its remark lines (numbers only)
data/rounds/<id>/observer_reviews.csv  what a person found in observers' records (edited by hand)
data/rounds/<id>/settlements.json each station's settlement in the 2022 census: census municipality, settlement, rule
data/rounds/<id>/commission.json  the municipal electoral commissions' documents: link, kind, day; RIK's name of a
                                  city the results don't have
```

A parliamentary file has 8,392 stations and is 4.3 MB. Consecutive versions differ by a few rows, so git stores them as small deltas.

The archive starts with the three files from 1 November 2026 at 22:19, 23:26 and 23:29. They were downloaded from RIK by hand.

## Schedule

- **Every day.** The **documents** workflow reads RIK's register of minutes: daily for two weeks after election day, then on Mondays until 60 days after it, and each time only if a quick count (one or two requests per kind of document) shows something new. The **boards** workflow reads new decisions on polling boards until 14 days after election day, then joins the stations to their census settlements again. The **observers** workflow scores new observers' records of the newest round, once each, until 60 days after election day.
- **By the election calendar.** The **update** workflow starts every hour, but asks RIK only as often as the nearest election calls for (`src/izbori/schedule.py`):
  - no election under way: once a day, which also finds a newly called election in RIK's list of rounds;
  - election day: every 6 hours until two hours before the polls close, then every hour until two days after;
  - until 14 days after: every 3 hours, for late results, corrections and repeated votes;
  - a round RIK lists without a known election day: every hour on Sundays, when elections are held.

  Election days come from the archived results and from `data/elections.csv`, where a maintainer enters an election once it is called (`date`, `round` if RIK lists it yet, `kind`, `note`; the home page shows the next one, with its kind and note). Each look downloads a file only when the number of counted stations changed, and re-downloads every recent round once a day to catch silent corrections; rounds more than 30 days past their election day are looked at once a week. The time of the last look is kept in `data/looks.json`, so a run GitHub skipped (its schedule drops many hourly runs) doesn't delay the next look. A run started by hand always asks.
- **While a count is open.** The same run turns into a watch loop:
  - it checks RIK every 3 minutes;
  - it downloads when progress changes, and at least every 15 minutes in any case;
  - it commits, publishes and emails whenever there is something new;
  - it runs for up to 5¾ hours.

  It then starts the next run itself, rather than wait for GitHub's schedule, and Sunday evenings get extra scheduled runs. Only one runs at a time.
- **Keepalive.** GitHub turns off schedules in repositories with no activity for 60 days. The hourly run commits a small heartbeat file if nothing else has been committed for 30 days.

Requests to RIK stay small and identify the project in the User-Agent.

## Commands

```sh
uv sync
uv run izbori rounds                      # elections and rounds RIK offers
uv run izbori fetch 680072                # download one round now; archive if changed
uv run izbori import FILE.csv --round 680072 --kind parliamentary --contestants lists.json
uv run izbori update --watch              # what the hourly job runs
uv run izbori check 680072                # flag counts for one round
uv run izbori boards --round 680072       # controllers: read decisions on extended polling boards (needs tesseract)
uv run izbori documents --round 680072    # observers' records, remarks and rulings from RIK's register of minutes
uv run izbori observers --round 680072    # score observers' records with OCR (needs tesseract); numbers only
uv run izbori observers --review --html review.html   # the records to read, most written-in first
uv run izbori observers --merge observers-review.csv  # the rows filled in there, into observer_reviews.csv
uv run izbori observers --station 70017/50 --diagnose 1 --layout   # what OCR found in one record, names masked
uv run izbori site --out _site            # build the site
uv run izbori site --out _site --incremental   # render only what changed since the last build
uv run --with shapely izbori geo          # municipal boundaries from OpenStreetMap (the geo workflow, by hand)
uv run --with shapely --with pyshp izbori geo --kim   # Kosovo and Metohija in RIK's division, into the same file
uv run izbori census                      # the 2022 census tables from the Statistical Office (the census workflow, by hand)
uv run izbori settlements                 # each station's census settlement, every round (after the boards workflow too)
uv run izbori boards --round 680072 --reindex --retry-unparsed   # place and read every decision again
uv run izbori boards --round 680072 --only 71218 --reread   # read one municipality's decisions again
uv run izbori boards --round 680072 --diagnose-ids 744462   # how one decision reads every way, names masked
uv run izbori targets --out targets.csv --html targets.html   # private: never commit or post
uv run pytest
```

`update` also takes options used by the scheduled job:
- `--commit` and `--push` to save changes to the repository
- `--dispatch-pages` to start the site build
- `--notify` to send the email digest

## Layout

```
src/izbori/
  rik.py        RIK client: rounds, progress, CSV export
  load.py       CSV → stations, any election type
  model.py      stations, contestants, rounds
  contests.py   presidential majority, D'Hondt seats, margins
  checks.py     station flags and their weights
  history.py    the archive: snapshots, change log, first-seen times
  report.py     everything about one round, for the site, feeds and targets
  describe.py   one line per flag with its numbers, in each language
  stats.py      statistics for the whole round and per municipality
  places.py     the same polling place across elections: address, then name, then number
  documents.py  RIK's register of minutes: observers' records, remarks, rulings per station
  observers.py  observers' records: reviews by a person, and the OCR score that orders them
  schedule.py   when to ask RIK, by the election calendar
  commission.py the municipal electoral commissions' documents from RIK's register
  publishing.py what reached RIK for each municipality and when: the facts on the Commissions page
  narrative.py  the sentences at the top of the pages across elections
  geo.py        municipal boundaries for the Explore page's map: OpenStreetMap, and Kosovo and Metohija in RIK's division
  census.py     the 2022 census tables from the Statistical Office, archived as published
  settlements.py each station's settlement in the census: by address, name, the same place, or the seat; the
                settlements' figures (type, population 2011 and 2022, people aged 65 or more)
  bysettlement.py results and controllers by kind of settlement, for each election's Settlements page
  notes.py      news notes
  targets.py    private ranking
  feed.py       Atom feeds
  mail.py       email digest
  i18n.py       text, numbers and dates in three locales
  translit.py   Cyrillic → Latin
  site.py       static site builder, with templates/ and static/
data/           the archive
notes/          news notes per round, added by hand
tests/
```

Python 3.12+, managed with uv. Networking uses only the standard library; templates use Jinja2; Excel files are read with xlrd (RIK's older results) and openpyxl (the census).

## Data sources

Election data all come from `https://www.rik.parlament.gov.rs`:

| Request | Returns |
|---|---|
| `POST /get-elections/` with `election_type=N` | Rounds of that type (id → name). |
| `POST /get_results/` with the round id | Counted and total stations, RIK's timestamp, totals per contestant, whether download is allowed. |
| `POST /get-election` with the round id and type | RIK's register of minutes, ten stations per page: each station's documents with label, link and upload time. |
| `GET /export-results/{round}/2` | The results CSV, one row per station. It has registered voters, voters, ballots in the box, valid and invalid ballots, entry time, one column per contestant, and links to the minutes and any correction. Available only while RIK allows downloads. |

### Census 2022

The Statistical Office of the Republic of Serbia (RZS) publishes the 2022 census as Excel tables at `https://popis2022.stat.gov.rs/`. A polling station serves part of a settlement, and the census counts people by settlement, so the census can describe the place around each station. `izbori census` (the **census** workflow, started by hand) keeps the tables listed in `src/izbori/census.py` in `data/census/2022/`, exactly as published, and records in `sources.json` the address, SHA-256, size and first fetch time of each; a table is written again only if its content changed.
- **By settlement (7 tables):** population; age and sex; households by number of members; families by type; the population and the households at every census from 1948 to 2022; dwellings and their floor space.
- **By municipality and city (8 tables):** population; ethnicity; age and sex; educational attainment; computer literacy; migration; economic activity; educational attainment by type of settlement (urban or other) within the municipality. The census gives education, ethnicity, activity and migration no further down than this.

The census wasn't held in Kosovo and Metohija. The tables count people and hold no names. The Office's site is out of reach from the development sandbox; GitHub's runners reach it.

**The municipalities' sites** (`watch.py`, the weekly **watch** workflow, `izbori watch`). The law has local electoral commissions publish their acts on the web, mostly on the municipality's own site. `data/municipal_sites.csv` gives each municipality's site, taken from the domain of the commission's e-mail in RIK's address book of local commissions (21 use webmail; their sites are added by hand as they are found). The watch visits each site's front page, the pages it links to about elections or the commission, and the site's search for polling stations and polling boards, and keeps the links to .pdf/.doc/.docx documents whose link text or file name is about polling stations, polling boards or the commission — the link, the municipality, a kind told from keywords and the day first seen, never a title (it can name a person) or any text. A new decision on polling stations is logged as a line to add to `data/station_lists.csv`. This is the preparation for local elections, where every commission publishes on its own.

**Each station's settlement** (`settlements.py`). `izbori settlements` joins every round's stations to the census, the same way for every station, the first rule that answers deciding:
1. a manual correction in `data/settlements.csv`: "manual";
1a. the local electoral commission's decision on polling stations (the law has it give each station's number, name, address and area; `data/station_lists.csv` lists the acts found, `izbori stationlist` and the **stations** workflow read them — text layer, OCR or .docx — cut them into one row per station number and take the settlement a row names, when the row also looks like the station in the results): "list";
2. a settlement of the station's municipality named in the address read from its board decision, after the first part: "address";
3. named in the address's first part ("Дом културе Голубинци"): "building";
4. named in the station's name in the results: "station";
5. the municipality has a single settlement (Belgrade's urban city municipalities): "single";
6. the same polling place in another election (as on the pages across elections) found its settlement by one of the rules above: "place";
7. an address with a street or a house number that names no settlement: the settlement bearing the municipality's name, "Стара Пазова", "Младеновац (варош)" or "Београд (Вождовац)": "seat". This one is assumed, as a town's stations are usually given by building and street alone;
8. a row in `data/settlements.csv` with `*` for the number: the settlement the maintainer checked every station of the municipality that no rule above places is in (commissions that write a bare building name for the town's stations and the village's name for the rest): "rest". Checked by hand per municipality, never assumed.

Otherwise the station has none: unknown is not zero. Names are compared in Latin without diacritics, word by word, the longest first; a name the census qualifies in brackets is also found without them when that leaves no doubt ("Београд" in Voždovac is "Београд (Вождовац)"; "Младеновац" is the town rather than the village). An address that names another building than the results isn't used. The census prints names, not codes, in a hierarchy shown by indentation; RIK's municipalities are matched by name, a name in brackets saying which city ("Палилула (Ниш)"). Of 2026's 8,210 stations in places with a census, 7,556 have a settlement: 6,520 named or certain (address, building, station, single), 607 from another election and 429 assumed seats.

**The settlements' figures** (`settlements.load_figures`) are read from the archived tables when the site is built: RZS's type (urban or other), the population in 2011 and 2022 (table 4: "-" is none, "..." unknown, as for Preševo's and Bujanovac's settlements in 2011, which the 2011 census counted only as municipalities) and the people aged 65 or more (table 1). The Settlements page of each election and the census's measures on Explore use them.

`data/rounds/<id>/settlements.json` keeps, per station, the census municipality (`u`, its city before a colon for a city municipality: "Град Ниш: Палилула"), the settlement as the census prints it (`s`) and the rule (`m`). `data/settlements.csv` corrects it by hand, with the columns `round`, `municipality_code`, `number`, `settlement`, `note` (why, with a source); a row naming a settlement outside the station's municipality is skipped. The **boards** workflow joins again after it reads new decisions, since they give the addresses.

## Setup

1. **Pages:** in Settings → Pages, choose "GitHub Actions" as the source. Then run the **pages** workflow once (Actions → pages → Run workflow).
2. **Reaching RIK:** run the **probe** workflow by hand. It lists the rounds RIK offers and changes nothing.
   - If it fails to connect, RIK is blocking GitHub's servers.
   - Then run `uv run izbori update --watch --commit --push` on election night from a computer in Serbia.
3. **Email:** get a neutral sender mailbox with SMTP and add these repository secrets:
   - `SMTP_HOST`, `SMTP_PORT`
   - `SMTP_USER`, `SMTP_PASSWORD`
   - `MAIL_FROM`
   - `MAIL_TO` (comma-separated)
4. **New rounds:** the hourly job archives new rounds by itself. Then a person checks the round's `data/rounds/<id>/meta.json`:
   - `kind`, `title_en` and `date` (election day, filled in automatically from the first percent of minutes uploads, so a stray early upload doesn't move it)
   - for list elections, each list's `minority` status, taken from RIK's decisions, and then `"minority_checked": true` under `contest`. Until that is set, the site warns that seat numbers may be off.
   - for local elections, `contest.seats`, the size of the assembly
5. **Commits:** scheduled commits come from GitHub's bot identity. People who commit by hand should use their GitHub no-reply address.

## Tests

The tests use the archived 2026 files and small made-up files. They check that the tool:
- reproduces the final seat allocation (140, 103, 2, 2, 1, 1, 1) and the seat margins;
- flags every station from the manual review of 2 November 2026;
- catches the five "voted = registered" typing errors;
- detects changed numbers, replaced minutes, corrections with no change, and register and turnout jumps;
- leaves the flags unchanged when contestants' votes are swapped.

## Open items

- **RIK blocking requests on election night.** GitHub's servers reached RIK on 2 November 2026, but RIK could start blocking traffic from abroad under load. If it does, run `update --watch --commit --push` from a computer in Serbia. Nothing else changes.
- **Presidential format.** The round's type number and columns are known only once RIK lists the election. Check as soon as it appears.
- **Local elections, likely on the same day as the presidential one.**
  - RIK's system carried Belgrade's 2024 city vote. Other towns publish through their own commissions.
  - Next steps: check how Novi Sad, Niš and Kragujevac published in 2024, write readers for those towns first, then add the towns observer groups ask for.
  - Assembly sizes and seat rules go in each round's `meta.json`.
- **Older station data (2022–2024)** to compare the same stations across elections. RIK no longer serves 2023; the national open-data portal is next to check.

## License

MIT
