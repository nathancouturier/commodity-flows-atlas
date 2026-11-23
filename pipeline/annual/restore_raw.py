"""
Restore the downloads of the monthly annual job (raw/usda, raw/eia, raw/usgs) at the start of its run: GitHub runners keep
nothing between runs, and an Actions cache entry not read for seven days is evicted, which a monthly job always is.

    python pipeline/annual/restore_raw.py

The job uploads the three folders as the workflow artifact ``raw-annual`` (kept 90 days) at the end of every run. This script
downloads the newest one that has not expired with the job's own token (``gh api``, as pipeline/freight/restore_portwatch.py
does; the workflow needs the ``actions: read`` permission) and unpacks it into raw/. Only files under usda/, eia/ and usgs/
are taken, never a path that leaves them, and a folder already present in raw/ is left as it is. Whatever goes wrong (no
artifact, expired, corrupt, no network, no ``gh``) leaves raw/ as it was: update_annual.py then downloads every source in
full, as on a fresh clone. It always exits 0.
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

import restore_portwatch as RP  # noqa: E402

NAME = "raw-annual"
FOLDERS = ("usda", "eia", "usgs")
RAW = os.path.join(ROOT, "raw")
MAX_AGE_DAYS = 90  # the retention of the artifact: any artifact still listed holds the last files the job had


def install(zip_path, raw, tmp):
    """Unpack the artifact into ``tmp``, then move each of its folders to ``raw/<folder>`` where that folder is absent.
    Members are read relative to raw/ (``usda/...``) or with a leading ``raw/``. Returns {folder: number of files moved};
    raises ValueError (or zipfile.BadZipFile) when the archive holds nothing usable or is corrupt."""
    out = os.path.join(tmp, "unpacked")
    counts = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = info.filename.replace("\\", "/").split("/")
            if parts and parts[0] == "raw":
                parts = parts[1:]
            if info.is_dir() or len(parts) < 2 or parts[0] not in FOLDERS or any(p in ("", ".", "..") or ":" in p for p in parts):
                continue
            dest = os.path.join(out, *parts)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            counts[parts[0]] = counts.get(parts[0], 0) + 1
    if not counts:
        raise ValueError("no file of usda/, eia/ or usgs/ in the artifact")
    moved = {}
    for folder, n in counts.items():
        target = os.path.join(raw, folder)
        if os.path.exists(target):
            continue  # never replace files already on disk
        os.makedirs(raw, exist_ok=True)
        shutil.move(os.path.join(out, folder), target)
        moved[folder] = n
    return moved


def main():
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or not shutil.which("gh"):
        print("restore: not on GitHub (no GITHUB_REPOSITORY or no gh): nothing to restore")
        return
    try:
        listing = json.loads(RP.gh("api", f"repos/{repo}/actions/artifacts?name={NAME}&per_page=20").stdout)
        art = RP.newest_usable(listing, datetime.now(timezone.utc), max_age_days=MAX_AGE_DAYS, name=NAME)
        if not art:
            print("restore: no usable artifact (none yet, or expired): every annual source will be downloaded in full")
            return
        with tempfile.TemporaryDirectory() as tmp:
            zpath = os.path.join(tmp, "a.zip")
            with open(zpath, "wb") as fh:
                subprocess.run(["gh", "api", f"repos/{repo}/actions/artifacts/{art['id']}/zip"], stdout=fh, timeout=600, check=True)
            moved = install(zpath, RAW, tmp)
        print(f"restore: {moved or 'nothing (the folders exist already)'} from artifact {art['id']} made {art['created_at']}")
    except Exception as e:  # noqa: BLE001  (never fails the job)
        print(f"restore: not restored ({e.__class__.__name__}: {e}); every annual source will be downloaded in full")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print("restore: failed:", e)
    sys.exit(0)
