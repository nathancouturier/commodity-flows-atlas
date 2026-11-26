# Updating the data

How the scheduled updates work, what they do when something goes wrong, what GitHub e-mails, and the steps done by
hand. The owner's rule: scheduled updates must be robust and must never send failure e-mails; a real problem opens
one GitHub issue.

## The workflows

| Workflow | When (UTC) | What |
|---|---|---|
| `update-prices.yml` | Wednesdays 21:43, Thursdays 09:43 | World Bank Pink Sheet, EIA daily spot prices, freight indicators -> `data/prices` |
| `update-portwatch.yml` | Wednesdays 19:17 | IMF PortWatch chokepoint transits -> `data/freight/portwatch`; then the weekly port traffic -> `data/freight/port-traffic` (a second step of the same job, see "Port traffic" below); then the alert banners and the freight market digest (`data/freight/market-now.json`, no network, see "Freight market digest" below) |
| `update-annual.yml` | the 15th, 22:17 | USDA PSD, USGS MCS, EIA INTL, FAOSTAT and WNA (every 80 days), a check of the CEPII BACI version, then the rebuilds that depend on them |
| `check-staleness.yml` | Mondays 13:37 | compares each source with its cadence; opens "Data stale: <source>" |
| `watch-releases.yml` | the 3rd, 14:41 | compares the yearly pages read by hand with the release recorded; opens "New release available: <id>" |
| `ci.yml` | every pull request, by hand, and before each publication (called by `deploy.yml`); not on a push to a working branch | type check, node tests, data validators, Python unit suite, build and size budget |
| `deploy.yml` | every push to `main`, and after a data update | the checks of `ci.yml`, then the build and the publication on GitHub Pages; opens "Site not republished: a check failed" when a data update could not be published |

Every workflow can also be started by hand: Actions tab, select the workflow, "Run workflow".

## One writer at a time

The three update workflows share one concurrency group, `data-update`: a run waits for the one in progress. GitHub
keeps one waiting run per group; a newer one replaces it (the replaced run shows as cancelled, and the next scheduled
run does its work).

Each job commits only the paths it writes (`paths` in the workflow; a hand edit elsewhere in `data/` is never part of
it). When its push is refused because another commit arrived first, `.github/actions/finish-data-update/push.sh`
rebases it on the new tip without taking either side blindly:

- the status files `data/_status/updates.json` and `log.jsonl` are merged entry by entry and line by line by
  `pipeline/common/status.py merge-driver` (declared in `.gitattributes`): per source, the entry with the later
  attempt; every log line once, in time order. No status entry is lost;
- the digest built from them (`data/_status/changes.json`, `web/public/changes.atom`) is taken from the new tip and
  rebuilt on top of it with `pipeline/common/changes.py`;
- any other conflict (for example the owner edited the same data file during a long run) stops the rebase: nothing is
  forced. The run's data is dropped and, on top of the newer commit, a failure "update not pushed: conflict with a
  newer commit in <file>" is recorded for each source of the job and pushed alone (the status files merge as above).
  The next run does the update again, and the issue "Data update not pushed" opens (at once, because the job's
  `build-changes` step alerts at its first failure). The same happens when the push is refused five times.

**When a source is renamed in the registry** (`data/sources.json`, the field `name`): the digest and its feed store the names of
the sources that published, as text. Add the former name to `FORMER_NAMES` in `pipeline/common/changes.py` (former name, then the
id), run `.venv/bin/python -I pipeline/common/changes.py`, restore `data/_status/updates.json` and `log.jsonl`
(`git checkout -- data/_status/updates.json data/_status/log.jsonl`) and commit `data/_status/changes.json` and
`web/public/changes.atom` with the renaming. `pipeline/tests/test_changes.py` fails while a stored line starts with a name that
the registry no longer holds.

## When something fails

Every risky step is `continue-on-error`, so a data job always ends green. A failure is recorded in
`data/_status/updates.json` (per source: last attempt, last success, consecutive failures, last error) and turns into
an issue with the label `data-update` when it repeats:

