"""The review gate. Nothing generated reaches a live page without passing
through here, so it has to be fast enough that nobody is tempted to skip it:
old and new side by side, bulk approve, keyboard shortcuts.

(We built generation first and reviewed 2,140 drafts in a spreadsheet once.
That's why this exists, and why it should have been built first.)
"""
from __future__ import annotations

import difflib

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .models import Draft, Run


def diff(old: str, new: str) -> str:
    """Word-level diff as HTML: removed struck through, added highlighted."""
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op in ("delete", "replace"):
            out.append(f"<del>{escape(' '.join(a[i1:i2]))}</del>")
        if op in ("insert", "replace"):
            out.append(f"<ins>{escape(' '.join(b[j1:j2]))}</ins>")
        if op == "equal":
            out.append(escape(" ".join(a[i1:i2])))
    return mark_safe(" ".join(out))


@staff_member_required
def review(request, run_id: int):
    run = get_object_or_404(Run, id=run_id)
    if request.method == "POST":
        action = request.POST["action"]
        ids = request.POST.getlist("ids")
        now = timezone.now()
        who = request.user.get_username()
        for d in Draft.objects.filter(run=run, id__in=ids, status__in=["pending", "failed"]):
            if action == "approve":
                d.title = request.POST.get(f"title_{d.id}", d.title).strip()
                d.description = request.POST.get(f"desc_{d.id}", d.description).strip()
                d.status = "approved"
            elif action == "reject":
                d.status = "rejected"
            d.reviewed_by, d.reviewed_at = who, now
            d.save()
        return redirect("review", run_id=run.id)

    # failed first, then least confident first: uncertain drafts get reviewed
    # while attention is highest
    drafts = (Draft.objects.filter(run=run, status__in=["pending", "failed"]).select_related("page")
              .order_by("-status", F("confidence").asc(nulls_first=True), "id")[:200])
    rows = [{"d": d, "title_diff": diff(d.page.title, d.title),
             "desc_diff": diff(d.page.description, d.description)} for d in drafts]
    counts = {s: Draft.objects.filter(run=run, status=s).count()
              for s in ("pending", "failed", "approved", "rejected")}
    return render(request, "metadata/review.html", {"run": run, "rows": rows, "counts": counts})
