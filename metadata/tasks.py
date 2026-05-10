"""tasks/draft_metadata — one queued job per page, result persisted at once.

The first version was one long script holding results in memory and writing
at the end. It died at page 812 and kept nothing.
"""
from __future__ import annotations

import hashlib
import random
import time
from decimal import Decimal

from celery import shared_task
from django.db import IntegrityError
from django.db.models import F

from .costs import price
from .generate import InvalidOutput, RateLimited, build_input, generate
from .importer import url_hash
from .models import Draft, Page, Run


def backoff_with_jitter(retries: int, base: float = 10.0, cap: float = 300.0) -> float:
    """Full jitter: 12 workers retrying in lockstep is how run one stalled for 40 minutes."""
    return random.uniform(0, min(cap, base * 2 ** retries))


@shared_task(bind=True, max_retries=3)
def draft_metadata(self, run_id: int, url: str) -> str:
    key = f"{run_id}:{url_hash(url)}"
    # Idempotency first: a retry, a resumed run and a double-enqueue all cost nothing.
    if Draft.objects.filter(key=key).exists():
        return "exists"
    page = Page.objects.get(run_id=run_id, url_hash=url_hash(url))
    # Hash the exact input we would send: a page that hasn't changed since an
    # earlier run costs one comparison instead of a model call.
    input_hash = hashlib.sha1(build_input(page).encode()).hexdigest()
    previous = (Draft.objects.filter(page__url_hash=page.url_hash, input_hash=input_hash)
                .exclude(run_id=run_id).exclude(status="rejected").order_by("-created").first())
    if previous:
        Draft.objects.get_or_create(key=key, defaults=dict(
            run_id=run_id, page=page, url=url, title=previous.title, description=previous.description,
            rationale=f"unchanged since run {previous.run_id}; reused", status=previous.status,
            input_hash=input_hash))
        return "unchanged"
    run = Run.objects.get(id=run_id)
    if run.status == "stopped_budget" or run.spent_usd >= run.budget_usd:
        Run.objects.filter(id=run_id).update(status="stopped_budget")
        return "budget"
    t0 = time.perf_counter()
    try:
        result = generate(page)
    except RateLimited as e:
        raise self.retry(countdown=e.retry_after or backoff_with_jitter(self.request.retries))
    except InvalidOutput as e:
        # invalid twice: a visible failed row for the reviewer, not a line in a worker log
        Draft.objects.get_or_create(key=key, defaults=dict(
            run_id=run_id, page=page, url=url, title=page.title, description=page.description,
            rationale=f"model output failed validation twice: {str(e)[:300]}", status="failed",
            input_hash=input_hash))
        return "failed"
    cost = Decimal(str(price(time.perf_counter() - t0, result.input_tokens, result.output_tokens)))
    Run.objects.filter(id=run_id).update(spent_usd=F("spent_usd") + cost)
    try:
        Draft.objects.create(
            key=key, run_id=run_id, page=page, url=url,
            title=result.title, description=result.description, rationale=result.rationale,
            confidence=result.confidence, status="pending", input_hash=input_hash,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            cost_usd=cost,
        )
    except IntegrityError:      # lost a race with a duplicate job: the index decided
        return "exists"
    return "drafted"
