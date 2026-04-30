from django.db import models


class Run(models.Model):
    name = models.CharField(max_length=200)
    created = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="running")   # running | done


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
    status = models.CharField(max_length=20, default="pending")   # never "published"
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
