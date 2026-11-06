# Izborni podaci

A public site in Serbian (Latin and Cyrillic) and English. It saves every results file that Serbia's Republic Electoral Commission (RIK) publishes. It checks every polling station by the same rules, whoever the candidates and lists are. It shows observers and journalists where to look.

**Site:** https://izborni-podaci.github.io/izborna-analiza/

**Status:** first version, being tested.
- **Working:**
  - the RIK client
  - the archive and its change log
  - election math
  - station checks
  - news notes
  - the private target list
  - the site in three languages
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
| Minutes replaced | The link to the minutes changed. The link carries an upload stamp, so every replacement shows. | 2 |
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

Station pages, the lists to check and the JSON name each document by its kind. Remarks and the RG-8 and RG-9 rulings become flags (see [Station checks](#station-checks)); the observers' record is linked on every row, and the "In short" text says in which elections it exists. Remarks written by hand inside the observers' record become flags once a person has read them (see [Observers' records](#observers-records)).

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
or empty is kept for each list.

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

**Languages:** Serbian Latin (default), Serbian Cyrillic and English. Serbian text is written once in Cyrillic and converted to Latin automatically, as are RIK's names.

**Pages:**
- **Home:** the search, and under it the archive in numbers (elections, polling stations across elections, RIK documents the pages link to). Beside the search, only when a maintainer has entered the next election in `data/elections.csv`: its day, the days left and the deadlines still ahead (polling board nominations and appointments, domestic observers, the handover of materials, campaign silence), counted back from voting day as the law states them and linking to the guide; it disappears once the day has passed, and with no election ahead the space stays empty. Then six ways in: what's unusual, unusual more than once, a municipality across elections, the guide, controllers by list, and data and alerts.
- **Elections** (`elections.html`): every archived round, with its counting progress.
- **Municipalities** (`municipalities.html`): every municipality in Serbian alphabetical order (Latin or Cyrillic, by page), with how many elections it took part in, its polling stations at the latest one and a link to its electoral commission's documents; a filter finds one by name.
- **Explore** (`explore.html`): the reader's own analyses, computed in the browser by `static/explore.js` (no library, nothing from other servers) from `api/r/<id>/stations.json` and `api/geo/municipalities.json`.
  - Views: a map of municipalities with the municipalities ranked beside it; two measures against each other (for many stations' shares, a heat grid of counts: the election fingerprint); two elections (stations matched by place as on the pages across elections, municipalities by code, with the diagonal, the totals of both elections and the largest changes; a count such as a list's votes changes by a number and in per cent, either of which ranks the changes); a distribution; a table (a list's votes beside its share, and its share beside its votes); municipalities across elections.
  - Measures, the same for every list: turnout, invalid ballots, a chosen list's share, a chosen list's votes, the largest share of any list, registered voters, voters, signatures minus ballots in the box, flagged, whether a chosen list had a controller (member or deputy of the extended composition), the observers' record, hours from the polls closing to the upload of the station's first minutes (a median for a municipality). No list is ever chosen for the reader; after another election is picked, the reader chooses the list again.
  - Filters: municipality; stations in the country, abroad or in prisons; at least so many registered voters; flags (any, none, one group); a list's controller; the observers' record; a range of the measure. They apply to each election's own stations; the controller filter only to the chosen election, whose lists it names.
  - Ready-made analyses are plain links. Every analysis is in the address (`#v=…&r=…`), downloads as CSV (UTF-8 with a BOM, a link per row) and, for a chart, as SVG with its title and source. Clicking a cell, bar, point or municipality lists its stations.
  - The map's boundaries are OpenStreetMap's (ODbL, credited on the map), joined to RIK's municipalities by code; a city RIK counts by its city municipalities (Belgrade, Niš and others) isn't drawn over them. Kosovo and Metohija are drawn in RIK's division, which OpenStreetMap doesn't follow there, from Glaurdić et al. (2021, CC BY 4.0, credited on the map when drawn), as of 1999; the province's municipalities with no station in any archived election are grey and say so.
  - The map's seven classes each hold about as many municipalities, at round limits, so a few far values (the province's low turnout) don't squeeze the rest into two colours.
- **Round:** totals, results, seats or the majority, statistics for the whole round and per municipality, and municipalities.
- **Commissions** (`r/<id>/commissions.html`, `publishing.py`): per municipality in Serbia, what reached RIK for its stations and from its electoral commission, and when — stations whose minutes RIK published and how many hours after the polls closed the first came (median, and how many after 24 hours), rulings correcting the minutes, decisions on the standing and extended composition of the polling boards, the commission's own documents and its city commission's ("+ city's", see [Electoral commission documents](#electoral-commission-documents)), and stations whose numbers changed after publication. Hours come from the upload stamp RIK writes into every document's link; the register of minutes shows the same time for almost every document and, where it differs, a later one. No score: a cell is highlighted by absolute rules (something missing, a median over 12 hours, minutes after more than a day, changes), sortable, with the table as CSV (`api/r/<id>/commissions.csv`). Abroad and prisons are left out, as RIK runs those stations. A commission with no document isn't highlighted: a city municipality may have none of its own where its city's commission runs the vote.
- **To check:** every flagged station. Filter by municipality and flag type, or a whole group of flags (`#g-paper` and the like in the address). Each flag shows its rule, its numbers and RIK's minutes.
- **Municipality:** every station, with its numbers, flags, minutes and notes.
- **Municipality across elections** (`m/<code>.html`): one row per election it took part in, every election alike: stations, registered voters, turnout, invalid ballots, the top three contestants and the number of stations to check, each linking to that election. Then its polling stations, each linking to its own page.
- **Polling station across elections** (`s/<place>.html`, one for every station): one row per election with that election's number and name, the numbers, the top three, flags, notes and minutes.
- **In short:** both pages across elections open with short labelled rows written from the numbers (`narrative.py`): flags and invalid ballots, turnout and how it compares, who had most votes, how the place changed, and the observers' records. Each row has the main fact first and a line or two of context; the figures are the latest election's unless a line names another. A station is compared with its municipality, a municipality with the whole election. The same rules apply to every place and contestant; the rows state numbers and never judge them.
- **Charts across elections:** below the text, turnout and the share of invalid ballots per election, the place against the area it is compared with (dashed).
- **Search** on the home page finds a municipality or a polling station, by its current or a former number, and opens its page across elections.
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
  settlements.py each station's settlement in the census: by address, name, the same place, or the seat
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

**Each station's settlement** (`settlements.py`). `izbori settlements` joins every round's stations to the census, the same way for every station, the first rule that answers deciding:
1. a manual correction in `data/settlements.csv`: "manual";
2. a settlement of the station's municipality named in the address read from its board decision, after the first part: "address";
3. named in the address's first part ("Дом културе Голубинци"): "building";
4. named in the station's name in the results: "station";
5. the municipality has a single settlement (Belgrade's urban city municipalities): "single";
6. the same polling place in another election (as on the pages across elections) found its settlement by one of the rules above: "place";
7. an address with a street or a house number that names no settlement: the settlement bearing the municipality's name, "Стара Пазова", "Младеновац (варош)" or "Београд (Вождовац)": "seat". This one is assumed, as a town's stations are usually given by building and street alone.

Otherwise the station has none: unknown is not zero. Names are compared in Latin without diacritics, word by word, the longest first; a name the census qualifies in brackets is also found without them when that leaves no doubt ("Београд" in Voždovac is "Београд (Вождовац)"; "Младеновац" is the town rather than the village). An address that names another building than the results isn't used. The census prints names, not codes, in a hierarchy shown by indentation; RIK's municipalities are matched by name, a name in brackets saying which city ("Палилула (Ниш)"). Of 2026's 8,210 stations in places with a census, 7,556 have a settlement: 6,520 named or certain (address, building, station, single), 607 from another election and 429 assumed seats.

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
