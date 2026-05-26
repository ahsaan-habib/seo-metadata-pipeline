"""One real draft from a local model. Opt-in:

    RUN_OLLAMA=1 pytest tests/test_smoke_ollama.py -s
"""
import os

import pytest

from metadata.generate import generate
from metadata.models import Page, Run

pytestmark = [pytest.mark.skipif(os.environ.get("RUN_OLLAMA") != "1", reason="set RUN_OLLAMA=1 to run"),
              pytest.mark.django_db]


def test_real_metadata_validates():
    run = Run.objects.create(name="smoke")
    p = Page.objects.create(
        run=run, url="https://shop.example/trail-shoes-women", url_hash="x", title="Shoes", description="",
        h1="Women's waterproof trail running shoes", h2s=["Sizes and fit", "Care"],
        body="Our waterproof trail shoe for women has a grippy rubber sole, a breathable membrane and comes "
             "in sizes 36 to 42 in three colours.", reasons=["title length 5", "missing description"])
    r = generate(p)
    print("\n", r)
    assert 30 <= len(r.title) <= 60 and 70 <= len(r.description) <= 160
