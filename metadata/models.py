from django.db import models


class Run(models.Model):
    name = models.CharField(max_length=200)
    created = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="running")   # running | stopped_budget | done
    # A hard ceiling, not an alert. It exists because a crawl once wandered into
    # a faceted-search URL space and found 90,000 pages.
    budget_usd = models.DecimalField(max_digits=10, decimal_places=4, default=5)
    spent_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)


class Page(models.Model):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="pages")
    url = models.URLField(max_length=2000)
    url_hash = models.CharField(max_length=40, db_index=True)
    status_code = models.IntegerField(null=True)
    indexable = models.BooleanField(default=True)
    title = models.TextField(blank=True)
    description = models.TextField(blank=True)
    h1 = models.TextField(blank=True)
    h2s = models.JSONField(default=list)
    canonical = models.URLField(max_length=2000, blank=True)
    word_count = models.IntegerField(null=True)
    body = models.TextField(blank=True)
    reasons = models.JSONField(default=list)          # why the filter sent it to the model
    input_hash = models.CharField(max_length=40, blank=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "url_hash"], name="page_once_per_run")]


class Draft(models.Model):
    # "{run_id}:{sha1(url)}". The unique index decides idempotency, not a SELECT:
    # a retry, a resumed run and a double-enqueue all cost nothing.
    key = models.CharField(max_length=80, unique=True)
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="drafts")
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="drafts")
    url = models.URLField(max_length=2000)
    title = models.TextField()
    description = models.TextField()
    rationale = models.TextField(blank=True)          # why, for the reviewer
    # Used ONLY to order the review queue (least sure first, while attention is
    # highest). Never to auto-approve: a model's stated confidence is not a
    # calibrated probability, and it's most confident on fluent, wrong output.
    confidence = models.FloatField(null=True)
    status = models.CharField(max_length=20, default="pending")   # never "published"
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    input_hash = models.CharField(max_length=40, blank=True, db_index=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)   # per row, not per run
    reviewed_by = models.CharField(max_length=150, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
