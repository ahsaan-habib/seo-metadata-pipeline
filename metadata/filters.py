"""Filter before you generate, in plain code.

A page with a good, unique, correctly sized title doesn't need a model to say
so. Length checks and duplicate detection are a query; the cheapest model
call is the one you don't make.
"""
from __future__ import annotations

from django.db.models import Count

from .models import Page

TITLE_LEN = (30, 60)
DESC_LEN = (70, 160)


def reasons(page: Page, dup_titles: set[str], dup_descs: set[str]) -> list[str]:
    out = []
    t, d = page.title.strip(), page.description.strip()
    if not t:
        out.append("missing title")
    elif not TITLE_LEN[0] <= len(t) <= TITLE_LEN[1]:
        out.append(f"title length {len(t)}")
    elif t in dup_titles:
        out.append("duplicate title")
    if not d:
        out.append("missing description")
    elif not DESC_LEN[0] <= len(d) <= DESC_LEN[1]:
        out.append(f"description length {len(d)}")
    elif d in dup_descs:
        out.append("duplicate description")
    return out


def candidates(run_id: int):
    """Indexable 200 pages whose metadata has a problem, with the problem attached."""
    base = Page.objects.filter(run_id=run_id, status_code=200, indexable=True)
    dup_titles = set(base.exclude(title="").values("title").annotate(n=Count("id"))
                     .filter(n__gt=1).values_list("title", flat=True))
    dup_descs = set(base.exclude(description="").values("description").annotate(n=Count("id"))
                    .filter(n__gt=1).values_list("description", flat=True))
    for page in base.iterator():
        why = reasons(page, dup_titles, dup_descs)
        if why:
            yield page, why
