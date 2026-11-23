# Updating the data

How the scheduled updates work, what they do when something goes wrong, what GitHub e-mails, and the steps done by
hand. The owner's rule: scheduled updates must be robust and must never send failure e-mails; a real problem opens
one GitHub issue.

## The workflows

| Workflow | When (UTC) | What |
|---|---|---|
| `update-prices.yml` | Wednesdays 21:43, Thursdays 09:43 | World Bank Pink Sheet, EIA daily spot prices, freight indicators -> `data/prices` |
| `update-portwatch.yml` | Wednesdays 19:17 | IMF PortWatch chokepoint transits -> `data/freight/portwatch`, then the alert banners |
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

## When something fails

Every risky step is `continue-on-error`, so a data job always ends green. A failure is recorded in
`data/_status/updates.json` (per source: last attempt, last success, consecutive failures, last error) and turns into
an issue with the label `data-update` when it repeats:

| What | Recorded as | Issue |
|---|---|---|
| a source fails (download refused, file malformed, a column, commodity or series missing) | a failure of that source; the previous files are kept | "Data update failing: <source>" after 3 runs in a row for a weekly source, 2 for a monthly one |
| a build step fails (`build-freight`, `build-commodities`, ...) | a failure of the step; its previous outputs are restored | at the first failure |
| a step times out, crashes (an import error after a failed `pip install`) or is cancelled | the finish action records a failure for each source the step had begun and not recorded (`status.py interrupted`); when it had begun none, for each source it always runs | as above |
| the data checks refuse the result (`web/scripts/validate-data.mjs`, or `guard-data.mjs`: see "The before-and-after guard" below) | the whole update is discarded, path by path; a failure of every source of the job, so that its builds run again. If the checks still fail after the discard, nothing is committed, not even the failure | one "Data update discarded by the data checks", with the output of the checks (at once when nothing could be committed) |
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
