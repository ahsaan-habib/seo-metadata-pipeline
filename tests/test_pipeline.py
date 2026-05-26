import csv
import io
from decimal import Decimal

import httpx
import pytest
from django.core.management import call_command

from conftest import meta
from metadata import filters, generate, tasks
from metadata.importer import import_csv, url_hash
from metadata.models import Draft, Page, Run

pytestmark = pytest.mark.django_db

HEAD = ["Address", "Content Type", "Status Code", "Indexability", "Title 1", "Meta Description 1", "H1-1",
        "H2-1", "Canonical Link Element 1", "Word Count", "First Paragraph 1"]
GOOD_DESC = "A clear description of this page that is comfortably between seventy and 160 chars"


def crawl(tmp_path, rows):
    p = tmp_path / "internal_html.csv"
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEAD)
        w.writerows(rows)
    return p


def row(url, title=None, desc=None, status="200", indexability="Indexable", canonical="",
        ctype="text/html; charset=UTF-8"):
    # unique by default, so only the rows a test makes alike count as duplicates
    title = f"A perfectly fine page title for {url[-6:]}" if title is None else title
    desc = f"{GOOD_DESC} ({url[-6:]})" if desc is None else desc
    return [url, ctype, status, indexability, title, desc, "H1 " + url, "Sizes", canonical, "420",
            "Our waterproof trail shoe has a grippy sole and comes in three colours for women runners."]


@pytest.fixture
def run_with_pages(tmp_path):
    run = Run.objects.create(name="t")
    n = import_csv(crawl(tmp_path, [
        row("https://s/ok"),
        row("https://s/short", title="Shoes"),
        row("https://s/dup1", title="Same title for two different pages here"),
        row("https://s/dup2", title="Same title for two different pages here"),
        row("https://s/nodesc", desc=""),
        row("https://s/shoes?colour=red", title="x"),                           # faceted: skipped
        row("https://s/old", title="x", canonical="https://s/new"),              # canonicalised: skipped
        row("https://s/gone", title="x", status="404"),
        row("https://s/noindex", title="x", indexability="Non-Indexable"),
        row("https://s/logo.png", ctype="image/png"),
        row("https://s/ok"),                                                      # duplicate row
    ]), run)
    return run, n


def test_import_and_filter(run_with_pages):
    run, n = run_with_pages
    assert n == 10 and Page.objects.filter(run=run).count() == 9          # duplicate url ignored
    got = {p.url: why for p, why in filters.candidates(run.id)}
    assert got == {"https://s/short": ["title length 5"], "https://s/dup1": ["duplicate title"],
                   "https://s/dup2": ["duplicate title"], "https://s/nodesc": ["missing description"]}


def page(run, url="https://s/short", reasons=("title length 5",)):
    p = Page.objects.get(run=run, url_hash=url_hash(url))
    p.reasons = list(reasons)
    p.save()
    return p


def test_generate_validates_and_repairs_once(run_with_pages, ollama):
    run, _ = run_with_pages
    p = page(run)
    calls = ollama(meta(title="Too short"), meta())
    r = generate.generate(p)
    assert r.title.startswith("Waterproof") and r.input_tokens == 600 and len(calls) == 2
    assert "failed validation" in calls[1]["messages"][-1]["content"]
    assert "Problems: title length 5" in calls[0]["messages"][1]["content"]
    ollama("nope", "still nope")
    with pytest.raises(generate.InvalidOutput):
        generate.generate(p)
    ollama(httpx.Response(429, headers={"Retry-After": "7"}))
    with pytest.raises(generate.RateLimited) as e:
        generate.generate(p)
    assert e.value.retry_after == 7.0


def test_generated_titles_pass_the_filter_that_sent_them():
    # a 20-29 char title would be flagged "title length" again on the next run
    assert generate.Metadata.model_fields["title"].metadata[0].min_length >= filters.TITLE_LEN[0]


def test_task_is_idempotent_and_reuses_unchanged_pages(run_with_pages, ollama):
    run, _ = run_with_pages
    page(run)
    calls = ollama(meta())
    assert tasks.draft_metadata.apply(args=(run.id, "https://s/short")).get() == "drafted"
    assert tasks.draft_metadata.apply(args=(run.id, "https://s/short")).get() == "exists"
    d = Draft.objects.get()
    assert d.status == "pending" and d.input_tokens == 300 and len(calls) == 1
    assert Run.objects.get(id=run.id).spent_usd == d.cost_usd

    # same input in a new run: no model call, previous draft reused
    run2 = Run.objects.create(name="t2")
    p2 = Page.objects.get(run=run, url_hash=url_hash("https://s/short"))
    p2.pk, p2.run = None, run2
    p2.save()
    assert tasks.draft_metadata.apply(args=(run2.id, "https://s/short")).get() == "unchanged"
    assert len(calls) == 1 and Draft.objects.filter(run=run2).get().rationale.startswith("unchanged since run")


def test_budget_and_failed_rows(run_with_pages, ollama):
    run, _ = run_with_pages
    page(run)
    page(run, "https://s/nodesc", ["missing description"])
    Run.objects.filter(id=run.id).update(spent_usd=Decimal("5"), budget_usd=Decimal("5"))
    assert tasks.draft_metadata.apply(args=(run.id, "https://s/short")).get() == "budget"
    assert Run.objects.get(id=run.id).status == "stopped_budget"
    Run.objects.filter(id=run.id).update(spent_usd=0, status="running")
    ollama("bad", "bad")
    assert tasks.draft_metadata.apply(args=(run.id, "https://s/nodesc")).get() == "failed"
    assert Draft.objects.get().status == "failed"


def test_rate_limit_retries_then_drafts(run_with_pages, ollama, monkeypatch):
    run, _ = run_with_pages
    page(run)
    calls = ollama(httpx.Response(503), meta())
    assert tasks.draft_metadata.apply(args=(run.id, "https://s/short")).get() == "drafted"
    assert len(calls) == 2
    assert 0 <= tasks.backoff_with_jitter(2) <= 40


def test_commands_import_start_export(tmp_path, monkeypatch):
    enqueued = []
    monkeypatch.setattr(tasks.draft_metadata, "delay", lambda run_id, url: enqueued.append(url))
    out = io.StringIO()
    call_command("import_crawl", str(crawl(tmp_path, [row("https://s/a"), row("https://s/b", title="Short")])),
                 stdout=out)
    run = Run.objects.get()
    call_command("start_run", run.id, "--budget", "1.5", stdout=out)
    assert enqueued == ["https://s/b"] and Run.objects.get().budget_usd == Decimal("1.5")
    p = Page.objects.get(url="https://s/b")
    assert p.reasons == ["title length 5"]
    Draft.objects.create(key="k", run=run, page=p, url=p.url, title="New title", description="New desc",
                         status="approved", reviewed_by="ana")
    Draft.objects.create(key="k2", run=run, page=p, url=p.url + "x", title="t", description="d", status="pending")
    dest = tmp_path / "out.csv"
    call_command("export_approved", run.id, "--out", str(dest), stdout=out)
    lines = dest.read_text().splitlines()
    assert lines == ["url,title,description,approved_by,approved_at", "https://s/b,New title,New desc,ana,"]
    assert "1 need work (50%)" in out.getvalue()
