"""
Polite, robust downloader shared by the update scripts.

    from common.fetch import download, get_text, get_json, FetchError

Features
  * ``requests`` with connect/read timeouts and a plain, truthful User-Agent (``USER_AGENT``: what the client is,
    no browser name, no project or personal name, no address); every update script downloads through this module;
  * retries with exponential backoff + jitter (default 4 attempts) on network errors, HTTP 408/425/429/5xx;
  * a minimum pause between two requests to the same host (``MIN_INTERVAL``, default 1.5 s);
  * resumable large downloads (HTTP Range) that keep a ``<dest>.part`` file between attempts;
  * sanity checks: Content-Type / magic bytes must match the expected kind ("xlsx", "xls", "zip",
    "csv", "json", "html"), so an HTML error page is never saved as a CSV/XLSX/ZIP; optional minimum size;
    final size must equal Content-Length when the server sent it;
  * atomic writes: data goes to ``<dest>.part`` and is moved with ``os.replace`` only when complete.

Everything raises ``FetchError`` (a short message) so callers can record the failure and carry on.
Importable from the repo root: ``sys.path.insert(0, "pipeline")`` (the update scripts do this).
"""
import os
import random
import threading
import time
from urllib.parse import urlsplit

import requests

# The one place the identification is set. A site that refuses this client is not worked around: its update becomes a
# step done by hand (docs/UPDATING.md). Naming the project or a contact page here is the owner's decision. sec.gov alone
# asks automated clients for a contact address: pipeline/companies/sec_edgar.py adds the owner's to this string in the
# headers of its own requests, for sec.gov only (the owner's decision of 24 November 2026); the session keeps this one.
USER_AGENT = "data-update-script/1.0 (python-requests)"
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 90
ATTEMPTS = 4
BACKOFF_BASE = 4.0       # seconds; delay = BACKOFF_BASE * 2**(attempt-1) + jitter
MIN_INTERVAL = 1.5       # seconds between requests to the same host
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}

# expected kind -> leading bytes of a genuine file
MAGIC = {
    "xlsx": (b"PK\x03\x04",),
    "zip": (b"PK\x03\x04",),
    "xls": (b"\xd0\xcf\x11\xe0",),
}

_session = None
_last_hit = {}
_lock = threading.Lock()


class FetchError(Exception):
    """A download failed for good (after retries) or the payload was not what was expected."""


def _sess():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        })
    return _session


def _pause(url, min_interval=None):
    """Sleep so that two requests to one host are at least ``min_interval`` apart."""
    host = urlsplit(url).netloc.lower()
    gap = MIN_INTERVAL if min_interval is None else min_interval
    with _lock:
        wait = _last_hit.get(host, 0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.monotonic()


def _sleep_backoff(attempt):
    time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, BACKOFF_BASE))


def _short(e):
    return (str(e).replace("\n", " ")[:160]) or e.__class__.__name__


def _check_head(kind, content_type, first):
    """Raise FetchError when the first bytes / content type do not fit ``kind``."""
    ct = (content_type or "").lower()
    if kind in ("xlsx", "xls", "zip", "csv", "json"):
        head = first.lstrip()[:200].lower()
        if "text/html" in ct or head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            raise FetchError(f"got an HTML page instead of {kind}")
    if kind in MAGIC and not any(first.startswith(m) for m in MAGIC[kind]):
        raise FetchError(f"content is not a valid {kind} file")
    if kind == "json" and first.lstrip()[:1] not in (b"{", b"["):
        raise FetchError("content is not JSON")


def request(url, *, params=None, headers=None, attempts=ATTEMPTS, timeout=None, stream=False, min_interval=None,
            method="GET", allow_redirects=True, retry_status=RETRY_STATUS):
    """GET/HEAD with retries; returns a ``requests.Response`` with a good status or raises FetchError.

    ``allow_redirects=False`` returns a redirect (3xx) to the caller instead of following it: requests sends the
    caller's headers on to whatever host a redirect names, so a caller whose header is meant for one host checks the
    next address itself (pipeline/companies/sec_edgar.py). ``retry_status``: the statuses asked again (a caller that
    must stop at the first HTTP 429 leaves it out)."""
    timeout = timeout or (CONNECT_TIMEOUT, READ_TIMEOUT)
    last = "no attempt"
    for attempt in range(1, attempts + 1):
        _pause(url, min_interval)
        try:
            r = _sess().request(method, url, params=params, headers=headers, timeout=timeout, stream=stream,
                                allow_redirects=allow_redirects)
        except requests.RequestException as e:
            last = e.__class__.__name__ + (" (timeout)" if isinstance(e, requests.Timeout) else "")
        else:
            if r.status_code in retry_status:
                last = f"HTTP {r.status_code}"
                r.close()
            elif r.status_code >= 400 and r.status_code != 416:
                code = r.status_code
                r.close()
                raise FetchError(f"HTTP {code} for {urlsplit(url).netloc}{urlsplit(url).path}")
            else:
                return r
        if attempt < attempts:
            _sleep_backoff(attempt)
    raise FetchError(f"{last} after {attempts} attempts ({urlsplit(url).netloc})")


