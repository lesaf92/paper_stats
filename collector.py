"""Collect journal review times: arXiv finds papers, Crossref and the arXiv PDF give the dates."""
import html
import io
import json
import logging
import os
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime

import pypdf

logging.getLogger('pypdf').setLevel(logging.ERROR)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'cache.json')
NS = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
MAILTO = os.environ.get('CROSSREF_MAILTO', '')
USER_AGENT = f'paper-stats/0.2 (mailto:{MAILTO})' if MAILTO else 'paper-stats/0.2'
ARXIV_DELAY = 3  # arXiv asks for one request every 3 seconds
CROSSREF_DELAY = 0.2  # Crossref public pool allows 5 requests per second
MAX_BYTES = 40 * 1024 * 1024  # some arXiv PDFs are huge; skip anything bigger
MAX_FETCHES = 15  # arXiv pages per journal, so a journal with no valid papers can't loop forever
MAX_REVIEW_DAYS = 5 * 365  # longer than this is a parsing error, not a review

# A date as journals print it: "24 February 2025", "February 24, 2025", "Feb. 24 2025" or "2025-02-24"
DATE_RE = r'(\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2}\s*,?\s+\d{4}|\d{4}-\d{2}-\d{2})'
RECEIVED_RE = re.compile(r'received:?\s+(?:on\s+)?' + DATE_RE, re.I)
ACCEPTED_RE = re.compile(r'accepted:?\s+(?:for publication\s+)?(?:on\s+)?' + DATE_RE, re.I)
DATE_FORMATS = ('%d %B %Y', '%B %d %Y', '%d %b %Y', '%b %d %Y', '%Y-%m-%d')


def http_get(url, max_retries=3):
    """GET with exponential backoff on 429/503. Returns the body, or None on failure."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read(MAX_BYTES + 1)
                return data if len(data) <= MAX_BYTES else None
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                wait = 10 * (attempt + 1)
                print(f"HTTP {e.code} for {url}. Retrying in {wait} seconds (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                print(f"HTTP Error {e.code} for {url}: {e.reason}")
                return None
        except Exception as e:
            print(f"Network error for {url}: {e}")
            return None
    print(f"Failed to fetch {url} after {max_retries} attempts.")
    return None


def parse_date(text):
    """'24 Feb. 2025', 'February 24, 2025', 'Sept 3 2021', '2025-02-24' -> ISO string, or None."""
    text = ' '.join(text.replace('.', ' ').replace(',', ' ').split()).replace('Sept ', 'Sep ')
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def first_date(rx, text):
    for m in rx.finditer(text):
        found = parse_date(m.group(1))
        if found:
            return found
    return None


def dates_from_text(text):
    """(received, accepted) from a 'Manuscript received ...; accepted ...' footnote."""
    flat = ' '.join(text.split())
    return first_date(RECEIVED_RE, flat), first_date(ACCEPTED_RE, flat)


def normalize(name):
    """Journal names compare equal regardless of case, '&' (Crossref sends '&amp;'), punctuation or a leading 'The'."""
    name = re.sub(r'[^a-z0-9 ]', ' ', html.unescape(name).lower().replace('&', ' and '))
    return re.sub(r'^the ', '', ' '.join(name.split()))


def full_date(field):
    parts = ((field or {}).get('date-parts') or [[]])[0]
    return date(*parts).isoformat() if len(parts) == 3 and None not in parts else None


def crossref_dates(work):
    """(received, accepted, published) from a Crossref work. Springer and Wiley deposit the history."""
    history = {a.get('name'): parse_date(str(a.get('value', ''))) for a in work.get('assertion', [])}
    published = full_date(work.get('published-online')) or full_date(work.get('created'))
    return history.get('received'), history.get('accepted'), published


def search_arxiv(journal, start, size):
    query = urllib.parse.quote(f'jr:"{journal}"')
    data = http_get(f"https://export.arxiv.org/api/query?search_query={query}&start={start}"
                    f"&max_results={size}&sortBy=submittedDate&sortOrder=descending")
    if not data:
        return []
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        print(f"Error parsing arXiv XML for {journal}: {e}")
        return []

    def text(entry, path):
        el = entry.find(path, NS)
        return el.text.strip() if el is not None and el.text else ''

    papers = []
    for entry in root.findall('atom:entry', NS):
        link = text(entry, 'atom:id')
        papers.append({
            'arxiv_id': re.sub(r'v\d+$', '', link.rsplit('abs/', 1)[-1]),
            'title': ' '.join(text(entry, 'atom:title').split()) or 'Unknown Title',
            'link': link,
            'submitted': text(entry, 'atom:published')[:10],
            'doi': text(entry, 'arxiv:doi'),
        })
    return papers


def crossref_record(paper, cache):
    """Venue and dates for a paper's DOI, cached by arXiv id."""
    if paper['arxiv_id'] in cache:
        return cache[paper['arxiv_id']]
    data = http_get(f"https://api.crossref.org/works/{urllib.parse.quote(paper['doi'])}")
    time.sleep(CROSSREF_DELAY)
    try:
        work = json.loads(data)['message'] if data else None
    except (ValueError, KeyError):
        work = None
    if not work:
        return None  # not cached: a network failure shouldn't drop the paper forever
    received, accepted, published = crossref_dates(work)
    measured = bool(received and accepted)
    cache[paper['arxiv_id']] = rec = {
        'venue': (work.get('container-title') or [''])[0],
        'received': received if measured else None,
        'accepted': accepted if measured else None,
        'published': published,
        'source': 'crossref' if measured else None,
        'pdf_checked': False,
    }
    return rec


