"""
Reads the annual reports that companies file with the US Securities and Exchange Commission (EDGAR), for the companies
layer (README.md of this folder). A person reads the figures; this script only fetches the documents politely and finds
the passages to read.

    .venv/bin/python -I pipeline/companies/sec_edgar.py cik <ticker or words of the name>    # filers of the tickers file
    .venv/bin/python -I pipeline/companies/sec_edgar.py search "<phrase>" [--forms 20-F]      # EDGAR full-text search
    .venv/bin/python -I pipeline/companies/sec_edgar.py filings <cik> [--forms 10-K,20-F,40-F] [--n 4]
    .venv/bin/python -I pipeline/companies/sec_edgar.py index <document or filing url> [--all]  # the documents of a filing
    .venv/bin/python -I pipeline/companies/sec_edgar.py get <url>                           # fetch one page, print its text file
    .venv/bin/python -I pipeline/companies/sec_edgar.py find <url> <regex> [--context 300] [--max 20]

The contact address. sec.gov asks automated clients to declare a User-Agent that names them with a contact address (its
page "Accessing EDGAR data": "Sample Company Name AdminContact@<sample company domain>.com"). The owner decided on 24
November 2026 that a contact address is sent to the SEC, and to nobody else, when its filings are read. The address is
the environment variable SEC_CONTACT_EMAIL, set by the owner: it is written in no file of the repository, and this
script never prints it, logs it or stores it. Without it the script stops before its first request.

Rules of the script, each tested in pipeline/tests/test_sec_edgar.py:
  * it downloads through the shared module (common/fetch.py), with the address in the headers of its own requests;
  * requests go to the hosts of HOSTS only, over HTTPS; a redirect is followed only to one of them, so the header never
    leaves sec.gov (requests would otherwise send it on to any host a redirect names);
  * one request at a time, at least MIN_INTERVAL seconds apart (sec.gov's published limit is 10 requests a second);
  * an HTTP 403 or 429 stops the run at once, without a retry (sec.gov answers so when it refuses or limits a client);
    a network error or an HTTP 5xx is asked again after the shared module's pause, ATTEMPTS times in all;
  * the pages are kept in pipeline/cache/sec/ (outside git): a filing does not change once filed, so it is read from the
    disk after the first time; the lists of filings and the tickers file are fetched again after a day.
"""
import html
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import fetch  # noqa: E402  (the shared downloader, whose address-free User-Agent this one extends)

ENV = "SEC_CONTACT_EMAIL"
HOSTS = ("www.sec.gov", "data.sec.gov", "efts.sec.gov")
CACHE = os.path.join(ROOT, "pipeline", "cache", "sec")
MIN_INTERVAL = 2.0          # seconds between two requests (sec.gov allows 10 a second)
ATTEMPTS = 3
MAX_REDIRECTS = 5
STOP_STATUS = (403, 429)    # never asked again (not in RETRY_STATUS)
RETRY_STATUS = (500, 502, 503, 504)
REDIRECT_STATUS = (301, 302, 303, 307, 308)
TIMEOUT = (20, 120)
FRESH_S = 24 * 3600         # the lists of filings and the tickers file are fetched again after this age
ANNUAL_FORMS = ("10-K", "20-F", "40-F", "10-K/A", "20-F/A", "40-F/A")
# one address, nothing around it (the value is never echoed: a message names the variable only)
ADDRESS = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}")

_last = [0.0]


class SecError(Exception):
    """A request was refused before it left, or sec.gov did not give the page. The message never holds the address."""


def user_agent():
    """The shared User-Agent of the update scripts followed by the owner's contact address, as sec.gov asks."""
    addr = os.environ.get(ENV, "").strip()
    if not addr:
        raise SecError(f"{ENV} is not set: sec.gov asks automated clients for a contact address, so no request is sent "
                       "without it (pipeline/companies/README.md)")
    if not ADDRESS.fullmatch(addr):
        raise SecError(f"{ENV} is not a single e-mail address: no request is sent")
    return f"{fetch.USER_AGENT} {addr}"


def host_ok(url):
    """True for an HTTPS address on one of HOSTS (the name the request goes to, whatever comes before an @)."""
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        return False
    return u.scheme == "https" and (u.hostname or "") in HOSTS and port in (None, 443)


def where(url):
    """Host and path of an address, for a message (never a query, which could carry anything)."""
    u = urlsplit(url)
    return f"{u.hostname or '?'}{u.path}"


def _pause():
    """At least MIN_INTERVAL seconds since the last request to any host of HOSTS (the shared module's own pause is per
    host; this one counts the three hosts of the SEC together)."""
    wait = _last[0] + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


