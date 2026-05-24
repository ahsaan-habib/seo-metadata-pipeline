# seo-metadata-pipeline

Drafts SEO titles and meta descriptions for a large site from a crawl export,
using a local model (`qwen3:4b` via Ollama), and puts every draft in front of
a person before anything ships.

Connecting a model to a real backend is mostly not a modelling problem. It's
a batch-processing problem with a slow, non-deterministic function in the
middle that can return something structurally invalid. This repo is that
batch pipeline.

```
Screaming Frog "Internal: HTML" CSV ─▶ import_crawl ─▶ Page rows (one run)
   ─▶ start_run: FILTER in plain code (indexable 200s with missing, badly sized
      or duplicate metadata; skip ?params and pages canonicalised elsewhere)
   ─▶ one Celery task per page ── idempotent on (run, sha1(url)), unique index
        ├─ hash the trimmed input; unchanged since an earlier run → reuse, no call
        ├─ budget ceiling reached → stop
        ├─ Ollama with JSON schema → Pydantic → one repair retry → else "failed" row
        ├─ 429/503 → retry with Retry-After or backoff + full jitter
        └─ persist immediately, cost per row
   ─▶ REVIEW UI: old vs new diff, rationale line, least confident first,
      bulk approve, keyboard shortcuts
   ─▶ export_approved → CSV for the CMS. Nothing publishes itself.
```

## The batch-pipeline basics

| Problem | Fix |
|---|---|
| One long script dies halfway and keeps nothing | one queued job per page, result persisted at once |
| Retries and resumed runs regenerate everything | idempotency key with a unique index; the index decides, not a SELECT |
| Workers stampede the model server | concurrency 4, honour `Retry-After`, exponential backoff with full jitter |
| Free-text output parsed with a regex | JSON schema + Pydantic, one repair attempt, then a visible failed row |

## Cost

- **Filter first.** Most pages don't need a model to tell them their title is
  fine. `metadata/filters.py` is the biggest cost saving in the project.
- **Smallest useful input.** H1, top H2s, first paragraph, current metadata —
  not the page body.
- **Skip unchanged.** The exact model input is hashed; a re-run on a slowly
  changing site mostly costs hash comparisons.
- **Hard ceiling.** `start_run --budget` stops generation when the run's spend
  reaches it. Cost is stored per row (`COMPUTE_USD_PER_HOUR` × wall time for a
  local model, plus token prices if you swap in a hosted one).

## The review gate

A weak title costs a little traffic; a confidently wrong claim published
across hundreds of pages is a different category of problem. So:

- every draft carries a one-line rationale the reviewer can check;
- the queue shows failed rows first, then the least confident drafts, while
  attention is highest;
- confidence orders the queue and **never** auto-approves;
- bulk approve with a word diff and keyboard shortcuts, so review is fast
  enough that nobody wants to skip it;
- the only way out is `export_approved`.

## Run it

```bash
ollama pull qwen3:4b
docker compose up -d redis
make install && source .venv/bin/activate
make migrate && python manage.py createsuperuser
python manage.py import_crawl crawls/internal_html.csv --name "client-site may"
python manage.py start_run 1 --budget 2.00
make worker                       # in another terminal
make web                          # review at http://localhost:8060/review/1/
python manage.py export_approved 1
```

## Known gaps

There is no evaluation set: "good title" is whatever the reviewer approves,
so this makes no claim about quality numbers. Screaming Frog is a desktop
tool, so a person exports the CSV. And shipping better metadata isn't the
same as measuring its effect on rankings or click-through — that needs a
before/after this pipeline doesn't run.
