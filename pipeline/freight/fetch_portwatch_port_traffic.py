"""
Fetch the IMF PortWatch daily port table and write the weekly port traffic files of data/freight/port-traffic/.

    python pipeline/freight/fetch_portwatch_port_traffic.py                       # the weekly run (what the workflow calls)
    python pipeline/freight/fetch_portwatch_port_traffic.py --dry-run             # the plan, no request
    python pipeline/freight/fetch_portwatch_port_traffic.py --backfill --max-ports 15   # one sitting of the first load
    python pipeline/freight/fetch_portwatch_port_traffic.py --full port955 port276      # read these ports in full again

Source  ArcGIS feature service Daily_Ports_Data (services9.arcgis.com/weJ1QsnbMYJlCHdG), one row per port per day, at most
        PAGE (1,000) rows a request, the ports named in the request (at most MAX_IDS ports and MAX_ADDRESS characters of
        address). The ports are the `portwatch` ids of data/infrastructure/ports.geojson; their names come from
        pipeline/cache/portwatch_ports.csv. Nothing else is read: no robots file is asked for (the data service has none).
Pace    the owner's rule for PortWatch (25 November 2026): read it as a person would, in small pieces, one request at a time
        and slowly, and credit it. This script gives every request to common/fetch.py with the least interval
        fetch_portwatch.PAUSE_S[0] (a request repeated after an error waits as long as any other) and waits a pause of
        random.uniform(*PAUSE_S) between two requests; the figures are those of the chokepoint script, imported, one place
        (8 to 14 seconds today). No thread, no pool. The seconds are this script's reading of "slowly", not a figure of the
        owner. The IMF's terms page says it "prohibits bulk download of information by automated technology without explicit
        permission" (NOTICE.md quotes it): that is why the first load is made in sittings of a few ports, by hand, and why a
        weekly run reads only what the plan below says.
Modes   weekly (no option): the last WINDOW_WEEKS weeks of every port that has a file (PortWatch revises its recent days),
        the last DEEP_WEEKS weeks instead for one quarter of the ports (the ports in their fixed order, the quarter by the
        week: every port is read over a year once every four weeks, never all together), and at most
        SCHEDULED_BACKFILL_CAP ports without a file read in full (3 requests each; a port that returned nothing is asked
        again only in the week of its quarter). The requests are counted by the plan itself (``--dry-run`` prints them).
        --backfill: only the ports without a file, in order, ``--max-ports N`` of them: a sitting of the first load; run it
        again for the next ports (a port with a file is skipped, a port that returned nothing is in index.json and skipped).
        --full ID...: the ports named, read in full again and their file replaced (after PortWatch re-estimates its history).
        --ports ID... and --limit N keep a few ports of the plan; --out DIR writes elsewhere (nothing under data/_status).
Files   weekly sums, see portwatch_ports.py. Nothing daily is written anywhere: the rows live in memory while a port is
        built. A file is written to ``<name>.tmp`` in its folder and moved into place; the weekly files of a run are written
        only after every request of the run has been made and checked; a first-load port is written when its pages arrived.
        data/freight/port-traffic/index.json lists the ports that returned no rows at the last check (``none``) and the ports
        not read yet (``pending``: the first load is made in sittings; an id leaves the list when its file is written, and the
        list is empty once every port has a file or is in ``none``).
Checks  a page without the expected fields or with a value that is not a number stops the run; a run that gets under 90% of
        the rows it expects, or has to skip more than 10% of the ports, is refused; a port that returns nothing, or whose new
        file would lose weeks, change a week older than the window or end earlier, keeps its file; a table that ends earlier
        than at the last run is refused; a deep pass that finds the older weeks of more than a tenth of the ports changed by
        more than a quarter ("history revised: run --full") is refused; a file the site's rules would refuse is never
        written; the folder may not exceed SIZE_STOP_KB. The quota answer of the service ("API calls quota exceeded ...
        Retry after 60 sec") is waited out once (QUOTA_WAIT_S), a second refusal stops the run.
Status  a weekly run records its success or its failure for ``portwatch-port-traffic`` in data/_status/updates.json; a run
        made by hand (an option) records its success but not its failure (a sitting that stops short is not a scheduled
        failure). While some port has neither a file nor an entry in ``none`` (the first load is not finished), a weekly run
        does not record its failure either, so that the About window does not show the source as failing or stale because of a
        load that is still going on: the failure is printed. A dry run, or a run with --out, --ports or --limit, records
        nothing.

Always exits 0: a failure is recorded (weekly run) and the previous files are kept.
"""
import argparse
import json
import os
import random
import sys
import time
import traceback
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))