def request(url):
    """GET one sec.gov page with the declared User-Agent; returns the response or raises SecError."""
    if not host_ok(url):
        raise SecError(f"not a sec.gov address ({where(url)}): the contact address is sent to the SEC only")
    headers = {"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate", "Accept": "*/*"}
    for hop in range(MAX_REDIRECTS + 1):
        _pause()
        try:
            r = fetch.request(url, headers=headers, attempts=ATTEMPTS, timeout=TIMEOUT, min_interval=MIN_INTERVAL,
                              allow_redirects=False, retry_status=RETRY_STATUS)
        except fetch.FetchError as e:
            stop = " (sec.gov refuses or limits this client: the run stops without asking again)" if any(
                f"HTTP {c} " in f"{e} " for c in STOP_STATUS) else ""
            raise SecError(f"{e}{stop}") from None
        if r.status_code not in REDIRECT_STATUS:
            return r
        nxt = urljoin(url, r.headers.get("Location", ""))
        r.close()
        if not host_ok(nxt):
            raise SecError(f"sec.gov redirected {where(url)} to {where(nxt)}: not followed, the contact address "
                           "would leave sec.gov")
        url = nxt
    raise SecError(f"more than {MAX_REDIRECTS} redirects ({where(url)})")


# ---------------------------------------------------------------------------------------------------------------- cache

def cache_path(url):
    """Where a page is kept: the host and the path of its address under pipeline/cache/sec/ (a query is hashed in)."""
    u = urlsplit(url)
    path = u.path.strip("/") or "index"
    if path.endswith("/"):
        path += "index"
    if u.query:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", u.query)[:80]
        path += "__" + safe
    parts = [re.sub(r"[^A-Za-z0-9._-]+", "_", p) for p in path.split("/") if p not in ("", ".", "..")]
    return os.path.join(CACHE, u.hostname or "host", *parts)


def fetch_bytes(url, max_age=None):
    """The page at url, from the cache when it is there (and younger than max_age seconds when given)."""
    path = cache_path(url)
    if os.path.exists(path) and (max_age is None or time.time() - os.path.getmtime(path) < max_age):
        with open(path, "rb") as f:
            return f.read()
    r = request(url)
    body = r.content
    if not body:
        raise SecError(f"empty answer for {where(url)}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, path)
    return body


def fetch_json(url, max_age=FRESH_S):
    body = fetch_bytes(url, max_age=max_age)
    try:
        return json.loads(body)
    except ValueError:
        raise SecError(f"the answer of {where(url)} is not JSON") from None


# ------------------------------------------------------------------------------------------------------------ html text

BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article", "ul", "ol",
         "hr", "title", "dt", "dd", "blockquote", "pre", "center"}
SKIP = {"script", "style", "head", "ix:header"}
CELL = {"td", "th"}


class _Text(HTMLParser):
    """Plain text of an HTML filing: one line per block or table row, the cells of a row joined by ' | ', the hidden
    XBRL header (ix:header) and scripts left out."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.row = [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag == "tr":
            self.row = []
        elif tag in CELL and self.row is not None:
            self.row.append([])
        elif tag in BLOCK:
            self._flush_text()

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "tr" and self.row is not None:
            cells = [" ".join("".join(c).split()) for c in self.row]
            cells = [c for c in cells if c]
            if cells:
                self.out.append("\n" + " | ".join(cells) + "\n")
            self.row = None
        elif tag in BLOCK and self.row is None:
            self._flush_text()

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "hr") and self.row is None:
            self._flush_text()

    def handle_data(self, data):
        if self.skip:
            return
        if self.row is not None:
            if not self.row:
                self.row.append([])
            self.row[-1].append(data)
        else:
            self.out.append(data)

    def _flush_text(self):
        self.out.append("\n")

    def text(self):
        raw = "".join(self.out).replace("\xa0", " ").replace("​", "")
        lines = [" ".join(line.split()) for line in raw.split("\n")]
        keep, blank = [], False
        for line in lines:
            if line:
                keep.append(line)
                blank = False
            elif not blank:
                keep.append("")
                blank = True
        return "\n".join(keep).strip() + "\n"


def html_text(body):
    """Plain text of an HTML (or plain text) document given as bytes."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            s = body.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if "<" not in s[:5000] and "<" not in s[-5000:]:
        return html.unescape(s)
    p = _Text()
    p.feed(s)
    p.close()
    return p.text()


def text_of(url):
    """The text of a document (kept next to the page in the cache as <name>.txt); returns (path, text)."""
    body = fetch_bytes(url, max_age=FRESH_S if "/Archives/" not in urlsplit(url).path else None)
    path = cache_path(url) + ".txt"
    if not os.path.exists(path) or os.path.getmtime(path) < os.path.getmtime(cache_path(url)):
        text = html_text(body)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    with open(path, encoding="utf-8") as f:
        return path, f.read()


# ------------------------------------------------------------------------------------------------------------- lookups

def tickers():
    """The SEC's file of the filers with a ticker: [{cik, ticker, title}]."""
    doc = fetch_json("https://www.sec.gov/files/company_tickers.json")
    rows = doc.values() if isinstance(doc, dict) else doc
    return [{"cik": int(r["cik_str"]), "ticker": r["ticker"], "title": r["title"]} for r in rows]


def find_cik(query):
    q = query.strip()
    rows = tickers()
    exact = [r for r in rows if r["ticker"].upper() == q.upper()]
    words = [w for w in re.split(r"\W+", q.lower()) if w]
    named = [r for r in rows if words and all(re.search(r"\b" + re.escape(w), r["title"].lower()) for w in words)]
    seen, out = set(), []
    for r in exact + named:
        if (r["cik"], r["ticker"]) not in seen:
            seen.add((r["cik"], r["ticker"]))
            out.append(r)
    return out


