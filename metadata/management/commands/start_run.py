from django.core.management.base import BaseCommand

from metadata.models import Page
from metadata.tasks import draft_metadata


class Command(BaseCommand):
    help = "Enqueue one draft job per page in a run"

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int)

    def handle(self, run_id, **kw):
        urls = list(Page.objects.filter(run_id=run_id).values_list("url", flat=True))
        for url in urls:
            draft_metadata.delay(run_id, url)
        self.stdout.write(f"enqueued {len(urls)} pages")
