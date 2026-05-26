import pytest
from django.contrib.auth.models import User

from metadata.models import Draft, Page, Run
from metadata.views import diff

pytestmark = pytest.mark.django_db


def test_diff_escapes_and_marks_changes():
    assert diff("Old <b>title</b>", "New <b>title</b>") == "<del>Old</del> <ins>New</ins> &lt;b&gt;title&lt;/b&gt;"


@pytest.fixture
def drafts():
    run = Run.objects.create(name="r")
    out = []
    for i, (status, conf) in enumerate([("pending", 0.9), ("pending", 0.2), ("failed", None)]):
        p = Page.objects.create(run=run, url=f"https://s/{i}", url_hash=str(i), title=f"Old {i}",
                                description="old desc")
        out.append(Draft.objects.create(key=f"k{i}", run=run, page=p, url=p.url, title=f"New {i}",
                                        description="new desc", status=status, confidence=conf))
    return run, out


def test_review_needs_staff(client, drafts):
    run, _ = drafts
    assert client.get(f"/review/{run.id}/").status_code == 302


def test_queue_order_and_bulk_actions(client, drafts):
    run, (high, low, failed) = drafts
    client.force_login(User.objects.create_user("ana", password="x", is_staff=True))
    html = client.get(f"/review/{run.id}/").content.decode()
    assert html.index("https://s/2") < html.index("https://s/1") < html.index("https://s/0")   # failed, least sure
    r = client.post(f"/review/{run.id}/", {"action": "approve", "ids": [low.id], f"title_{low.id}": " Edited title "})
    assert r.status_code == 302
    low.refresh_from_db()
    assert (low.status, low.title, low.reviewed_by) == ("approved", "Edited title", "ana") and low.reviewed_at
    client.post(f"/review/{run.id}/", {"action": "reject", "ids": [high.id, low.id]})
    high.refresh_from_db()
    low.refresh_from_db()
    assert high.status == "rejected" and low.status == "approved"      # decided rows don't flip