from common import fetch, status  # noqa: E402
import fetch_portwatch as FP  # noqa: E402  (PAUSE_S: the pace of PortWatch, one place)
import portwatch_ports as PP  # noqa: E402

SOURCE = PP.SOURCE
PAUSE_S = FP.PAUSE_S
QUOTA_WAIT_S = 65          # the service asks for 60 seconds after a quota answer
MAX_PAGES = 60             # pages of one query: a safeguard against a service that never says it is done
RUN_LIMIT_S = 12 * 60      # a weekly run stops asking after this long (the workflow's step is allowed 15 minutes)


class SizeStop(fetch.FetchError):
    """The folder would exceed SIZE_STOP_KB."""


class TimeUp(fetch.FetchError):
    """The run has used its time."""


def quota_refused(e):
    s = str(e).lower()
    return "quota" in s or "http 429" in s


class Reader:
    """Asks the service, one request at a time, with the pause of PAUSE_S before every request but the first."""

    def __init__(self, limit_s=None):
        self.n = 0
        self.limit_s = limit_s
        self.t0 = time.monotonic()

    def page(self, where, offset, order, allowed):
        if self.limit_s is not None and time.monotonic() - self.t0 > self.limit_s:
            raise TimeUp(f"the run used its {int(self.limit_s)} seconds")
        if self.n:
            time.sleep(random.uniform(*PAUSE_S))
        self.n += 1
        params = PP.request_params(where, offset, order)
        try:
            doc = fetch.get_json(PP.URL, params=params, min_interval=PAUSE_S[0])
        except fetch.FetchError as e:
            if not quota_refused(e):
                raise
            print(f"  the service refused for its quota ({e}); waiting {QUOTA_WAIT_S} s, once")
            time.sleep(QUOTA_WAIT_S)
            doc = fetch.get_json(PP.URL, params=params, min_interval=PAUSE_S[0])   # a second refusal stops the run
        feats = doc.get("features") if isinstance(doc, dict) else None
        if not isinstance(feats, list):
            raise fetch.FetchError("page without features")
        try:
            rows = PP.parse_rows(feats, allowed)
        except PP.RowError as e:
            raise fetch.FetchError(str(e))
        return rows, bool(doc.get("exceededTransferLimit")), len(feats)

    def rows(self, where, order, allowed):
        """All the rows matching ``where`` (the pages one after the other)."""
        out, offset = [], 0
        for _ in range(MAX_PAGES):
            rows, more, n = self.page(where, offset, order, allowed)
            out += rows
            offset += n
            if not n or not more:
                return out
        raise fetch.FetchError("too many pages")


# --------------------------------------------------------------------------------------------------- files
def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def dump(doc):
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False)


