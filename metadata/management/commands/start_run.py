from django.core.management.base import BaseCommand

from metadata.filters import candidates
from metadata.models import Page
from metadata.tasks import draft_metadata


class Command(BaseCommand):
    help = "Enqueue one draft job per page in a run"

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int)
        parser.add_argument("--budget", type=float, help="hard ceiling in USD for this run")

    def handle(self, run_id, budget=None, **kw):
        if budget is not None:
            from metadata.models import Run

            Run.objects.filter(id=run_id).update(budget_usd=budget)
        total = Page.objects.filter(run_id=run_id).count()
        n = 0
        for page, why in candidates(run_id):
            page.reasons = why
            page.save(update_fields=["reasons"])
            draft_metadata.delay(run_id, page.url)
            n += 1
        self.stdout.write(f"{total} pages, {n} need work ({n / total:.0%}) -> enqueued" if total else "no pages")
