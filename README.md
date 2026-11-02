# Izborni podaci

A public site in Serbian (Latin and Cyrillic) and English. It saves every results file that Serbia's Republic Electoral Commission (RIK) publishes. It checks every polling station by the same rules, whoever the candidates and lists are. It shows observers and journalists where to look.

**Site:** https://izborni-podaci.github.io/izborna-analiza/

**Status:** first version, in progress.
- **Working:**
  - the RIK client
  - the archive and its change log
  - election math
  - station checks
  - news notes
  - the private target list
  - tests on the 2026 parliamentary files
- **Next:** the site, feeds, email and scheduled jobs.

A Serbian version of this file (`README.sr.md`) will follow.

---

## Who it's for

- **Journalists:** what stood out, at which station, with the numbers and a link to RIK's own minutes.
- **Observer groups:** the same checks during the count, plus a private list of stations to watch next time.

## Principles

1. **Same rules for every contestant.** No party is hardcoded. Contestants appear in RIK's ballot order with neutral colours. A test swaps contestants' votes and checks that the flags don't change.
2. **A flag is a question, not a verdict.** Flags mean "unusual, check the minutes". The site never says "fraud".
3. **Flags come from primary sources only:** laws, RIK documents, ODIHR reports.
   - A news report about a specific polling station can be attached to it as a note, marked as unconfirmed.
   - A note never creates a flag or changes the ranking.
4. **No personal data.** RIK's results are station totals. The minutes carry board members' names and signatures, so the site links to them and never re-hosts or transcribes them.
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

Every check treats every contestant the same way. Stations are matched across elections by municipality code + station number.

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

**Unusual results.** Weak signals and often legitimate, e.g. bloc voting in minority areas. They cover stations in Serbia only, not abroad or in prisons.

| Flag | Rule (starting values) | Weight |
|---|---|---|
| Invalid-ballot spike | At least 8% invalid with at least 100 voters. Or at least 10 invalid, at least 4%, and at least 3× the median at the same address, or in the municipality if the station has its own address. | 2 |
| Register jump | Registered voters changed by at least 10% (and at least 20 voters) since the last election held at the same station. | 2 |
| Turnout jump | Turnout changed by at least 20 points more than it did across the stations both elections share. | 2 |
| Near-unanimity | Turnout at least 90% and one contestant with at least 80% of valid votes, with at least 50 registered. | 1 |
| Very high turnout | Turnout at least 90% with at least 50 registered, when near-unanimity doesn't apply. | 1 |

The two turnout checks skip stations flagged as a likely typing error.

**Context statistics.** These cover the whole round and are never station flags. They are computed for the two contestants with the most votes, whoever they are:
- last-digit test
- round percentages
- correlation between turnout and share
- turnout histogram

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
- **Overview:** every archived round, with its counting progress.
- **Round:** totals, results, seats or the majority, statistics for the whole round, and municipalities.
- **To check:** every flagged station. Filter by municipality and flag type. Each flag shows its rule, its numbers and RIK's minutes.
- **Municipality:** every station, with its numbers, flags, minutes and notes.
- **Changes:** what changed after first publication, and each archived version of the file.
- **Observer guide:** what's allowed at a polling station on election day, with article references.
- **About:** method, sources, limits.

Every page says which RIK timestamp the data comes from and when it was fetched. Charts are drawn as SVG when the site is built, so the site needs no JavaScript libraries.

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
data/mail.json                    email state: pending flags, time of the last message
data/rounds/<id>/meta.json        type, title, contestants (name, short name, minority status), seat rules
data/rounds/<id>/results.csv      latest file exactly as downloaded; git history keeps every version
data/rounds/<id>/snapshots.jsonl  one line per distinct file: fetch time, RIK time, progress, SHA-256
data/rounds/<id>/changes.jsonl    one line per value that changed at a station after it had results
data/rounds/<id>/first_seen.json  when each station first had results in the archive
data/rounds/<id>/flags_seen.json  when each flag first appeared
data/rounds/<id>/state.json       RIK's progress at the last download
```

A parliamentary file has 8,392 stations and is 4.3 MB. Consecutive versions differ by a few rows, so git stores them as small deltas.

The archive starts with the three files from 1 November 2026 at 22:19, 23:26 and 23:29. They were downloaded from RIK by hand.

## Schedule

- **Every hour.** A short run lists every round and checks its progress. It downloads a file only when the number of counted stations changed. Once a day it re-downloads every round, to catch silent corrections.
- **While a count is open.** The same run turns into a watch loop:
  - it checks RIK every 3 minutes;
  - it downloads when progress changes, and at least every 15 minutes in any case;
  - it commits, publishes and emails whenever there is something new;
  - it runs for up to 5¾ hours.

  The next hourly run takes over. Only one runs at a time.
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
uv run izbori site --out _site            # build the site
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
  stats.py      statistics for the whole round
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

Python 3.12+, managed with uv. Networking uses only the standard library; templates use Jinja2.

## Data sources

All from `https://www.rik.parlament.gov.rs`:

| Request | Returns |
|---|---|
| `POST /get-elections/` with `election_type=N` | Rounds of that type (id → name). |
| `POST /get_results/` with the round id | Counted and total stations, RIK's timestamp, totals per contestant, whether download is allowed. |
| `GET /export-results/{round}/2` | The results CSV, one row per station. It has registered voters, voters, ballots in the box, valid and invalid ballots, entry time, one column per contestant, and links to the minutes and any correction. Available only while RIK allows downloads. |

## Setup

1. Turn on Pages with "GitHub Actions" as the source.
2. For email, get a neutral sender mailbox with SMTP and add these repository secrets:
   - `SMTP_HOST`, `SMTP_PORT`
   - `SMTP_USER`, `SMTP_PASSWORD`
   - `MAIL_FROM`
   - `MAIL_TO` (comma-separated)
3. Scheduled commits come from GitHub's bot identity. People who commit by hand should use their GitHub no-reply address.

## Tests

The tests use the archived 2026 files and small made-up files. They check that the tool:
- reproduces the final seat allocation (140, 103, 2, 2, 1, 1, 1) and the seat margins;
- flags every station from the manual review of 2 November 2026;
- catches the five "voted = registered" typing errors;
- detects changed numbers, replaced minutes, corrections with no change, and register and turnout jumps;
- leaves the flags unchanged when contestants' votes are swapped.

## Open items

- **Can GitHub's servers reach RIK?** RIK may block requests from abroad, so this is the first thing to test. If it does, run `update --watch` from a computer in Serbia on election night. Nothing else changes.
- **Presidential format.** The round's type number and columns are known only once RIK lists the election. Check as soon as it appears.
- **Local elections, likely on the same day as the presidential one.**
  - RIK's system carried Belgrade's 2024 city vote. Other towns publish through their own commissions.
  - Next steps: check how Novi Sad, Niš and Kragujevac published in 2024, write readers for those towns first, then add the towns observer groups ask for.
  - Assembly sizes and seat rules go in each round's `meta.json`.
- **Older station data (2022–2024)** to compare the same stations across elections. RIK no longer serves 2023; the national open-data portal is next to check.

## License

MIT
