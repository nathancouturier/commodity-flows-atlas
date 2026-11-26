"""The ONLY way the atlas talks to the U.S. Securities and Exchange Commission (decision of the owner, 24 November 2026).

    .venv/bin/python -I pipeline/companies/sec_get.py <url> [<url> ...]

- Hosts allowed: www.sec.gov and data.sec.gov, https only. Anything else is refused before any request.
- The contact that sec.gov asks automated readers to declare is read from the environment variable
  SEC_CONTACT_EMAIL, which the owner sets himself. It goes into the User-Agent header after a generic client name and
  NOWHERE else: it is never printed, never written to a file, never put in a URL. Without the variable nothing is
  fetched.
- One request at a time, at least 3 seconds after the previous one (a stamp file keeps the time of the last request
  across runs), far under the SEC's published limit. No retry inside a run. After a 403 or a 429 a stop file is
  written and every later run refuses to fetch: a person decides what happens next.
- A path that robots.txt of the host disallows for every agent is refused (the file is fetched once per host and
  cached like any other response).
- Every response body is saved under raw/sec-edgar/ at the root of the repository (not tracked; file name: a hash of
  the URL) with a line in raw/sec-edgar/index.tsv (time, status, bytes, URL). A URL already in the cache with status
  200 is not fetched again. At most 700 requests are counted in the index; beyond it nothing is fetched until a person
  raises the figure.
Prints one line per URL: status, bytes, cache file. The response headers are not saved.
"""
import fcntl
import hashlib
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.abspath(os.path.join(HERE, "..", "..", "raw", "sec-edgar"))
STAMP = os.path.join(CACHE, ".last_request")
STOP = os.path.join(CACHE, "STOPPED")
INDEX = os.path.join(CACHE, "index.tsv")
HOSTS = {"www.sec.gov", "data.sec.gov"}
PAUSE = 3.0  # seconds between two requests
MAX_REQUESTS = 700  # in all, counted in the index: beyond it nothing is fetched until a person raises the figure
LOCK = os.path.join(CACHE, ".lock")
CLIENT = "research-script/1.0"


def cache_path(url):
    return os.path.join(CACHE, hashlib.sha256(url.encode()).hexdigest()[:24])


def cached(url):
    """(status, path) of an earlier answer, or None."""
    if not os.path.exists(INDEX):
        return None
    hit = None
    for line in open(INDEX, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 4 and parts[3] == url:
            hit = (int(parts[1]), cache_path(url))
    return hit


def wait_turn():
    try:
        last = float(open(STAMP).read().strip())
    except (OSError, ValueError):
        last = 0.0
    delay = PAUSE - (time.time() - last)
    if delay > 0:
        time.sleep(delay)
    with open(STAMP, "w") as f:
        f.write(str(time.time()))


def requests_made():
    try:
        return sum(1 for _ in open(INDEX, encoding="utf-8"))
    except OSError:
        return 0


def fetch(url, contact):
    """One request, never beside another one (a lock file serialises every run). Returns (status, body bytes)."""
    os.makedirs(CACHE, exist_ok=True)
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if requests_made() >= MAX_REQUESTS:
            return 0, b""  # the budget of requests is spent
        wait_turn()
        req = urllib.request.Request(url, headers={"User-Agent": f"{CLIENT} {contact}", "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return -1, b""  # no answer (network): recorded, not retried here


def record(url, status, body):
    os.makedirs(CACHE, exist_ok=True)
    if status == 200:
        with open(cache_path(url), "wb") as f:
            f.write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\t{status}\t{len(body)}\t{url}\n")


def allowed_by_robots(url, contact):
    host = urllib.parse.urlsplit(url).netloc
    robots = f"https://{host}/robots.txt"
    hit = cached(robots)
    if hit is None:
        status, body = fetch(robots, contact)
        if status == 0:
            return None
        record(robots, status, body)
        if status in (403, 429):
            open(STOP, "w").write(f"{status} on {robots}\n")
            return None
        hit = (status, cache_path(robots))
    if hit[0] != 200:
        return True  # no robots file: nothing is disallowed
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(open(hit[1], encoding="utf-8", errors="replace").read().splitlines())
    return rp.can_fetch("*", url)


def main(urls):
    contact = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    if not contact:
        print("SEC_CONTACT_EMAIL is not set: nothing fetched")
        return 2
    if "@" not in contact or any(c.isspace() for c in contact):
        print("SEC_CONTACT_EMAIL does not look like one address: nothing fetched")
        return 2
    os.makedirs(CACHE, exist_ok=True)
    rc = 0
    for url in urls:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.netloc not in HOSTS:
            print(f"REFUSED (host not allowed)\t{url}")
            rc = 1
            continue
        if contact.lower() in url.lower():
            print("REFUSED (the contact may not be in a URL)")
            rc = 1
            continue
        if os.path.exists(STOP):
            print(f"STOPPED earlier ({open(STOP).read().strip()}): nothing fetched\t{url}")
            return 3
        hit = cached(url)
        if hit and hit[0] == 200:
            print(f"200 (cache)\t{os.path.getsize(hit[1])}\t{hit[1]}\t{url}")
            continue
        ok = allowed_by_robots(url, contact)
        if ok is None:
            print(f"STOPPED on robots.txt\t{url}")
            return 3
        if not ok:
            print(f"REFUSED (robots.txt disallows the path)\t{url}")
            rc = 1
            continue
        status, body = fetch(url, contact)
        if status == 0:
            print(f"BUDGET SPENT ({MAX_REQUESTS} requests in the index): nothing fetched\t{url}")
            return 4
        record(url, status, body)
        if status in (403, 429):
            open(STOP, "w").write(f"{status} on {url}\n")
            print(f"{status}\t0\t-\t{url}\nSTOPPED: the SEC refused; no further request will be made")
            return 3
        print(f"{status}\t{len(body)}\t{cache_path(url) if status == 200 else '-'}\t{url}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