| What | Recorded as | Issue |
|---|---|---|
| a source fails (download refused, file malformed, a column, commodity or series missing) | a failure of that source; the previous files are kept | "Data update failing: <source>" after 3 runs in a row for a weekly source, 2 for a monthly one |
| a build step fails (`build-freight`, `build-commodities`, `build-coverage`, ...) | a failure of the step; its previous outputs are restored (for `build-coverage`: the previous `data/coverage.json`; the other steps still run) | at the first failure (`build-market-now`: after 3 runs in a row, see "Freight market digest") |
| a step times out, crashes (an import error after a failed `pip install`) or is cancelled | the finish action records a failure for each source the step had begun and not recorded (`status.py interrupted`); when it had begun none, for each source it always runs | as above |
| the data checks refuse the result (`web/scripts/validate-data.mjs`, or `guard-data.mjs`: see "The before-and-after guard" below; the guard's coverage rule is one of them: a page that lost a block of `coverage_floor.json`, see "The coverage matrix") | the whole update is discarded, path by path; a failure of every source of the job, so that its builds run again. If the checks still fail after the discard, nothing is committed, not even the failure | one "Data update discarded by the data checks", with the output of the checks (at once when nothing could be committed) |
| the update cannot be pushed (a conflict with a newer commit, or a refused push) | the update is dropped; a failure of every source of the job, pushed alone | one "Data update not pushed" (at once when not even the failure could be pushed) |
| the site is not republished after a data update (a check of `ci.yml`, the build or the Pages deployment failed) | nothing: the data is on `main`, the site still shows the previous data | one "Site not republished: a check failed", with the run and the failed steps; closed by the next run that publishes |
| a watcher cannot run (`check-staleness.yml`, `watch-releases.yml`: Python, its dependency or its script failing) | nothing | one "Watcher failing: <workflow name>", closed when it runs again |
| a source stops being updated without failing (a disabled workflow, the same old file served again) | nothing | "Data stale: <source>" from the weekly staleness check, with the same rules as the site's "Data freshness" table |
| a newer release than the one in use (BACI, or a yearly page read by hand) | `state.available` of the source | "New release available: <id>", with the steps |

Each issue is updated at every run and closed automatically when the source recovers. Issues must be enabled for the
repository, and the owner must watch it to be notified.

### The before-and-after guard

`web/scripts/guard-data.mjs` compares each data file a job changed with its version in the last commit and refuses:

- a table (any list of 10 or more entries) that lost more than a tenth of its rows, a file of 1 kB or more that shrank
  to less than half, a folder of 10 or more files that lost more than a tenth of them;
- a price series whose shape broke: its frequency changed, its days are not one per value in increasing order, or a
  value of the last commit is gone (a hole, or a series that now ends earlier). This is the only test of the two
  series whose unit is a deviation (`igrea-m`, % deviation from trend; `gscpi-m`, standard deviations from average:
  the unit is read in `data/prices/index.json`): they cross zero, so a move is not proportional to their level, and
  their past months can be revised;
- a weekly port traffic file (`data/freight/port-traffic/<port id>.json`) that does not only grow: fewer weeks than in the
  last commit, a first week that moved, a last day of data that went back, a week older than the 52 weeks before the last
  stored week that is not the same (the weekly job reads again the last six weeks of every port and, in turn, 52 weeks of
  a quarter of the ports, and no older week), or a port file that is gone. The lists of `index.json` of that folder (the
  ports not read yet, the ports with no rows) shrink as the ports are read and are left out of the rows rule. A reading in
  full by hand (`--full`) that changes old weeks, or the first load, is a real move: accept it as below;
- for every other price series (a price or a positive index), a value of the previous last date revised by more than
  half, and, for a daily or monthly series, a new value that moves in one step further than the series itself has
  ever moved in one step: the range is ×0.5 to ×1.5 for a quiet series, widened to the largest one-step move of its
  history raised to the third power, and never wider than ×0.2 to ×5, so a value ten times too large or too small is
  always refused. Only steps between strictly positive values are tested (WTI's negative day of April 2020 and the
  zeros of one Pink Sheet rice series in 2008 are left out, not the whole series). Annual series are tested on
  revisions only: a yearly price can halve.

Replayed over the whole published history of the 138 series (every month, every week of the 8 daily series, every
year of the annual ones: 69,629 updates), the guard refuses 5 updates, each the first move of its size in the
series' history: four in the 1973-74 oil and fertiliser shocks (energy index, phosphate rock, TTF, Thai rice) and
Viet rice in June 2008, after a seven-month gap. The guard of the previous release refused 479 of the same updates:
363 of the 1,050 months of the two deviation series, 97 months of price series and 19 weeks of daily prices (14 of
them Henry Hub, among them the week of 23 January 2026, when the spot price rose from 3.06 to 30.72 USD/MMBtu). The
same real updates with their new values multiplied by 10, or by 0.1, are refused in all but 7 to 13 of 65,681 cases;
each of those adds the error to a real move the other way (×10 on a real fall to less than half, ×0.1 on a real rise
to more than double).

**A real move that the guard refused.** A price can move further than it ever has (a first shock of its kind), and a
rebuild can drop rows on purpose. After checking the change by hand, run the workflow by hand with "accept large
moves" ticked: the guard then reports the changes without refusing them.

The guard also reads one hand-typed file, for the coverage matrix: when `data/coverage.json` changed, a page that lost a
block that `pipeline/commodities/coverage_floor.json` lists is refused, by name ("page lithium lost the block price").
This rule is the guard's and not the validator's, so that the same "accept large moves" overrides it: a real loss (a
publisher dropped a table for good) is accepted by running the workflow by hand with that box ticked. A loss that the last
commit already holds is not refused again. See "The coverage matrix" below for what to do after accepting one.

## What GitHub e-mails

GitHub e-mails about a failed workflow run (with the default notification settings) to the person who triggered it;
for a scheduled run, to the person who last changed its schedule.

- **Data updates, staleness check, release watcher:** no e-mail in the normal course. Every step that can fail is
  allowed to; the run ends green, and the problem becomes an issue (GitHub e-mails new issues to the people who watch
  the repository). A data update that calls the deploy passes `soft: true`: a failed check, a failed build or a failed
  Pages deployment skips the publication without failing the run, and opens "Site not republished: a check failed".
  A watcher whose own script fails opens "Watcher failing: <workflow name>".
- **Still possible:** a failure of GitHub itself before the steps (a runner that does not start, the checkout or the
  Python and Node set-up of a data job failing; the watchers' Python set-up is allowed to fail), or a job that runs past its own
  time limit (the steps have shorter limits so that this should not happen). These runs are red and GitHub e-mails as
  usual.
- **A push to `main`:** the deploy runs the checks; a failed check, build or Pages deployment makes the run red and
  GitHub e-mails the person who pushed. This is GitHub's default for a failed deploy; nothing more is sent (no issue:
  the red run is the signal). A later run that publishes closes an open "Site not republished" issue.
- **Pull requests:** a failed check e-mails the person who pushed, as for any failed workflow. A push to another
  branch runs nothing.
- **Cancelled runs** (a waiting run replaced by a newer one in the `data-update` group) are not failures.

## Reports from visitors

The "Report an error" button in the header of every page, and the link of the same name in the About window (twice),
open GitHub's new-issue form of this repository (`.github/ISSUE_TEMPLATE/report-an-error.yml`), filled in by the
browser with the address of the page, what is selected on it, the page's heading and the release. The site sends
nothing to GitHub before the click. A GitHub account is needed to submit: the form is GitHub's.

- **Where they arrive.** As ordinary issues, titled "Error: <page>", which GitHub e-mails to the people who watch
  the repository. A report is not a failed job and no job reads it: the jobs find their own issues by the label
  `data-update` and an exact title, and a report carries neither.
- **No label.** The form has no `labels:` key and the address never carries `labels=` (GitHub answers 404 to a visitor
  who may not label), because the repository has no label for reports and none is created for them. The label
  `data-update` is the jobs' and is never used for a report. `pipeline/tests/test_governance.py` fails if the form
  names a label.
- **No promise.** Nobody promises a delay of answer, and nothing answers, labels or closes a report by itself: the
  owner reads the reports and closes the issues.

## The coverage matrix

`data/coverage.json` says which of eleven blocks (production, reserves, consumption, trade, lanes, routes, price, assets,
companies, and for the families that have them monthly series and the crop balance) each commodity page has. The annual
job rebuilds it with the step `build-coverage` (`pipeline/commodities/build_coverage.py`), after the pages and before the
country profiles, whenever a step before it ran or its own last run failed. It reads only tracked files, so it needs no
download. Two hand-typed tables sit beside it: `coverage_reasons.json` (why a block a page lacks is not applicable to
it, or not available for free) and `coverage_floor.json` (the blocks each page has had). **A typed reason never stops
an update and a failed step keeps the previous file; one rule refuses an update, the guard's: a page that loses a block it
had (third bullet)**:

- **A reason that the data now contradict** (a table appeared for a block typed as not applicable): the data win. The
  cell is written as present and the run shows a warning ("stale reason: wheat/reserves is present now, the reason ... is
  not used"). Nothing fails. Remove the reason from `coverage_reasons.json` by hand afterwards, then run the builder. The
  Python test of it (`test_no_reason_sits_on_a_block_that_is_present`) fails in the checks of a push or a pull request and
  only warns in the checks of a scheduled update (`COVERAGE_CHECKS=warn`, set by `ci.yml` when it is called with `soft`),
  as do the other tests that compare the committed file with the data.
- **A step that fails** (a page or block named in a table that does not exist, a file that is not in its shape): the previous
  `data/coverage.json` is restored, the failure is recorded as `build-coverage` and opens one issue at the first failure,
  because the same tables would fail the same way next month. The pages, prices and other steps are built and published
  as usual. The step checks the shape of its own file (`web/scripts/validate-coverage.mjs`) so that the data validator,
  which has no override, never refuses a whole update for a coverage file.
- **A page that lost a block it had**: the guard refuses the whole update of that run, every path of the job and not only
  `data/coverage.json` (see "The before-and-after guard"): the previous data is kept and the site is unchanged. One "Data
  update discarded by the data checks" opens, naming the page and the block. The next run of the annual job is refused the
  same way until someone acts, because the committed file still shows the block. Two ways out: run the workflow by hand with
  "accept large moves" ticked, if the loss is real (the matrix then shows the block as missing), and afterwards lower the
  floor by hand, deleting the block from its page in `pipeline/commodities/coverage_floor.json` in a commit that says
  why; or restore the block in the data. Until the floor is lowered the Python test `test_no_page_has_lost_a_block` fails
  in the checks of a push or a pull request. The guard compares the rebuilt file with the floor and with the file of the
  last commit, and `data/coverage.json` is rebuilt only by the annual job: a block that another job took from a page
  (the weekly prices job dropping the only price series of a commodity, for example) is seen by the annual job only, at
  its next run, and that run is refused although it did not cause the loss.
- **Raising the floor.** After a page gains a block, run `.venv/bin/python -I pipeline/commodities/build_coverage.py
  --raise-floor`: it adds the blocks present now to the floor and never removes one. Commit the file with the page.
- **A release.** The file carries the release number of `release.json`: after a bump, rebuild it (`build_coverage.py`), or
  `test_it_carries_the_release_and_no_time_of_day` fails. The number is the last release, not the date of the data.

## Keeping the schedules alive

GitHub disables the scheduled workflows of a public repository after 60 days without activity in it. **This is an
assumption, not yet seen on GitHub:** the data commits that the weekly jobs push with the workflow token
(`github-actions[bot]`) are expected to count as that activity, so that the schedules stay on as long as the jobs
commit. GitHub documents the rule only as "no repository activity", and a weekly run can also end without a commit
(nothing new published). If the commits do not count, or the jobs stop committing for two months, GitHub disables all
the schedules together, the staleness check included, and nothing reports it: the check opens "Scheduled workflows
disabled by GitHub" only while it still runs itself.

**What the owner should look at once, about two months after the first scheduled runs (late January 2027):** the
Actions tab, list of workflows on the left. A workflow disabled by GitHub is marked as disabled, with a banner on its
page. If one is, enable it ("Enable workflow"), run it once by hand, and keep the schedules alive by some activity of
your own in the repository at least every 60 days (a commit, for example). If none is, the assumption holds.

## Yearly refresh by hand

### CEPII BACI (once a year, usually January)

The BACI archive is 2.4 GB and CEPII has refused a cloud runner. The monthly job therefore only reads the version
CEPII lists (`update_annual.py --baci-check-only`); when it is newer than the one in use, the status of `baci` records
it as `available` and the issue "New release available: baci" opens. Then, on a local machine with about 6 GB free
and the Python environment of the repository (`.venv`, see below), from the repository root:

```bash
.venv/bin/python pipeline/annual/update_annual.py --only baci
node web/scripts/validate-data.mjs
.venv/bin/python -m unittest discover -s pipeline/tests -p "test_*.py"
git add pipeline/cache data
git commit -m "data: CEPII BACI <version>"
git push
```

The first command downloads the archive into `raw/baci/` (resumable), reduces it into `pipeline/cache/`, and rebuilds
what depends on it (borders, lanes, routes and chokepoints, alert banners, commodity pages, country profiles); the
version is recorded in `data/_status/updates.json` and the issue closes at the next monthly run. If CEPII refuses the
download from your machine too, download the archive by hand from the BACI page
(http://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37), put it in `raw/baci/`, and run the same command:
a complete archive already on disk is not downloaded again.

### Pages read by hand

`pipeline/common/release_watch.json` lists the yearly pages whose figures are entered by hand and the release each
was read at: the EIA World Oil Transit Chokepoints page, the GIIGNL annual report, the WNA uranium table. When the
monthly watcher sees a new date or file, its issue lists the steps; set `known` to the new value once the figures are
updated, and the issue closes. Not watched, because there is no fixed page to watch: the Panama Canal Authority's
fiscal-year results (a new press release each year, after the fiscal year ends on 30 September) and the Baltic
Exchange route changes (circulars). Look for them each autumn.

The standard-vessel figures (speed and fuel a day, laden and in ballast, in the `std` of each class of
`pipeline/freight/vessel_classes.json`, copied into `data/freight/vessel-classes.json` by `build_freight.py`) are read by hand,
from the Baltic Exchange's dry services page for the dry classes and from its Guide to Market Benchmarks for tankers and gas
carriers. Nothing watches them. Re-read them each January, with the circulars, and whenever a circular changes a standard vessel
(the Capesize vessel moved to 182,000 dwt on 2 January 2026): the figure, its year (`std.y`) and the sentence of `std.n`. The class
page states them, and the voyage calculator of the route pages (`web/src/lib/voyage.ts`) starts its speed and fuel fields from
them, so a changed figure moves the defaults of the calculator at the next build. `node web/scripts/validate-freight.mjs` fails
a standard vessel that gives the speed or the fuel for one leg only, or whose `bench` names a class that has none.

### At each release: the routes and lanes that stay

A generated route and a main lane of the last release are never put out by a cap: they stay while their corridor or their pair still exists in the
data (`pipeline/freight/generated_routes.py`, `pipeline/freight/build_lanes.py`; METHODOLOGY, section 3). The builders read the ids of what the last release
published from `pipeline/freight/released_ids.json`, which a release writes from the files it publishes. At each release, once the site is published (or on the
commit that is published), from the repository root:

```bash
.venv/bin/python -I pipeline/freight/release_ids.py                  # from data/freight/routes.json and data/freight/lanes/*.json as they are
.venv/bin/python -I pipeline/freight/release_ids.py --ref <commit>   # or from the files of a commit
git add pipeline/freight/released_ids.json
```

Run it on the files that are published, not on a rebuild that is not: the file is what the next rebuild keeps. A route or a lane whose corridor or pair has left the data
since the last release leaves the atlas: `pipeline/freight/QA_routes.md` lists the routes that ended, and the two tests that hold the lists
(`test_fncf.py`, `test_lanes.py` S07b) fail until each one is written in their `ENDED_SINCE_RELEASE` table with its reason.

### Metallurgical coal by pair of countries (by hand, when the Queensland file or EIA's coal file is newer)

The Main flows block of the Metallurgical coal page reads `pipeline/cache/metcoal_pairs.csv`, `metcoal_ports.csv` and
`metcoal_meta.json`, which no scheduled job refreshes and no staleness entry watches. The page refuses to be built for a
customs year that the cache does not hold (`pipeline/trade/metcoal.py` raises), so a new BACI year stops the commodity
build until the cache is renewed. The page prints the dates of the two files; they come from the meta file, so that the page never prints a date the
files do not have. From the repository root, with `raw/` on disk:

1. **Queensland.** Download the workbook "Quarterly Coal Sales" of the dataset "Quarterly coal reports"
   (<https://www.data.qld.gov.au/dataset/quarterly-coal-reports>) in a browser (the site refuses scripts) and put it in
   `raw/australia/queensland-sales/coal-sales-data-2010-2026.xlsx` (the extractor reads that name: change `RAW_QLD` in
   `pipeline/trade/extract_metcoal.py` when the file is renamed). The extractor reads the dates, the credit line and the disclaimer
   from the workbook's About sheet; nothing is typed.
2. **United States.** Download <https://www.eia.gov/opendata/bulk/COAL.zip> into `raw/eia/coal/COAL.zip`. Read the site's robots file
   first; one request, no more. The zip holds no date: write the `Last-Modified` date of the file in `EIA_FILE_DATE` of
   `pipeline/trade/extract_metcoal.py` (the one constant a person must change at each download).
3. **Extract.** `.venv/bin/python -I pipeline/trade/extract_metcoal.py`. It stops when a destination is not a country of the atlas, when Queensland's
   country and port sheets differ by a tonne in 2022 or later, when EIA's destinations or districts do not add to its world row within 0.5%,
   or when a 2024 total is more than 2% from the one the page notes were written for (`GUARD_2024` in the same file). Queensland says that its data may be
   revised and EIA that the latest year is preliminary, so a smaller difference is not a stop: it is printed and written to the meta file
   (`guard_2024`). A stop beyond 2% is more likely a changed definition (a coal type or a rank that moved in the file) than a revision: the message says what to look at; if the new
   figure is right, change `GUARD_2024` and say why in the commit. With a file missing, the extractor leaves that source's rows as they are.
4. **What a refresh still makes a person write.** The tests of `test_metcoal.py` compare the dates, the years and the file name with the meta file, and keep a
   typed value only where it guards a definition (the credit line of the About sheet, `GUARD_2024`, the first year read, PCI counted with the coking coals); a new
   file therefore breaks a test only through something that must be written by hand:
   - the dates of the two files, typed in the paragraphs of `NOTICE.md` on the Queensland Government and on the EIA coal exports ("Data through to ..." and
     "Current as at ...", "file dated ...") and in the last sentence of the metallurgical coal paragraph of METHODOLOGY.md, section 10:
     `test_no_page_prints_a_date_the_files_do_not_have` fails while any of them differs from the meta file;
   - the figures that METHODOLOGY.md, section 10, types for the layer (the two totals and their numbers of countries, the 63 rows, Singapore, India, the break
     of 2022, the coverage against EIA International): `MethodologyFigures` of `test_metcoal.py` fails while one differs from the cache or from the notes of
     the page. Australia's own figure for thermal coal to India (3.78 Mt, table 41 of the Resources and Energy Quarterly) is read from the workbook in `raw/`
     when it is there; the test skips itself without it;
   - `EIA_FILE_DATE` and, when the workbook is renamed, `RAW_QLD` in `pipeline/trade/extract_metcoal.py` (steps 1 and 2), and `GUARD_2024` when the extractor stops beyond 2%.
   The registry's `update`, `access` and `use` text of the two sources (`DATA_SOURCES.md`, the file name, the dates) is built from the meta file by
   `build_commodities.py` and replaces the text already in `data/sources.json`.
5. **Rebuild and check.** `.venv/bin/python -I pipeline/commodities/build_commodities.py`, then `pipeline/common/sources_table.py` and
   `pipeline/common/notice_lists.py` (they rewrite `DATA_SOURCES.md` and the lists of `NOTICE.md`), `node web/scripts/validate-data.mjs`, and the unit suite.
   The words that describe each source under the block ("by destination as the file gives it", "by destination country") come from the definition in
   the meta file, and the test of the definitions reads it there.

### World Port Index (by hand, when a newer file is downloaded)

The "World Port Index" block of the port pages reads `data/infrastructure/wpi.json`, which is built from
`pipeline/cache/wpi_ports.csv` and `pipeline/cache/wpi_meta.json`. No scheduled job refreshes them, no staleness entry
watches them, and no script downloads the file: the publisher's site (msi.nga.mil) answered HTTP 503 to every request of 22 to 25 November 2026, its
robots file answered with its maintenance page, and the pipeline never asks it for anything. Look for a newer edition each autumn, as for
the Panama and Baltic pages. When the site is down, nothing is needed: the three files are in git and the site keeps the last block.
The cache, the meta and `wpi.json` are one unit and are committed together; the terms of the file are not settled
(`NOTICE.md`), so a change of the terms holds back all three, not `wpi.json` alone. What was done the first time: on 24 November 2026
the publisher's site was in maintenance, and the owner took the file by hand from the Internet Archive's copy, captured on 29 September
2026, of the publisher's download address (written down in the hand-over note kept under `raw/`, which is not tracked, with the file's hash, which the meta file also holds). The
file holds no date inside it, so `CAPTURED` and `CAPTURED_FROM` say which copy it is. From the repository root:

1. **Read the page, then download.** In a browser open <https://msi.nga.mil/Publications/WPI> and read what it says of the
   edition, the date and the terms of use. Download the CSV into `raw/nga/UpdatedPub150.csv`, keeping the old file aside until the checks pass
   (`raw/` is not tracked). Only when the publisher's site does not answer, take the Internet Archive's copy of its download address, and
   record which you took. The file holds neither an edition nor a date inside it.
2. **Type what the page says**, in the constants at the head of `pipeline/infrastructure/extract_wpi.py`: `DOWNLOADED` (the day taken),
   `CAPTURED` and `CAPTURED_FROM` (the day the Internet Archive captured the address and the archived address, both `None` when the file
   comes from the publisher itself; with a capture date the source line of the page reads "Internet Archive copy of <day>" in place of
   "read <month>"), `EDITION` and `EDITION_PAGE` (the edition as the page states it, and its address; when `EDITION` is typed the source line of the
   page prints it in place of "read <month>"), and `TERMS_QUOTE`, `TERMS_PAGE`, `TERMS_READ_ON` and `TERMS_SCOPE` when the page states the
   terms of the file (quote the sentence, with its address and the day read). The extractor does not write the registry: change the `licence` text of the
   entry `nga-wpi` of `data/sources.json` by hand, run `pipeline/common/sources_table.py`, and edit the NOTICE.md bullet on the World Port Index. `Registry` and
   `Documents` of `test_wpi.py` fail while the quoted sentence, its address or the day read differ between the constants, the registry and NOTICE.md; they
   also pin the words that say the sentence is on the 2017 edition and not on the file, which are edited by the person who has read the page. Write nothing
   that the page does not say, and take nothing about what may be done with the figures from the statement on another edition.
3. **Extract.** `.venv/bin/python -I pipeline/infrastructure/extract_wpi.py`. It stops, writes nothing and leaves both cache files as they were when a
   column of the 23 it reads is missing from the header, a value is not a number or is negative, a position is off the globe, a class is unknown, a row of
   its review table is gone from the file, or a published row is of another country. It stops unless `--accept` is given when the file has fewer than
   95% of the rows of the last one, more than 5 ports fewer are published, or more than 20% of the ports kept show a figure that moved by more than 25% (a re-coded
   scale). Read its message, and its report (ports gained and lost, rows changed, the counts, the ports whose maximum vessel is held back); run it again with
   `--accept` only when the change is real. Two stops come before all the others, on their own, and `--accept` does not pass them: the file is not
   the one of the meta file and `DOWNLOADED` (or `CAPTURED`, when it is not `None`) is still the meta file's (the date of the new file was not typed;
   the message names the constant to edit); and the eight digits of `CAPTURED` are not in `CAPTURED_FROM`, or one of the two is `None` and not the
   other (the archived address says the day it was captured). Without the raw file it prints one line and does nothing.
4. **Look at what moved.** A port that fell out of the matches, a port in `doubtful` in the meta whose reason is "another row is nearer", and a promotion of the
   review table (`REVIEW`, each with a sentence written after opening the two rows, and a position check that stops the run) are to be read by a person: open the
   two rows again before keeping a promotion, and leave a match doubtful when it cannot be checked.
5. **Build and check.** `.venv/bin/python -I pipeline/infrastructure/wpi_limits.py`, then `node web/scripts/validate-data.mjs`, `node web/scripts/validate-infra.mjs`,
   `cd web && npx tsc --noEmit && npm test`, and `.venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_wpi.py"`.
6. **What a refresh still makes a person write.** The counts that METHODOLOGY.md, section 11, quotes (the ports with an entry and how they were matched, the doubtful,
   the ports without a match, the ports whose maximum vessel is held back, the doubtful ports with a nearer row, and the columns and rows of the file) and
   the figures of the paragraph on Port Hedland: `Documents` of `test_wpi.py` fails while one differs from the meta file or the data. The same test fails
   when the sentence that NOTICE.md quotes differs from `TERMS_QUOTE` and `TERMS_PAGE`, or when this section names a constant that the extractor no longer has. The registry's
   `access` text names the 23 columns by test.
7. **Commit the three files together** (`pipeline/cache/wpi_ports.csv`, `pipeline/cache/wpi_meta.json`, `data/infrastructure/wpi.json`), never one alone.

Where `raw/` does not exist (a fresh clone, the runners of GitHub), the match rule, the review table and the equality of the cache with the raw file
are not tested: those tests skip themselves, and a change to the rule is therefore proved only on a machine that has the file. The tests that run without it
check the cache, the meta file, the builder and the data file against each other.

### Place names on the map (by hand, when Natural Earth publishes a new version)

The names of the oceans, seas, bays and gulfs on the map are `data/geo/seas.json`, built by `pipeline/geo/build_seas.mjs` from Natural Earth's
marine areas 1:50m (registry entry `naturalearth-marine`); the names of the countries are read from `data/countries/index.json`, which
`pipeline/geo/build_countries.mjs` builds from the same publisher's countries file. Nothing is scheduled: no workflow, no status entry and no
staleness entry reads the files, the zip is read once by hand, and Natural Earth moves by years (the marine areas file is version 5.1.0). The
builder writes only on a machine that has the shapefile (`raw/` is not tracked); on GitHub's runners and in a fresh clone it prints one line and
leaves the tracked file as it is. When Natural Earth publishes a new version, from the repository root:

1. **Read the terms again, then copy.** Open <https://www.naturalearthdata.com/about/terms-of-use/> and the download page
   <https://www.naturalearthdata.com/downloads/50m-physical-vectors/>. Copy the sentences that `NOTICE.md` quotes (the bullet on Natural Earth) from the
   page, word for word, into `NOTICE.md` and into `pipeline/tests/fixtures/naturalearth_terms_quotations.json`, with the day you read them; change a sentence
   that the page no longer says and say nothing the page does not say. `test_naturalearth_marine.py` fails while `NOTICE.md` and the fixture differ.
2. **Download the zip** of the marine areas 1:50m into `raw/naturalearth/ne_50m_marine/` and unzip it there (`raw/` is not tracked), keeping the old
   folder aside until the checks pass. Read the README in the zip.
3. **Run the builder.** `node pipeline/geo/build_seas.mjs`. It takes the version for the note of the file from `ne_50m_geography_marine_polys.VERSION.txt` and the day
   from the constant `READ_ON` at the head of the script, which you edit to the day you read the zip and the terms page. A second run changes no byte.
   It stops, writes nothing and exits 1 when a field it reads (`name`, `name_en`, `featurecla`, `scalerank`) is missing, when it would write
   fewer than 60 names, when a name holds a bracket or comes twice, or when the new file would hold fewer names than the tracked one (`--accept-fewer`
   overrides the last one, once you have read which names went). Read its report and compare the names with the old file; a name that changed is a
   change on the map.
4. **Rebuild the lettering if a character appeared** in a name: `node pipeline/geo/build_glyphs.mjs` (the builder of the map's glyph file, which takes its characters
   from the names; see "The glyph file of the lettering" below).
5. **Check.** `node web/scripts/validate-data.mjs` (its rules for `data/geo/seas.json` and for the country index are in `web/scripts/validate-labels.mjs`: a sea
   named like a passage of `data/freight/chokepoints.json` is refused, since the atlas draws its passages as markers), `cd web && npx tsc --noEmit && npm test`,
   `.venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_naturalearth_marine.py"` and `.venv/bin/python -I pipeline/common/sources_table.py --check`.
   If the version changed, edit the `name` of the entry `naturalearth-marine` in `data/sources.json` and run `.venv/bin/python -I pipeline/common/sources_table.py`.
6. **Commit** `data/geo/seas.json` together with the glyph file if it was rebuilt, and the notice, the fixture and the registry if they changed.

When a source is down or changes shape there is no run to fail: the files are in git and the site keeps its last names. The builder never replaces
the tracked file with a smaller one without `--accept-fewer`.

**The glyph file of the lettering** (`web/public/glyphs/inter-medium/0-255.pbf`, with `LICENSE.txt` next to it). MapLibre draws the names from
signed-distance bitmaps of the characters, served by the site itself (no outside font server). `pipeline/geo/build_glyphs.mjs` builds the file from
the font Inter Medium, which is not tracked: it is the file `Inter-Medium.otf` of the Debian package `fonts-inter` (installed at
`/usr/share/fonts/opentype/inter/Inter-Medium.otf`; read the version with `dpkg -s fonts-inter`, 4.0+ds-1 when the file was built, and the file's sha256 with
`sha256sum`, `1e65171f...97ba`). Copy it to `raw/fonts/Inter-Medium.otf` (`raw/` is not tracked) and run, from the repository root,
`node pipeline/geo/build_glyphs.mjs`. The builder prints the font's own strings (copyright, licence, trademark, version): `LICENSE.txt` and the
Inter entries of `NOTICE.md` and `THIRD-PARTY-NOTICES.md` are written from them, by hand, so compare them after a new font version, and the builder
stops, writing nothing, when the font no longer states the SIL Open Font License 1.1 or when the `LICENSE.txt` in the output folder does not hold the font's copyright
line. Without the font file it prints one line and leaves the tracked file as it is, which is what GitHub's runners and a fresh clone do.

The characters are not typed: printable ASCII, and every other character found in the `name` of the rows of `data/countries/index.json`, in the names of the
point features of `data/infrastructure/*.geojson` once the places in brackets at their end are dropped (`assetLabel` of `web/src/map/labelRules.ts`), and in the
sea names of `data/geo/seas.json` in upper case. The file is therefore rebuilt only when a character appears or a name changes, and the check comes first:
`web/scripts/glyphs.test.mjs` fails ("no glyph for ...") on a name with a character the file does not hold, and says so in the run of `cd web && npm test`; the
builder itself stops on a character above U+00FF (one range file, `0-255`; a second one is not built). The same test also fails when a character leaves the
data (a name rewritten without the last use of an accented letter): its message names the character, and the way out is the same run of the builder, which
needs the font. A run changes no byte if nothing changed, and
`glyphs.test.mjs` compares the tracked file with a run to a temporary folder wherever `raw/fonts/Inter-Medium.otf` exists. The size budget of the glyph files
(`glyphs` in `web/scripts/check-size.mjs`) is checked on the built site. Nothing is scheduled and no workflow runs the builder.

`pipeline/geo/build_glyphs.mjs` imports `fontkit` and `pbf` from `web/node_modules`; they are not dependencies of the atlas but of `mapshaper` and of
`maplibre-gl`. If an upgrade drops one the builder fails when run by hand and nothing else does; writing the protocol buffer without `pbf` is about fifteen lines.
It was written for this atlas and compared with no other glyph tool; its output was looked at, character by character, in MapLibre (a test page with every
character at 9 to 40 px on the land and the ocean colours, and a name anchored at its centre: the `top` of a glyph is written from the ascender line, because
the library's layout reads it so; written from the baseline the names sat about one em above their point).

### Port traffic: the weekly step, the first load in sittings, and `index.json`

`data/freight/port-traffic/` holds one weekly file per PortWatch port (`<port id>.json`) and `index.json`. The ports are the `portwatch`
ids of `data/infrastructure/ports.geojson`; the files come from `pipeline/freight/fetch_portwatch_port_traffic.py`, which asks the data service
for the daily rows of the ports, keeps none of them and writes only the weekly sums (NOTICE.md). The owner's rule for PortWatch
(25 November 2026) is small pieces, one request at a time, slowly; the pauses in seconds (8 to 14 between two requests) are the script's reading of
"slowly" (the chokepoint script's, imported: one place), never the owner's figure.

**The weekly step.** `update-portwatch.yml` runs the script as its second step, after the chokepoint step and before the alert banners
(`continue-on-error`, 15 minutes; the job's own limit is the sum of the limits of its steps plus 15, a test keeps it so). The step is
independent of the chokepoint step: the finish step records each source on its own, and a step that fails, or is stopped by its limit,
records a failure for `portwatch-port-traffic` alone while the chokepoint files are committed. What one run asks for, counted by the plan
itself (`--dry-run` prints it, a test ties the figures below to `portwatch_ports.py` and the script):

- the last six weeks of every port that has a file (the window, PortWatch revises its recent days) and, instead of the window, the last 52
  weeks of one quarter of the ports (the ports in their fixed order, the quarter chosen by the week: every port is read over a year once
  every four weeks, never all together);
- at most five ports without a file, each read in full (3 requests: the table holds fewer than 3,000 days of a port, a fourth request comes
  when it passes that), a port that returned no rows only in the week of its quarter;
- the requests, 18 ports at a time, in pages of 1,000 rows (a page that is full is followed by one more request, so the count is an upper
  bound of the rows; 18 is the most ports whose window of a normal week, at most 55 days, is fewer than 1,000 rows, one page, and no size
  from 1 to 20 asks for fewer requests in a normal week): **23 requests** in a normal week (every port has a file, as the run of the week
  before left it, the table ends 0 to 9 days before the run and has gained one complete week since the run before, whatever the quarter), and
  **never more than 42**, not counting a request repeated after an error: the plan keeps to that, whatever state the files are in (a service
  that was down for weeks leaves the files late and the run asks for more days). A table that gains two or more complete weeks between two
  runs (it ended on a Saturday or earlier at the run before and ends on a Sunday or later now, PortWatch skips a week, or it is the first run
  after the files of the first load) makes the window of a full request more than one page of 1,000 rows, and the run asks for 29 requests;
  after one missed week 29 to 31, after two 31 to 32, after three 31 to 33. The first scheduled run (Wednesday 2 December 2026, the files
  ending with the week of 9 to 15 November 2026) asks for 23 requests if the table then ends on or before Saturday 28 November, 29 if it ends
  on Sunday 29 November or later. When the late files would need more, the ports whose files end earliest are
  read first and the others wait for the next run (the run says which); the ports without a file take what is left, each at its pages and one
  request more (the check that a port whose file ends weeks before the others is late in the service), so a run near its bound reads fewer
  than five. 42 is the figure for the pace: at 14 seconds a pause and three seconds an answer, 42 requests fill the 12 minutes after which
  the script stops asking (`RUN_LIMIT_S`), which is inside the step's 15 minutes with room for the last answer;
- the first request waits a pause as well: the chokepoint step before it asks the same host from another process, and each process keeps
  the least interval of the downloader alone. A run of the job (no option) waits one pause of 8 to 14 seconds before its first request, a
  sitting by hand does not (the person keeps the twenty minutes), and the 12 minutes count that wait.

**Time.** At the script's pace (a pause of 8 to 14 seconds before each request, the first included in a run of the job, an answer of about a
second): a normal run of 23 requests is 23 pauses, 3.1 to 5.4 minutes, 4 to 6 minutes in all; the worst run, 42 requests, is 42 pauses, 5.6 to
9.8 minutes, 6 to 12 minutes in all (the 12 minutes are the limit of the script: a run that is not done by then asks for nothing more and fails as below). The job
as a whole is a few minutes longer, and about ten minutes longer in the week of the chokepoint script's whole re-read (every fourth week). A
first-load sitting of 15 ports is 45 requests (6 to 10 minutes of pauses), one more for a port that is checked against the newest.

**What a run does with what it read.** Everything is read, then checked, then written; a port that fails a check keeps its file. A run that
gets under 90% of the rows it expects, whose table ends earlier than at the last run, that has to skip more than 10% of the ports, whose deep
pass finds the older weeks of more than a tenth of the ports changed by more than a quarter ("history revised: run `--full`"), or whose
folder would pass the size stop, is refused as a whole: nothing is written and a failure is recorded. The script never writes a file that
the site's data checks refuse (it applies the same rules before it writes; a test runs both on the same documents), and it exits 0 whatever
happens, so that the step cannot turn the job red. A step killed between the writing of a file and its move into place would leave a
`<id>.json.tmp` that the data checks refuse and a refusal discards the whole update, the chokepoint files with it: the job removes such a file
in a step of its own.

**The folder's size.** The folder may not exceed 3,500 kB (`SIZE_STOP_KB`, the owner's figure to raise: `web/scripts/check-size.mjs` budgets
the whole data folder separately). From 90% of it (3,150 kB) the summary of every run says so, as a GitHub warning in the run and in the note of
the status entry: how many kB the folder holds, how many it grows by in a week (each file gains one week a week) and in how many weeks the
stop would be reached. Raising the stop is a decision for the owner; at the stop a weekly run refuses everything and records a failure.

**When it fails.** After three weekly runs in a row, "Data update failing: portwatch-port-traffic" opens, with the last error of the run.
The usual ones and what to do: the service refused for its quota (the script waits 65 seconds once per page, or the delay the service names plus 5 seconds when that is
longer, and stops at a second refusal, at a delay of more than five minutes and at a wait that would end after its 12 minutes; the
downloader, for the other scripts, does the same for an HTTP 429 with the delay in its body and no header; look again next week); the service returned fewer rows than expected or the table ends earlier than before (the service is behind or
changed: read the run's log, nothing was written); some ports were skipped or "history revised" (PortWatch re-estimated its history: run
`--full` by hand for the ports it names, below); the folder would pass the size stop; the run used its twelve minutes. The files keep their
last good version in every case. "Data update discarded by the data checks" after this step means the checks refused a file of the folder
and, with it, the chokepoint update of the same job: open the output of the checks in the issue. The first scheduled run of the step is the one
that writes the status entry of the source into `data/_status/updates.json`: until then neither the staleness check nor the About window
says anything about it, and a first run that fails shows the source in the "Data freshness" table with the badge "Retrying" (never "On time", and not stale), with the note that the last check did not complete; it turns "Check failing" at the third run in a row. What a failed run
records: a failure whenever the status file already holds an entry of the source; while it holds none, the failure is printed and recorded
nowhere when some port has neither a file nor an entry of `none` (the first load is not finished), and recorded when every port is accounted
for (the first scheduled runs, retrying until the third). Leave
out of your commits the entry that a sitting by hand writes. "Data stale: portwatch-port-traffic" (Mondays) means no success for more than 16
days or a latest day of data more than 21 days old.

**By hand.**

1. `.venv/bin/python -I pipeline/freight/fetch_portwatch_port_traffic.py --dry-run` prints the plan of a weekly run (the groups, the chunks, the
   requests, the minutes), and `--dry-run --backfill --max-ports 15` that of a sitting; they ask for nothing and take no lock.
2. `... --backfill --max-ports N` (N from 1 to 15, 15 when it is left out) reads the next ports that have no file, in the fixed order of the ids,
   each written as soon as its pages are in: a sitting of the first load, or the reading of a port added to `ports.geojson` (add the asset, run
   it, commit both; the weekly step would also read it, five a run). Run it in the background (several minutes). A sitting that stops short
   (the service refuses, the folder reaches the size stop) leaves the files already written: run it again. What the code enforces: a sitting is at
   most 15 ports (`--max-ports` takes 1 to 15, `--full` takes at most 15 ports), and one runs at a time (a run that asks holds a lock on a file
   of the system's temporary folder; a second copy prints one line and exits without a request). What it does not enforce: the twenty minutes
   between two sittings, which are yours to keep.
3. `... --full port955 port276` reads these ports in full again (at most 15) and replaces their files, after PortWatch has re-estimated its history
   or when a run reports a port as skipped for good. Commit the files by hand: a job never changes a week older than the 52 it reads, and the guard
   (above) would refuse such a change in a job's output.
4. After a sitting, `node web/scripts/validate-data.mjs`, `.venv/bin/python -I pipeline/common/staleness.py`, and read what the sitting printed: the ports
   that returned no rows, and how far the rounding moves the 52-week sums of each port (the rule keeps it within 0.5%; `ROUNDING OVER 0.5%` would
   be a defect).
5. A page of 1,000 rows counts as followed by more rows even when the service does not say so. A first-load port whose last week starts more than 21
   days before the newest last week (of the folder and of the sitting) is not accepted on the first read: the script asks the service for the
   rows of that port after its last day. If there are some, the first read stopped short, the file is not written and the port stays in `pending`;
   if there are none, the port really ends there in PortWatch and its file is written as it is (the sitting says so). Once the load is complete, check
   that no file ends more than 21 days before the newest (the list must be empty or hold only ports that PortWatch itself has not updated):
   `.venv/bin/python -I -c "import glob,json,datetime as d; f={p:d.date.fromisoformat(json.load(open(p))['y']) for p in glob.glob('data/freight/port-traffic/port*.json')}; n=max(f.values()); print(n, sorted(p for p,v in f.items() if (n-v).days>21))"`.

`index.json` is `{checked, none, pending}`, written by the script and checked by the validator, which asks of every `portwatch` id of the port assets a
file, an entry of `none` or an entry of `pending`, and of no id more than one of them:

- `none`: the ports that returned no rows at the last check. They have no file and `--backfill` skips them; no page shows them. The weekly run asks again
  for them, in the week of their quarter of the ports.
- `pending`: the ports not read yet. While the first load is under way it lists the ports without a file; the script takes an id out of it as it writes
  the file (after each port, so that a run that stops leaves the folder as the validator accepts it), and it is an empty list once every port has a file or is in
  `none`. It is what lets a release go out between two sittings.
- `checked`: the day of the last run that read a port in full.

A run that reads no port in full leaves `index.json` byte-identical when nothing in the folder changed.

The port page (the "Weekly port traffic" block, `PortTrafficSection.tsx`) reads `index.json` first and asks for a port's file only when the port is in
neither list: for a port in `none` or in `pending` it shows nothing. What the block shows, and the rules of the weekly sums, the pairing of the ports and
the revisions, are in METHODOLOGY.md (section 5, "Port traffic").

### Freight market digest: a build step of the PortWatch job

`pipeline/freight/build_market_now.py` writes `data/freight/market-now.json` (about 1 kB): for tankers and for dry bulk carriers, the five
passages with the most estimated cargo of that ship type over the 52 weeks that end a year back, with the vessel transits and PortWatch's
estimated cargo (Mt) over the last four complete weeks (28 days) and over the same four weeks 364 days earlier, the window of the alert banners,
and the change between the two in per cent, which the builder computes on the sums before rounding (the page prints it and computes none).
The method is in METHODOLOGY.md. **It uses no network and reads nothing but `data/freight/portwatch/*.json`**: no download, no request to
PortWatch, no `raw/` folder, no daily table, no `chokepoints.json`. It therefore runs on a fresh clone and on the runners of GitHub as it is
(`pipeline/bootstrap.sh` runs it after the alert banners).

**Where it is.** `update-portwatch.yml` runs it after the alert banners and before the digest of changes (`id: market`, `continue-on-error`, 5
minutes). Its place relative to the port step does not matter: it reads the chokepoint files, which the chokepoint step has written, and the port
step does not touch them. The finish step records it as source `build-market-now`, validates the file (`web/scripts/validate-freight.mjs`: the
shape only) and commits `data/freight/market-now.json` with the other paths of the job. The annual job has no step for it: it rebuilds neither
the weekly series nor anything this file holds.

**When it fails.** The step never fails the job. It refuses, keeps the previous file, records a failure of `build-market-now` and exits 0 when: a
weekly file is not the one its name says, has no `vol` block or lists of different lengths, does not start on a Monday, holds a value that is not a
finite number or is negative, or has a week missing or extra (the weeks are taken by date, rebuilt from `start`: a week dropped by the weekly
series would otherwise shift every later value by one week), whether or not the file would rank; fewer than five weekly files exist, or fewer than
five can be ranked; the new digest would end on a date earlier than the file published. A file that starts after the first of the 52 ranking weeks
(a passage mapped lately, which has fewer than 104 weeks) is not a refusal: it is left out of the ranking, the output names it
("left out of the ranking: <passage>.json starts on ..."), and the digest is built from the others. The file is not rewritten when its content is the same, so a week without new data
makes no commit. After three failed runs in a row (not at the first, which is the rule of the other build steps: its inputs change every week and
a short week heals with the next) "Data update failing: build-market-now" opens, with the last error. The usual cause is a week that PortWatch
did not deliver: look at `data/freight/portwatch` (the last `y` of each file, and the number of weeks since `start`); the next weekly run
rebuilds the digest from the files it finds.

**A failed step does not hold back the site.** The checks that run before the site is republished compare the digest with the weekly
files at the digest's own date. They skip that comparison, with the reason, when the builder would refuse a weekly file, when a file no
longer holds the digest's window, and when the record of `build-market-now` in `data/_status/updates.json` says that the step failed at its
last run (the previous digest is then kept under weekly files that the same job has rewritten, perhaps with revised values). A digest dated
after the weekly files, or a row that differs from a recount while the step's last run succeeded, still fails.

**A series that lags.** `to` is the earliest last complete week of all the files, so one series that lags holds the digest's date back for
every passage and the figures of every row are those of the earlier week, without any failure. Whenever some series end later than that date,
whether the file is rewritten or unchanged, the output of the step names the series the digest waits for ("N series end later than the digest, on ...; the
digest ends on ..., the last complete week of <passage>") and the note of its status record (`data/_status/log.jsonl`, the last line of
`build-market-now`) gives the count and the date ("unchanged; N series end later than <to> (on <date>)"), without naming any.
If a lag appears when the digest has already reached the later week, the new date would be earlier than the file published and the run is
refused (the failure above, with the same sentence in its error). What to look at: the file named as the last complete week of the digest,
in `data/freight/portwatch`: its last `y`, and whether the weekly PortWatch download of that passage was short. The digest has no source of its own in the staleness check: it follows `portwatch`, whose last day
it carries as `to`.

## Releasing

A release is a state of the code and of the hand-made layers that the owner decides to number. The weekly and monthly
data updates are not releases. The release shown in the About window ("Release N, date") is not the date of the data:
the dates of the data updates, which the window shows apart, are the sources'. No git tag and no GitHub release is made.
What a release does today, in this order:

1. **The account.** `PROGRESS.md` gets a section "<Ordinal> release (<date>): what changed".
2. **`CHANGELOG.md`.** One entry at the top, `## Release <N> (<YYYY-MM-DD>)`, written from that section in the words of a
   visitor (what one sees added, changed or corrected on the site), with `### Added`, `### Changed` and `### Corrected`
   as needed. A figure goes in only if it is in `PROGRESS.md` and the site shows it as such: check it in `data/`.
3. **`release.json`.** The change that publishes a release bumps it: `{ "release": <N>, "date": "<YYYY-MM-DD>" }`, the
   same number and date as the entry. Rebuild `data/coverage.json` after the bump (`pipeline/commodities/build_coverage.py`):
   it carries the release number. `web/vite.config.ts` reads it at build and the About window shows the number
   and date with a link to `CHANGELOG.md`. `pipeline/tests/test_governance.py` fails when the file, the changelog and
   the sections of `PROGRESS.md` do not agree.
4. **The routes and lanes that stay.** Once the site is published, `pipeline/freight/release_ids.py` writes
   `pipeline/freight/released_ids.json` (the section "At each release" above gives the command).
5. **The checks.** `.github/workflows/ci.yml` runs the type check, the node tests, `node web/scripts/validate-data.mjs`,
   the Python unit suite, the production build and `npm run check-size`; `deploy.yml` calls it and publishes nothing
   unless all pass.
6. **The push.** A push to `main` runs `deploy.yml`, which builds the site and publishes it on GitHub Pages.

## A site that refuses the downloader

The downloader (`pipeline/common/fetch.py`) identifies itself plainly, with the one constant `USER_AGENT`
(`data-update-script/1.0 (python-requests)`): no browser name, no project or personal name, no address. Every update
script downloads through it. If a site refuses it, it is not worked around: the source fails, the issue opens, and
its update becomes a step done by hand (download the file in a browser into `raw/`, then run the script, which uses a
complete file already on disk where it can).

## Rebuilding everything from a fresh clone

`raw/` (the downloads) is not in git. `bash pipeline/bootstrap.sh` creates the Python environment, installs the
exact versions, downloads the scheduled sources, rebuilds every builder in order and runs the checks
(`--dry-run` prints the steps; `--with-baci` also downloads BACI). Versions: Python 3.12 in the workflows (3.11 or
later works; 3.13 is used locally), Node 22. Python packages: `pipeline/requirements-lock.txt` (exact versions;
`requirements.txt` names the direct dependencies); the actions are pinned to commit SHAs. Dependabot's monthly
pull requests are configured but switched off (`open-pull-requests-limit: 0` in `.github/dependabot.yml`: each pull
request would send an e-mail); set the three limits to 3 to turn them on.

The annual job keeps its downloads (`raw/usda`, `raw/eia`, `raw/usgs`) between runs as the workflow artifact
`raw-annual`: uploaded at the end of every run, kept 90 days, restored at the start of the next run by
`pipeline/annual/restore_raw.py` (the Actions cache would not do: an entry not read for seven days is evicted, and the
job runs monthly). What that gives, step by step:

- with the artifact restored, a source whose download fails, or whose file fails its checks, keeps its previous file
  in `raw/` (a new file replaces it only after the checks), and the builders that run read that previous file;
- a source is recognised as unchanged only when the file just downloaded has the digest recorded in the status file
  and the same digest as the file in `raw/` (an artifact can be older than the last recorded download, when an upload
  failed); otherwise it is installed again and the builders run;
- with no artifact (the first run, a restore that failed, or no upload for 90 days), `raw/` is empty: every source
  that downloads counts as changed, and a source that fails leaves its builder without input. The builder that reads
  it (`build-commodities`) then fails, its previous outputs are restored, so the site keeps the previous commodity
  pages, and "Data update failing: build-commodities" opens at once. The next run tries again.

## Only confirmed by a real run on GitHub

The workflows cannot be run outside GitHub. Tested locally: the status module (failures recorded for a step that did
not finish, the merge of two jobs' status files, the thresholds), `push.sh` in throwaway repositories (two jobs
pushing at once, with and without the merge driver; a conflicting hand edit, whose failure record is then pushed; a
push refused every time), the discard of the finish action (path by path, and nothing committed when the checks still
fail), the issue scripts (data update alerts, "Site not republished", "Watcher failing") against a mock of the GitHub
API, the verdict steps of `ci.yml` and `deploy.yml`, the restore of `raw-annual` with a mocked `gh`, the guard
replayed over the published history, the validators, the staleness check and the watcher on saved pages. Untested
until a real run: the expressions of the workflows (step outcomes, `inputs` and outputs of a called workflow, job
results under `!cancelled()`, the concurrency group across three workflows), the upload and listing of the
`raw-annual` artifact (its size, about 350 MB before compression), the nested call deploy -> ci with `soft` and the
`issues: write` permission it is granted, the issue calls with the real API and permissions, the runner's Python with
`setup-python` in the watchers, whether commits made with the workflow token keep the schedules alive, and the
downloads from GitHub's runners with the new identification (checked from a development machine only).
