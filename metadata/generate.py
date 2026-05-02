"""One page in, one validated draft out.

The model call is the only non-deterministic function in the pipeline and the
only one that can return something structurally invalid, so: JSON schema in
the request, Pydantic on the way out, one repair attempt with the validation
error, then fail.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from django.conf import settings
from pydantic import BaseModel, Field, ValidationError

from .models import Page


class Metadata(BaseModel):
    title: str = Field(min_length=20, max_length=60)
    description: str = Field(min_length=70, max_length=160)
    rationale: str = Field(max_length=200, description="one line: what was wrong and what changed")


@dataclass
class Result:
    title: str
    description: str
    rationale: str
    input_tokens: int
    output_tokens: int


class RateLimited(Exception):
    def __init__(self, retry_after: float | None = None):
        super().__init__(f"rate limited (retry after {retry_after})")
        self.retry_after = retry_after


class InvalidOutput(Exception):
    pass


SYSTEM = """You write SEO metadata for one web page.
- title: 20-60 characters, specific to this page, no site name, no clickbait.
- description: 70-160 characters, says what the page offers, plain language.
- Only state facts present in the page content. Never invent prices, specs,
  offers, locations or claims.
- rationale: one line for the human reviewer: what was wrong with the current
  metadata and what you changed.
Reply as JSON with keys title, description, rationale."""


def first_paragraph(body: str, words: int = 90) -> str:
    para = next((p for p in body.split("\n\n") if len(p.split()) >= 12), body)
    return " ".join(para.split()[:words])


def build_input(page: Page) -> str:
    """The smallest input that answers the question. Whole page bodies cost
    far more tokens and didn't make the titles better: headings, the first
    paragraph and the current metadata carry what a title needs."""
    h2 = "; ".join(page.h2s[:3])
    return (f"URL: {page.url}\nProblems: {', '.join(page.reasons) or 'none'}\n"
            f"Current title: {page.title or '(none)'}\n"
            f"Current description: {page.description or '(none)'}\n"
            f"H1: {page.h1}\nH2: {h2}\n"
            f"First paragraph: {first_paragraph(page.body)}")


def _call(messages: list[dict]) -> tuple[str, int, int]:
    r = httpx.post(f"{settings.OLLAMA_URL}/api/chat", timeout=120, json={
        "model": settings.LLM_MODEL, "messages": messages, "stream": False, "think": False,
        "format": Metadata.model_json_schema(), "options": {"temperature": 0.0}})
    if r.status_code in (429, 503):
        ra = r.headers.get("Retry-After")
        raise RateLimited(float(ra) if ra and ra.replace(".", "", 1).isdigit() else None)
    r.raise_for_status()
    data = r.json()
    return data["message"]["content"], data.get("prompt_eval_count", 0), data.get("eval_count", 0)


def generate(page: Page) -> Result:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_input(page)}]
    tin = tout = 0
    for attempt in range(2):
        raw, i, o = _call(messages)
        tin, tout = tin + i, tout + o
        try:
            m = Metadata.model_validate_json(raw)
            return Result(m.title, m.description, m.rationale, tin, tout)
        except ValidationError as e:
            if attempt == 1:
                raise InvalidOutput(str(e)) from e
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"That failed validation:\n{e}\nReturn corrected JSON only."}]
    raise AssertionError("unreachable")
