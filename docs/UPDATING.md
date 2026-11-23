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
| `ci.yml` | every pull request, and by hand (not on a push to a working branch) | type check, node tests, data validators, Python unit suite, build and size budget |
| `deploy.yml` | every push to `main`, and after a data update | the checks of `ci.yml`, then the build and the publication on GitHub Pages |

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
  forced, a warning is written in the run log, and the next run does the update again.

## When something fails

Every risky step is `continue-on-error`, so a data job always ends green. A failure is recorded in
`data/_status/updates.json` (per source: last attempt, last success, consecutive failures, last error) and turns into
an issue with the label `data-update` when it repeats:

| What | Recorded as | Issue |
|---|---|---|
| a source fails (download refused, file malformed, a column, commodity or series missing) | a failure of that source; the previous files are kept | "Data update failing: <source>" after 3 runs in a row for a weekly source, 2 for a monthly one |
| a build step fails (`build-freight`, `build-commodities`, ...) | a failure of the step; its previous outputs are restored | at the first failure |
| a step times out, crashes (an import error after a failed `pip install`) or is cancelled | the finish action records a failure for each source the step had begun and not recorded (`status.py interrupted`); when it had begun none, for each source it always runs | as above |
| the data checks refuse the result (`web/scripts/validate-data.mjs`, or `guard-data.mjs`: a table that lost more than a tenth of its rows, a file that shrank by half, a price that moved or was revised by more than half) | the whole update is discarded; a failure of every source of the job, so that its builds run again | one "Data update discarded by the data checks", with the output of the checks |
| a source stops being updated without failing (a disabled workflow, the same old file served again) | nothing | "Data stale: <source>" from the weekly staleness check, with the same rules as the site's "Data freshness" table |
| a newer release than the one in use (BACI, or a yearly page read by hand) | `state.available` of the source | "New release available: <id>", with the steps |

Each issue is updated at every run and closed automatically when the source recovers. Issues must be enabled for the
repository, and the owner must watch it to be notified.

**A real move that the guard refused.** A price can move by more than half, and a rebuild can drop rows on purpose.
After checking the change by hand, run the workflow by hand with "accept large moves" ticked: the guard then reports
the changes without refusing them.

## What GitHub e-mails

GitHub e-mails about a failed workflow run (with the default notification settings) to the person who triggered it;
for a scheduled run, to the person who last changed its schedule.

- **Data updates, staleness check, release watcher:** no e-mail in the normal course. Every step that can fail is
  allowed to; the run ends green, and the problem becomes an issue (GitHub e-mails new issues to the people who watch
  the repository). A data update that calls the deploy passes `soft: true`: a failed check skips the publication
  without failing the run.
- **Still possible:** a failure of GitHub itself before the steps (a runner that does not start, the checkout or the
  Python and Node set-up failing), or a job that runs past its own time limit (the steps have shorter limits so that
  this should not happen). These runs are red and GitHub e-mails as usual.
- **A push to `main`:** the deploy runs the checks; a failed check (or a failed Pages deployment) makes the run red and
  GitHub e-mails the person who pushed. This is GitHub's default for a failed deploy; nothing more is sent.
- **Pull requests and other branches:** a failed check e-mails the person who pushed, as for any failed workflow.
- **Cancelled runs** (a waiting run replaced by a newer one in the `data-update` group) are not failures.

## Keeping the schedules alive

GitHub disables the scheduled workflows of a public repository after 60 days without activity in it. The data
commits of the weekly jobs are that activity (prices change every week), so the schedules stay on as long as the jobs
commit. If the jobs stop committing for two months (sources frozen, or everything failing), GitHub disables the
schedules: the weekly staleness check opens "Scheduled workflows disabled by GitHub" while it still runs, and the
staleness issues show the sources going stale. To restore them: Actions tab, select each disabled workflow, "Enable
workflow", then run it once by hand.

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
`requirements.txt` names the direct dependencies); Dependabot proposes updates monthly (`.github/dependabot.yml`), and
the actions are pinned to commit SHAs.

The annual job keeps its downloads between runs in the Actions cache (`raw/usda`, `raw/eia`, `raw/usgs`), so an
unchanged file is recognised as unchanged and a failed download leaves the builders the previous file.

## Only confirmed by a real run on GitHub

The workflows cannot be run outside GitHub. Tested locally: the status module (failures recorded for a step that did
not finish, the merge of two jobs' status files, the thresholds), `push.sh` in throwaway repositories (two jobs
pushing at once, with and without the merge driver; a conflicting hand edit), the alert script against a mock of the
GitHub API, the guard, the validators, the staleness check and the watcher on saved pages. Untested until a real run:
the expressions of the workflows (step outcomes, `inputs` of a called workflow, the concurrency group across three
workflows), the Actions cache of `raw/`, the nested call deploy -> ci with `soft`, the issue calls with the real API
and permissions, and the downloads from GitHub's runners with the new identification (checked from a development
machine only).
