"""Approved drafts -> CSV for the CMS import. This is the only way out of the
pipeline, and it only ever contains drafts a person approved."""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from metadata.models import Draft


class Command(BaseCommand):
    help = "Write approved drafts for a run to a CSV (url,title,description,approved_by,approved_at)"

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int)
        parser.add_argument("--out", default="")

    def handle(self, run_id, out, **kw):
        path = Path(out or f"exports/run-{run_id}-approved.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        drafts = Draft.objects.filter(run_id=run_id, status="approved").order_by("url")
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["url", "title", "description", "approved_by", "approved_at"])
            for d in drafts:
                w.writerow([d.url, d.title, d.description, d.reviewed_by,
                            d.reviewed_at.isoformat() if d.reviewed_at else ""])
        self.stdout.write(f"{drafts.count()} approved drafts -> {path}")
