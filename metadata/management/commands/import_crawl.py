from pathlib import Path

from django.core.management.base import BaseCommand

from metadata.importer import import_csv
from metadata.models import Run


class Command(BaseCommand):
    help = "Import a Screaming Frog 'Internal: HTML' CSV export as a new run"

    def add_arguments(self, parser):
        parser.add_argument("csv")
        parser.add_argument("--name", default="")

    def handle(self, csv, name, **kw):
        run = Run.objects.create(name=name or Path(csv).stem)
        n = import_csv(Path(csv), run)
        self.stdout.write(f"run {run.id}: imported {n} pages")