def get_text(url, *, params=None, attempts=ATTEMPTS, min_interval=None, max_bytes=20_000_000):
    """Download a small text page (HTML/CSV) and return it as str."""
    r = request(url, params=params, attempts=attempts, min_interval=min_interval)
    if len(r.content) > max_bytes:
        raise FetchError("response larger than expected")
    if not r.content:
        raise FetchError("empty response")
    return r.text


def get_json(url, *, params=None, attempts=ATTEMPTS, min_interval=None):
    """Download a JSON document, retrying when the body is not valid JSON; ArcGIS ``error`` payloads are failures."""
    last = "invalid JSON"
    for attempt in range(1, attempts + 1):
        r = request(url, params=params, attempts=attempts, min_interval=min_interval)
        try:
            doc = r.json()
        except ValueError:
            last = "response is not valid JSON"
        else:
            if isinstance(doc, dict) and isinstance(doc.get("error"), dict):
                last = f"service error: {_short(doc['error'].get('message', doc['error']))}"
            else:
                return doc
        if attempt < attempts:
            _sleep_backoff(attempt)
    raise FetchError(last)


def download(url, dest, *, kind=None, min_bytes=1, attempts=ATTEMPTS, resume=False, min_interval=None,
             chunk=1 << 20, timeout=None, max_seconds=None):
    """
    Download ``url`` to ``dest`` atomically and return the file size in bytes.

    kind        expected type: "xlsx", "xls", "zip", "csv", "json" or None (no type check).
    min_bytes   smaller files are rejected (a stub or error page).
    resume      keep ``dest + '.part'`` between attempts and continue it with a Range request (large files).
    max_seconds wall-clock limit per attempt (default 600 s; 3 h for resumable large files), so a server
                that trickles bytes slower than the read timeout cannot stall a scheduled job.
    """
    max_seconds = max_seconds or (3 * 3600 if resume else 600)
    dest = os.fspath(dest)
    part = dest + ".part"
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    timeout = timeout or (CONNECT_TIMEOUT, READ_TIMEOUT)
    last = "no attempt"
    for attempt in range(1, attempts + 1):
        have = os.path.getsize(part) if (resume and os.path.exists(part)) else 0
        headers = {"Range": f"bytes={have}-"} if have else None
        try:
            r = request(url, headers=headers, attempts=1, stream=True, timeout=timeout, min_interval=min_interval)
        except FetchError as e:
            last = str(e)
            if "HTTP 4" in last and "HTTP 408" not in last and "HTTP 425" not in last and "HTTP 429" not in last:
                raise
        else:
            try:
                if r.status_code == 416:  # nothing left to fetch: the part file is probably complete
                    total = have
                else:
                    if have and r.status_code == 206:
                        mode = "ab"
                    else:
                        mode, have = "wb", 0  # server ignored Range (or fresh start)
                    expected = r.headers.get("Content-Length")
                    expected = int(expected) + have if expected and expected.isdigit() else None
                    first = None
                    started = time.monotonic()
                    with open(part, mode) as fh:
                        for block in r.iter_content(chunk):
                            if time.monotonic() - started > max_seconds:
                                raise requests.Timeout(f"download exceeded {max_seconds} s")
                            if not block:
                                continue
                            if first is None and mode == "wb":
                                first = block[:512]
                                _check_head(kind, r.headers.get("Content-Type"), first)
                            fh.write(block)
                    total = os.path.getsize(part)
                    if expected is not None and total < expected:
                        raise requests.RequestException(f"truncated download ({total} of {expected} bytes)")
                if total < min_bytes:
                    os.remove(part)
                    raise FetchError(f"file too small ({total} bytes)")
                if kind in MAGIC:
                    with open(part, "rb") as fh:
                        _check_head(kind, None, fh.read(512))
                os.replace(part, dest)
                return total
            except FetchError:
                if os.path.exists(part):
                    os.remove(part)
                raise
            except (requests.RequestException, OSError) as e:
                last = e.__class__.__name__ + (" (timeout)" if isinstance(e, requests.Timeout) else "")
                if not resume and os.path.exists(part):
                    os.remove(part)
            finally:
                r.close()
        if attempt < attempts:
            _sleep_backoff(attempt)
    if os.path.exists(part) and not resume:
        os.remove(part)
    raise FetchError(f"{last} after {attempts} attempts")


def head(url, *, attempts=2, min_interval=None):
    """HEAD request; returns the response headers or raises FetchError."""
    return request(url, attempts=attempts, method="HEAD", min_interval=min_interval).headers
