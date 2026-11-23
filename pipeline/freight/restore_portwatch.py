"""
Restore the PortWatch daily working table at the start of the weekly job (GitHub runners keep nothing between runs).

    python pipeline/freight/restore_portwatch.py

The table is not kept in git (NOTICE.md): the weekly job uploads pipeline/cache/portwatch/ as the workflow artifact
``portwatch-daily`` after each successful update. This script downloads the newest artifact of that name with the job's own
token (``gh api``: GET /repos/{owner}/{repo}/actions/artifacts?name=..., then .../artifacts/{id}/zip; the workflow needs the
``actions: read`` permission), checks that it is readable and not older than the monthly refresh, and installs it. Whatever
goes wrong (no artifact, expired, too old, corrupt, no network, no ``gh``) leaves the folder as it was and the job downloads the
whole table instead (fetch_portwatch.py). It always exits 0.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))

NAME = "portwatch-daily"
MAX_AGE_DAYS = 28  # fetch_portwatch.FULL_EVERY_DAYS: an older table is replaced by a full download anyway


def newest_usable(listing, now, max_age_days=MAX_AGE_DAYS, name=NAME):
    """The newest artifact named ``name`` of a listing (``gh api`` output of the artifacts endpoint) that has not expired and
    is not older than ``max_age_days``; None when there is none. Also used by pipeline/annual/restore_raw.py."""
    best = None
    for a in (listing or {}).get("artifacts", []):
        if a.get("expired") or a.get("name") != name:
            continue
        try:
            made = datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if (now - made).days > max_age_days:
            continue
        if best is None or made > best[0]:
            best = (made, a)
    return best[1] if best else None


def install(zip_path, dest, tmp):
    """Unpack ``zip_path``, check the daily files are readable and plausible, and move them into ``dest``. Returns the number of
    rows, or raises ValueError."""
    import build_portwatch as BW

    out = os.path.join(tmp, "unpacked")
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            base = os.path.basename(n)
            if base.startswith("daily_") and base.endswith(".csv.gz"):  # only the daily files, flat: no path from the archive is used
                with z.open(n) as src, open(os.path.join(tmp, base), "wb") as dst:
                    shutil.copyfileobj(src, dst)
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(tmp):
        if f.startswith("daily_"):
            shutil.move(os.path.join(tmp, f), os.path.join(out, f))
    try:
        rows = BW.read_cache(out)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"unreadable: {e.__class__.__name__}") from e
    if len(rows) < 1000 or not all(r.get("date") and r.get("portid") for r in rows[:50]):
        raise ValueError(f"implausible table ({len(rows)} rows)")
    os.makedirs(dest, exist_ok=True)
    for f in os.listdir(dest):
        if f.startswith("daily_"):
            os.remove(os.path.join(dest, f))
    for f in os.listdir(out):
        shutil.move(os.path.join(out, f), os.path.join(dest, f))
    return len(rows)


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, timeout=300, check=True)


def main():
    import build_portwatch as BW

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or not shutil.which("gh"):
        print("restore: not on GitHub (no GITHUB_REPOSITORY or no gh): nothing to restore")
        return
    try:
        listing = json.loads(gh("api", f"repos/{repo}/actions/artifacts?name={NAME}&per_page=20").stdout)
        art = newest_usable(listing, datetime.now(timezone.utc))
        if not art:
            print("restore: no usable artifact (none, expired, or older than %d days): the whole table will be downloaded" % MAX_AGE_DAYS)
            return
        with tempfile.TemporaryDirectory() as tmp:
            zpath = os.path.join(tmp, "a.zip")
            with open(zpath, "wb") as fh:
                fh.write(gh("api", f"repos/{repo}/actions/artifacts/{art['id']}/zip").stdout)
            n = install(zpath, BW.CACHE_DIR, tmp)
        print(f"restore: {n} daily rows from artifact {art['id']} made {art['created_at']}")
    except Exception as e:  # noqa: BLE001  (never fails the job)
        print(f"restore: not restored ({e.__class__.__name__}: {e}); the whole table will be downloaded")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print("restore: failed:", e)
    sys.exit(0)