def read_state(out_dir, ids, index_ids=None):
    """({id: document} of the valid files of ``ids``, [ids of files that are not valid], {ids of the ``none`` of index.json
    that are among ``index_ids``, by default ``ids``})."""
    docs, bad = {}, []
    for i in ids:
        p = os.path.join(out_dir, f"{i}.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
            problems = PP.validate_doc(doc, i)
        except (OSError, ValueError) as e:
            problems = [str(e)]
        if problems:
            bad.append(i)
        else:
            docs[i] = doc
    none = set()
    try:
        with open(os.path.join(out_dir, PP.INDEX), encoding="utf-8") as fh:
            none = {i for i in json.load(fh).get("none", []) if i in (ids if index_ids is None else index_ids)}
    except (OSError, ValueError, AttributeError):
        pass
    return docs, bad, none


def folder_bytes(out_dir, replacing=()):
    """Bytes of the port files of the folder, those of ``replacing`` (ids) left out."""
    total = 0
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            if f.endswith(".json") and f[:-5] not in replacing:
                total += os.path.getsize(os.path.join(out_dir, f))
    return total


def print_plan(pl, today):
    r = pl["requests"]
    print(f"  quarter of the week: {pl['quarter']} of {PP.QUARTERS}")
    for kind in ("window", "deep"):
        for g in pl[kind]:
            lens = [len(PP.address(PP.where_window(c, date.fromisoformat(g["since"])))) for c in g["chunks"]]
            print(f"  {kind}: {len(g['ports'])} ports from {g['since']}, {len(g['chunks'])} chunks "
                  f"({', '.join(str(len(c)) for c in g['chunks'])} ports; addresses of {', '.join(map(str, lens))} characters), "
                  f"up to {sum(PP.pages(len(c) * g['days']) for c in g['chunks'])} requests")
    if pl["history"]:
        n = len(PP.address(PP.where_history(pl["history"][0]), order="date"))
        print(f"  in full: {len(pl['history'])} ports ({', '.join(pl['history'])}), up to {r['history']} requests "
              f"(addresses of {n} characters)")
    print(f"  requests: {r['total']} at most (window {r['window']}, deep {r['deep']}, in full {r['history']}); "
          f"{r['total'] * (PAUSE_S[0] + PAUSE_S[1]) / 2 / 60:.0f} to {r['total'] * PAUSE_S[1] / 60:.0f} minutes of pauses")


def run(argv=None, today=None):
    """One run. Returns {"requests", "written", "skipped", "none", "unchanged", "stopped", "error"} (the tests read it)."""
    ap = argparse.ArgumentParser(description="Weekly port traffic from IMF PortWatch")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, ask for nothing")
    ap.add_argument("--backfill", action="store_true", help="only the ports without a file (a sitting of the first load)")
    ap.add_argument("--max-ports", type=int, help="with --backfill: at most this many ports")
    ap.add_argument("--full", nargs="+", metavar="PORTID", help="read these ports in full again")
    ap.add_argument("--ports", nargs="+", metavar="PORTID", help="keep only these ports")
    ap.add_argument("--limit", type=int, help="keep only the first N ports")
    ap.add_argument("--out", help="write the files here instead of data/freight/port-traffic (no status is recorded)")
    args = ap.parse_args(argv)
    today = today or date.today()
    out_dir = args.out or PP.OUT
    by_hand = any([args.backfill, args.max_ports is not None, args.full, args.ports, args.limit, args.out])
    record = not (args.dry_run or args.out or args.ports or args.limit)   # a part of the ports must not set the counts of all
    res = {"requests": 0, "written": [], "skipped": [], "none": [], "unchanged": [], "stopped": None, "error": None, "revised": []}

    all_ids = PP.port_ids(PP.PORTS_GEOJSON)
    ids = all_ids
    names = PP.port_names(PP.TABLE)
    if args.ports:
        unknown = sorted(set(args.ports) - set(ids))
        if unknown:
            print("not a port of ports.geojson:", ", ".join(unknown))
            res["error"] = "unknown port"
            return res
        ids = [i for i in ids if i in set(args.ports)]
    if args.full:
        unknown = sorted(set(args.full) - set(ids))
        if unknown:
            print("not a port of ports.geojson (or not among --ports):", ", ".join(unknown))
            res["error"] = "unknown port"
            return res
    if args.limit:
        ids = ids[:args.limit]
    docs, bad, none = read_state(out_dir, ids, all_ids)
    for i in bad:
        print(f"  {i}.json is not a valid port file: read again in full")
    pl = PP.plan(ids, docs, none, today, backfill=args.backfill, max_ports=args.max_ports, full=args.full)
    print(f"port traffic: {len(ids)} ports, {len(docs)} with a file, {len(none)} without rows at the last check")
    print_plan(pl, today)
    least, most = PP.weekly_request_bounds(len(all_ids), today)
    print(f"  a weekly run for all {len(all_ids)} ports asks for {least} to {most} requests")
    if args.dry_run:
        return res

    prev = status.get(SOURCE) if record else {}
    reader = Reader(None if by_hand else RUN_LIMIT_S)

    def sync_index(force=False):
        """index.json is the list of the ports with no rows and of those not read yet, as the folder is now; it is written when
        that changed (or ``force``: a port was read in full), after every port of a sitting, so that a run that stops leaves
        a folder the site's rules accept."""
        pending = [i for i in all_ids if i not in none and not os.path.exists(os.path.join(out_dir, f"{i}.json"))]
        new = PP.index_doc(none, today.isoformat(), pending)
        try:
            with open(os.path.join(out_dir, PP.INDEX), encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, ValueError):
            old = None
        if force or not isinstance(old, dict) or set(old) != set(new) or any(old[k] != new[k] for k in ("none", "pending")):
            atomic_write(os.path.join(out_dir, PP.INDEX), dump(new))

    try:
        if pl["history"]:
            sync_index()
        # ---- the weeks of the ports that have a file: read everything, check everything, then write
        todo = [(k, g) for k in ("window", "deep") for g in pl[k]]
        if todo:
            fetched, since_of, deep_ports = {}, {}, []
            for kind, g in todo:
                since = date.fromisoformat(g["since"])
                for p in g["ports"]:
                    since_of[p] = since
                    if kind == "deep":
                        deep_ports.append(p)
                for ch in g["chunks"]:
                    for row in reader.rows(PP.where_window(ch, since), "ObjectId", set(ch)):
                        fetched.setdefault(row["portid"], []).append(row)
            latest = max((PP.last_day(r) for r in fetched.values()), default=None)
            if latest is None:
                raise fetch.FetchError("no row returned for the weeks asked for")
            if prev.get("data_to") and latest < prev["data_to"]:
                raise fetch.FetchError(f"the table ends on {latest}, earlier than at the last run ({prev['data_to']})")
            expected = sum((date.fromisoformat(latest) - s).days + 1 for s in since_of.values())
            got = sum(len(r) for r in fetched.values())
            print(f"  {got} rows of about {expected} expected, latest day {latest}")
            if got < PP.MIN_ROW_SHARE * expected:
                raise fetch.FetchError(f"the service returned {got} rows of the {expected} expected")
            new, skipped = {}, []
            for p, since in since_of.items():
                rows = fetched.get(p)
                if not rows:
                    skipped.append((p, "no row returned"))
                    continue
                merged = PP.merge_weeks(docs[p], PP.weekly(rows), since, PP.last_day(rows))
                why = PP.check_merge(docs[p], merged, since) or next(iter(PP.validate_doc(merged, p)), None)
                if why:
                    skipped.append((p, why))
                    continue
                if p in deep_ports:
                    share = PP.revision(docs[p], merged, since, PP.window_since(docs[p]))
                    if share is not None and share > PP.REVISED_SHARE:
                        res["revised"].append(p)
                new[p] = merged
            res["skipped"] = skipped
            for p, why in skipped:
                print(f"  {p} kept as it is: {why}")
            if len(skipped) > PP.MAX_SKIPPED_SHARE * len(since_of):
                raise fetch.FetchError(f"{len(skipped)} of {len(since_of)} ports skipped")
            if len(res["revised"]) > PP.REVISED_PORTS * len(deep_ports):
                raise fetch.FetchError(f"history revised: the older weeks of {len(res['revised'])} of {len(deep_ports)} ports "
                                       f"changed by more than {int(PP.REVISED_SHARE * 100)}% ({', '.join(res['revised'])}); run --full")
            texts = {p: dump(d) for p, d in new.items()}
            total = folder_bytes(out_dir, replacing=set(texts)) + sum(len(t.encode("utf-8")) for t in texts.values())
            if total > PP.SIZE_STOP_KB * 1000:
                raise SizeStop(f"the folder would be {total / 1000:.0f} kB, over the {PP.SIZE_STOP_KB} kB stop")
            for p, t in texts.items():
                path = os.path.join(out_dir, f"{p}.json")
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as fh:
                        if fh.read() == t:
                            res["unchanged"].append(p)
                            continue
                atomic_write(path, t)
                res["written"].append(p)
                docs[p] = new[p]
            print(f"  weeks: {len(res['written'])} files changed, {len(res['unchanged'])} as they were")

        # ---- the ports without a file (or named by --full): read in full, one file as soon as its pages are in
        rechecked = False
        for p in pl["history"]:
            try:
                rows = reader.rows(PP.where_history(p), "date", {p})
            except TimeUp as e:
                res["stopped"] = str(e)
                print("  stopped:", e)
                break
            rechecked = True
            weeks = PP.weekly(rows)
            if not weeks:
                if p in docs:
                    print(f"  {p}: no complete week returned, its file is kept")
                else:
                    none.add(p)
                    sync_index()
                    print(f"  {p}: no complete week returned (no row)" if not rows else f"  {p}: no complete week yet")
                continue
            if p not in names:
                raise fetch.FetchError(f"{p} is not in the ports table")
            doc = PP.build_doc(p, names[p], weeks, PP.last_day(rows))
            problems = PP.validate_doc(doc, p)
            if problems:
                raise fetch.FetchError(f"{p}: the file would be refused: {problems[0]}")
            text = dump(doc)
            size = folder_bytes(out_dir, replacing={p}) + len(text.encode("utf-8"))
            if size > PP.SIZE_STOP_KB * 1000:
                res["stopped"] = f"the folder would be {size / 1000:.0f} kB, over the {PP.SIZE_STOP_KB} kB stop"
                print("  stopped:", res["stopped"])
                if not by_hand:
                    raise SizeStop(res["stopped"])
                break
            atomic_write(os.path.join(out_dir, f"{p}.json"), text)
            docs[p] = doc
            none.discard(p)
            sync_index()
            res["written"].append(p)
            share, where = PP.rounding_error(weeks)
            tshare, twhere = PP.rounding_error(weeks, by_type=True)
            print(f"  {p} {names[p]}: {len(doc['calls']['tanker'])} weeks, {len(text.encode('utf-8'))} bytes, to {doc['y']}; "
                  f"rounding moves the 52-week sum of the four types by at most {share * 100:.2f}%" + (f" ({where})" if where else "")
                  + f", of one type by at most {tshare * 100:.2f}%" + (f" ({twhere})" if twhere else "")
                  + (" ROUNDING OVER 0.5%" if max(share, tshare) > 0.005 else ""))
        if rechecked:
            sync_index(force=True)
        elif os.path.exists(os.path.join(out_dir, PP.INDEX)):
            sync_index()
    except Exception as e:  # noqa: BLE001
        res["error"] = " ".join(str(e).split()) if isinstance(e, fetch.FetchError) else f"{e.__class__.__name__}: {e}"
        if not isinstance(e, fetch.FetchError):
            traceback.print_exc()
        res["requests"] = reader.n
        print("failed, the previous files are kept:", res["error"])
        if record and not by_hand:
            unread = [i for i in ids if i not in docs and i not in none]
            if unread:
                print(f"  not recorded as a failure: the first load is not finished ({len(unread)} ports have no file yet)")
            else:
                status.record_failure(SOURCE, res["error"])
        return res
    res["requests"] = reader.n
    res["none"] = sorted(none)
    if record:
        y = max((d["y"] for d in docs.values()), default=None)
        status.record_success(SOURCE, records=len(docs), data_to=y, note="updated" if res["written"] else "unchanged",
                              state={"mode": "hand" if by_hand else "weekly", "files": len(docs), "written": len(res["written"]),
                                     "skipped": len(res["skipped"]), "none": len(none), "requests": reader.n})
    print(f"done: {len(res['written'])} files written, {len(docs)} in all, {reader.n} requests")
    return res


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    sys.exit(0)
