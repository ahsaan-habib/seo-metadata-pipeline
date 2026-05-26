"""pytest-django gives each test a fresh database. The model call is
replaced by a script of HTTP replies; Celery tasks run in-process with
.apply(), so no Redis. test_smoke_ollama.py is opt-in."""
import json

import httpx
import pytest


@pytest.fixture
def ollama(monkeypatch):
    """Script the replies of metadata.generate's httpx.post."""
    def install(*replies):
        calls = []

        def post(url, json=None, timeout=None):
            calls.append(json)
            r = replies[min(len(calls), len(replies)) - 1]
            if isinstance(r, httpx.Response):
                return r
            return httpx.Response(200, json={"message": {"content": r}, "prompt_eval_count": 300,
                                             "eval_count": 60}, request=httpx.Request("POST", url))

        monkeypatch.setattr("metadata.generate.httpx.post", post)
        return calls
    return install


def meta(title="Waterproof Trail Running Shoes for Women",
         desc="Lightweight waterproof trail shoes for women with a grippy sole, sizes 36 to 42, in three colours.",
         confidence=0.7):
    return json.dumps({"title": title, "description": desc, "rationale": "title was a duplicate", "confidence": confidence})