def add_pdf_dates(arxiv_id, rec):
    """Fill rec's dates from the first page of the latest arXiv PDF, where IEEE prints them."""
    data = http_get(f"https://export.arxiv.org/pdf/{arxiv_id}")
    time.sleep(ARXIV_DELAY)
    if not data:
        return  # not marked checked: a network failure shouldn't drop the paper's dates forever
    rec['pdf_checked'] = True
    try:
        received, accepted = dates_from_text(pypdf.PdfReader(io.BytesIO(data)).pages[0].extract_text() or '')
    except Exception as e:
        print(f"Error reading PDF {arxiv_id}: {e}")
        return
    if received and accepted:
        rec.update(received=received, accepted=accepted, source='pdf')


def in_scope(rec, journal, year_start, year_end):
    """Crossref confirms the venue (arXiv's jr: search also matches e.g. 'Annual Review of ...')."""
    return (normalize(rec['venue']) == normalize(journal) and rec['published'] is not None
            and year_start <= int(rec['published'][:4]) <= year_end)


def days_between(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days if a and b else None


def build_row(paper, rec, journal):
    """The output row, or None when neither the review time nor the proxy is usable."""
    review = days_between(rec['received'], rec['accepted'])
    review = review if review and 0 < review <= MAX_REVIEW_DAYS else None
    proxy = days_between(paper['submitted'], rec['published'])
    proxy = proxy if proxy and proxy > 0 else None
    if review is None and proxy is None:
        return None
    return {
        'journal': journal, 'title': paper['title'], 'link': paper['link'], 'doi': paper['doi'],
        'source': rec['source'] if review else 'proxy',
        'received': rec['received'] if review else None, 'accepted': rec['accepted'] if review else None,
        'submitted': paper['submitted'], 'published': rec['published'],
        'review_days': review, 'proxy_days': proxy,
    }


def collect_journal(journal, num_samples, year_start, year_end, mine_pdfs, cache, on_paper):
    papers, start, batch_size = [], 0, num_samples * 2  # fetch more than needed to account for invalid ones
    for _ in range(MAX_FETCHES):
        entries = search_arxiv(journal, start, batch_size)
        time.sleep(ARXIV_DELAY)
        if not entries:
            break
        start += batch_size
        for p in entries:
            if not p['doi']:
                continue
            rec = crossref_record(p, cache)
            if not rec or not in_scope(rec, journal, year_start, year_end):
                continue
            if mine_pdfs and not rec['source'] and not rec['pdf_checked']:
                add_pdf_dates(p['arxiv_id'], rec)
            row = build_row(p, rec, journal)
            if row:
                papers.append(row)
                on_paper(len(papers))
                if len(papers) == num_samples:
                    return papers
    return papers


def load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cache(cache):
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(cache, f)
    os.replace(tmp, CACHE_FILE)  # atomic: a Ctrl+C mid-write can't leave a truncated cache


def collect(journals, config, on_progress=lambda fraction, message: None):
    """Rows for every journal. on_progress(fraction, message) reports as it goes."""
    cache, rows, n = load_cache(), [], config['num_samples']
    for i, journal in enumerate(journals):
        def report(k):
            on_progress((i + k / n) / len(journals), f"{journal} ({i + 1}/{len(journals)}): {k}/{n} papers")
        report(0)
        rows += collect_journal(journal, n, config['year_start'], config['year_end'],
                                config.get('mine_pdfs', True), cache, report)
        save_cache(cache)
    on_progress(1.0, f"Done: {len(rows)} papers")
    return rows


def quartiles(values):
    """(q1, median, q3) as Plotly's box plot computes them; None when there are no values."""
    if len(values) < 2:
        return (values[0],) * 3 if values else (None,) * 3
    return tuple(statistics.quantiles(values, n=4, method='inclusive'))


def summarize(rows):
    """Per-journal counts and quartiles, fastest median review first, journals with no measured data last."""
    by_journal = {}
    for r in rows:
        by_journal.setdefault(r['journal'], []).append(r)
    summary = []
    for journal, rs in by_journal.items():
        review = [r['review_days'] for r in rs if r['review_days']]
        proxy = [r['proxy_days'] for r in rs if r['proxy_days']]
        summary.append({'journal': journal, 'papers': len(rs), 'measured': len(review),
                        'review': quartiles(review), 'proxy': quartiles(proxy)})
    return sorted(summary, key=lambda s: (s['review'][1] is None, s['review'][1] or 0))