def full_text_search(phrase, forms=None):
    """EDGAR full-text search (filings since 2001): [(form, file date, names, adsh, document)]."""
    url = "https://efts.sec.gov/LATEST/search-index?q=" + quote(f'"{phrase}"')
    if forms:
        url += "&forms=" + quote(",".join(forms))
    doc = fetch_json(url, max_age=FRESH_S)
    out = []
    for h in (doc.get("hits") or {}).get("hits") or []:
        src = h.get("_source") or {}
        adsh, _, docname = (h.get("_id") or "").partition(":")
        out.append((src.get("form") or src.get("root_form") or "?", src.get("file_date") or "?",
                    "; ".join(src.get("display_names") or []), adsh, docname))
    return out


def filings(cik, forms=ANNUAL_FORMS, n=4):
    """The latest filings of a filer of the given forms, newest first: dicts with form, filed, period, accession, url."""
    cik = int(cik)
    doc = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    rec = (doc.get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(rec.get("form") or []):
        if form not in forms:
            continue
        acc = rec["accessionNumber"][i]
        primary = rec["primaryDocument"][i]
        out.append({"form": form, "filed": rec["filingDate"][i], "period": rec.get("reportDate", [""] * (i + 1))[i],
                    "accession": acc, "name": doc.get("name"),
                    "index": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{primary}"})
        if len(out) >= n:
            break
    return out


ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
HREF = re.compile(r'href="([^"]+)"', re.I)


def filing_documents(url):
    """The documents of a filing from its index page: [(seq, description, type, url)]. `url` is the index page or any
    document of the filing."""
    u = urlsplit(url)
    m = re.match(r"^/Archives/edgar/data/(\d+)/(\d{18})(?:/|$)", u.path)
    if not m:
        raise SecError(f"not the address of a filing ({where(url)})")
    cik, acc = m.group(1), m.group(2)
    adsh = f"{acc[:10]}-{acc[10:12]}-{acc[12:]}"
    index = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{adsh}-index.htm"
    page = fetch_bytes(index).decode("utf-8", "replace")
    out = []
    for row in ROW.findall(page):
        cells = TD.findall(row)
        if len(cells) < 4:
            continue
        href = HREF.search(row)
        if not href:
            continue
        clean = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split()) for c in cells]
        target = urljoin(index, href.group(1))
        if target.startswith("https://www.sec.gov/ix?doc="):
            target = "https://www.sec.gov" + target.split("=", 1)[1]
        out.append((clean[0], clean[1], clean[3], target))
    return out


def passages(text, pattern, context=300, limit=20):
    """The passages of a text that match a regular expression (case-insensitive), each with its offset."""
    out = []
    for m in re.finditer(pattern, text, re.I):
        a, b = max(0, m.start() - context), min(len(text), m.end() + context)
        out.append((m.start(), text[a:b].replace("\n", " / ")))
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------------------------------------------------------- cli

def _arg(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            val = args[i + 1]
            del args[i:i + 2]
            return val
    return default


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    cmd = args.pop(0)
    try:
        if cmd == "cik":
            for r in find_cik(" ".join(args))[:40]:
                print(f"{r['cik']:>10}  {r['ticker']:<8} {r['title']}")
        elif cmd == "search":
            forms = _arg(args, "--forms")
            for form, date, names, adsh, docname in full_text_search(" ".join(args), forms.split(",") if forms else None):
                print(f"{form:<7} {date}  {adsh}  {docname}  {names}")
        elif cmd == "filings":
            forms = _arg(args, "--forms")
            n = int(_arg(args, "--n", "4"))
            for f in filings(args[0], tuple(forms.split(",")) if forms else ANNUAL_FORMS, n):
                print(f"{f['form']:<7} filed {f['filed']}  period {f['period']}  {f['name']}\n        {f['url']}\n        {f['index']}")
        elif cmd == "index":
            every = "--all" in args
            args = [a for a in args if a != "--all"]
            for seq, desc, typ, url in filing_documents(args[0]):
                if every or not (typ in ("GRAPHIC", "XML", "ZIP", "PDF") or typ.startswith("EX-101") or not typ):
                    print(f"{seq:>3} {typ:<12} {desc[:60]:<60} {url}")
        elif cmd == "get":
            path, text = text_of(args[0])
            print(f"{os.path.relpath(path, ROOT)}  ({len(text):,} characters)")
        elif cmd == "find":
            context = int(_arg(args, "--context", "300"))
            limit = int(_arg(args, "--max", "20"))
            path, text = text_of(args[0])
            hits = passages(text, args[1], context, limit)
            print(f"{len(hits)} passage(s) in {os.path.relpath(path, ROOT)}")
            for off, s in hits:
                print(f"\n@{off}: {s}")
        else:
            print(f"unknown command {cmd!r}; see --help", file=sys.stderr)
            return 2
    except SecError as e:
        print(f"sec_edgar: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
