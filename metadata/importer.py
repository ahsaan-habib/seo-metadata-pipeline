"""Screaming Frog "Internal: HTML" CSV export -> Page rows.

The crawl is deliberately the boring part: Screaming Frog already handles
redirects, canonicals, JS rendering and robots rules. This just reads its
export. Column names are the ones the export uses; a custom extraction for
the main content's first paragraph is picked up if present.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .models import Page, Run

COLS = {
    "url": "Address",
    "status": "Status Code",
    "indexability": "Indexability",
    "title": "Title 1",
    "description": "Meta Description 1",
    "h1": "H1-1",
    "canonical": "Canonical Link Element 1",
    "words": "Word Count",
}
H2_COLS = ("H2-1", "H2-2")
BODY_COLS = ("First Paragraph 1", "Content 1")   # custom extraction, if configured


def url_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def _int(v: str | None) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


def import_csv(path: Path, run: Run) -> int:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    pages = []
    for r in rows:
        url = r.get(COLS["url"], "").strip()
        if not url or "html" not in r.get("Content Type", "text/html"):
            continue
        pages.append(Page(
            run=run, url=url, url_hash=url_hash(url),
            status_code=_int(r.get(COLS["status"])),
            indexable=r.get(COLS["indexability"], "Indexable") == "Indexable",
            title=r.get(COLS["title"], ""), description=r.get(COLS["description"], ""),
            h1=r.get(COLS["h1"], ""), h2s=[r[c] for c in H2_COLS if r.get(c)],
            canonical=r.get(COLS["canonical"], ""), word_count=_int(r.get(COLS["words"])),
            body=next((r[c] for c in BODY_COLS if r.get(c)), ""),
        ))
    Page.objects.bulk_create(pages, batch_size=1000, ignore_conflicts=True)
    return len(pages)
