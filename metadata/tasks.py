"""tasks/draft_metadata — one queued job per page, result persisted at once.

The first version was one long script holding results in memory and writing
at the end. It died at page 812 and kept nothing.
"""
from __future__ import annotations

import random

from celery import shared_task
from django.db import IntegrityError

from .generate import RateLimited, generate
from .importer import url_hash
from .models import Draft, Page


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
    try:
        result = generate(page)
    except RateLimited as e:
        raise self.retry(countdown=e.retry_after or backoff_with_jitter(self.request.retries))
    try:
        Draft.objects.create(
            key=key, run_id=run_id, page=page, url=url,
            title=result.title, description=result.description, rationale=result.rationale,
            status="pending",
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        )
    except IntegrityError:      # lost a race with a duplicate job: the index decided
        return "exists"
    return "drafted"
